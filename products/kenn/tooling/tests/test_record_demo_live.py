"""Recorder checks use generated media; they never capture a desktop or touch Live."""

import hashlib
import json
import math
from pathlib import Path
import shutil
import struct
import subprocess

import pytest

from scripts import record_demo_live, record_demo_video


@pytest.fixture
def media_tools():
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        # Media integration checks need the operator's existing tools, not a
        # new downloaded dependency. The Mac qualification runs these checks.
        pytest.skip("ffmpeg and ffprobe are not installed")
    return ffmpeg, ffprobe


@pytest.fixture
def movie(tmp_path, media_tools):
    """Generate two audio streams so accidental default-stream loss is visible."""
    path = tmp_path / "generated.mov"
    subprocess.run([
        media_tools[0], "-hide_banner", "-loglevel", "error", "-n",
        "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=12:duration=2",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
        "-f", "lavfi", "-i", "sine=frequency=880:duration=2",
        "-map", "0:v", "-map", "1:a", "-map", "2:a",
        "-c:v", "mpeg4", "-c:a", "pcm_s16le", str(path),
    ], check=True)
    return path


def tone_amplitudes(path, ffmpeg, start_seconds=0.5, duration_seconds=1.0,
                    first_sample_seconds=0.0):
    """Measure each fixture tone in the audio track a normal player opens."""
    sample_rate = 8000  # Hz; enough for both tones and small enough for a direct DFT.
    decoded = subprocess.run([
        ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(path),
        "-map", "0:a:0", "-f", "s16le", "-ac", "1", "-ar", str(sample_rate), "pipe:1",
    ], capture_output=True, check=True)
    samples = [value / 32768.0 for (value,) in struct.iter_unpack("<h", decoded.stdout)]
    # PCM carries no timestamps; restore the encoded track's start offset so
    # measurement windows use the video clock, as an ordinary player does.
    samples = [0.0] * round(first_sample_seconds * sample_rate) + samples
    # A one-second window contains whole cycles of each tone; the default
    # 0.5–1.5 s window also avoids AAC startup/end padding.
    start = round(start_seconds * sample_rate)
    count = round(duration_seconds * sample_rate)
    samples = samples[start:start + count]
    assert len(samples) == count
    amplitudes = {}
    for frequency in (440, 880):
        radians_per_sample = 2 * math.pi * frequency / sample_rate
        real = math.fsum(value * math.cos(index * radians_per_sample)
                         for index, value in enumerate(samples))
        imaginary = math.fsum(value * math.sin(index * radians_per_sample)
                              for index, value in enumerate(samples))
        amplitudes[frequency] = 2 * math.hypot(real, imaginary) / len(samples)
    return amplitudes


def test_recording_mixes_both_sources_into_one_playback_track_without_applying_live_commands(
    tmp_path, movie, media_tools, monkeypatch,
):
    # Separate audio tracks made ordinary players choose music or narration;
    # measuring both tones in their default track catches either missing source.
    run = subprocess.run
    commands = []

    def passive_capture(command, **kwargs):
        commands.append(command)
        if command[0] == "screencapture":
            assert "-A" in command and "-g" in command
            shutil.copyfile(movie, command[-1])
            return subprocess.CompletedProcess(command, 0)
        assert Path(command[0]).name in {"git", "ffmpeg", "ffprobe"}
        return run(command, **kwargs)

    monkeypatch.setattr(record_demo_live.subprocess, "run", passive_capture)
    monkeypatch.setattr(record_demo_live.shutil, "which", lambda name: {
        "screencapture": "/usr/sbin/screencapture",
        "ffmpeg": media_tools[0], "ffprobe": media_tools[1],
    }.get(name))
    output = record_demo_live.record_take(tmp_path / "take", 285, True)
    receipt = json.loads((output.parent / "capture.json").read_text())
    assert receipt["status"] == "media_valid_unreviewed"
    assert len(receipt["media"]["raw"]["audio"]) == 2
    assert len(receipt["media"]["mp4"]["audio"]) == 1
    assert receipt["media"]["audio_playback"] == "normalized_mix_all_sources"
    # ffmpeg's sine fixture peaks at 1/8 full scale. A normalized two-source
    # mix halves each tone; this also rejects an unnormalized sum.
    for amplitude in tone_amplitudes(output, media_tools[0]).values():
        assert amplitude == pytest.approx(0.0625, rel=0.15)
    assert receipt["media"]["mp4"]["seconds"] == pytest.approx(2.0, abs=0.25)
    assert (output.parent / "raw.mov").read_bytes() == movie.read_bytes()
    assert receipt["sha256"]["showcase.mp4"] == hashlib.sha256(output.read_bytes()).hexdigest()
    assert "audible Live before/after" in receipt["human_checks_pending"]
    assert [cmd[0] for cmd in commands].count("screencapture") == 1


def test_one_audio_source_keeps_its_level_and_raw_track(tmp_path, movie, media_tools):
    # A music-only sound check must not lose gain merely because mixing exists.
    raw, output = tmp_path / "one-source.mov", tmp_path / "one-source.mp4"
    subprocess.run([
        media_tools[0], "-hide_banner", "-loglevel", "error", "-n", "-i", str(movie),
        "-map", "0:v:0", "-map", "0:a:0", "-c", "copy", str(raw),
    ], check=True)
    original = raw.read_bytes()
    info = record_demo_live.convert_take(raw, output, *media_tools)
    amplitudes = tone_amplitudes(output, media_tools[0])
    assert len(info["mp4"]["audio"]) == 1
    assert info["audio_playback"] == "single_source"
    assert amplitudes[440] == pytest.approx(0.125, rel=0.15)
    assert amplitudes[880] < 0.005
    assert raw.read_bytes() == original


def test_mix_keeps_the_longer_sources_tail_when_another_source_ends(tmp_path, media_tools):
    # A microphone stopping early must not cut the rest of Live's playback.
    raw, output = tmp_path / "unequal-sources.mov", tmp_path / "unequal-sources.mp4"
    subprocess.run([
        media_tools[0], "-hide_banner", "-loglevel", "error", "-n",
        "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=12:duration=3",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
        "-f", "lavfi", "-i", "sine=frequency=880:duration=3",
        "-map", "0:v", "-map", "1:a", "-map", "2:a",
        "-c:v", "mpeg4", "-c:a", "pcm_s16le", str(raw),
    ], check=True)
    original = raw.read_bytes()
    info = record_demo_live.convert_take(raw, output, *media_tools)
    tail = tone_amplitudes(output, media_tools[0], start_seconds=2.0)
    assert info["mp4"]["seconds"] == pytest.approx(3.0, abs=0.25)
    assert tail[880] > 0.05
    assert tail[440] < 0.005
    assert raw.read_bytes() == original


@pytest.mark.parametrize("other_source", [False, True])
def test_narration_start_offset_stays_aligned_with_video(tmp_path, media_tools, other_source):
    # amix moved a mic starting at 1 s to 0 s, and duration checks missed the
    # shifted narration because the longer music/video still lasted 3 s.
    raw, output = tmp_path / "delayed-mic.mov", tmp_path / "delayed-mic.mp4"
    audio_maps = ["-map", "1:a", "-map", "2:a"] if other_source else ["-map", "2:a"]
    subprocess.run([
        media_tools[0], "-hide_banner", "-loglevel", "error", "-n",
        "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=12:duration=3",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
        "-itsoffset", "1", "-f", "lavfi", "-i", "sine=frequency=880:duration=2",
        "-map", "0:v", *audio_maps, "-c:v", "mpeg4", "-c:a", "pcm_s16le", str(raw),
    ], check=True)
    original = raw.read_bytes()
    info = record_demo_live.convert_take(raw, output, *media_tools)
    timing = subprocess.run([
        media_tools[1], "-v", "error", "-select_streams", "a:0",
        "-show_entries", "stream=start_time", "-of", "json", str(output),
    ], capture_output=True, text=True, check=True)
    first_sample_seconds = float(json.loads(timing.stdout)["streams"][0]["start_time"])
    amplitudes = [
        tone_amplitudes(output, media_tools[0], start_seconds=start, duration_seconds=0.8,
                        first_sample_seconds=first_sample_seconds)[880]
        for start in (0.1, 1.1, 2.1)
    ]
    assert amplitudes[0] < 0.005
    assert amplitudes[1] > 0.05
    assert amplitudes[2] > 0.05
    assert info["mp4"]["seconds"] == pytest.approx(3.0, abs=0.25)
    assert raw.read_bytes() == original


def test_video_without_audio_is_rejected_before_encoding(tmp_path, media_tools):
    # A playable silent movie must not become the investor backup recording.
    raw, output = tmp_path / "silent.mov", tmp_path / "silent.mp4"
    subprocess.run([
        media_tools[0], "-hide_banner", "-loglevel", "error", "-n",
        "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=12:duration=1",
        "-c:v", "mpeg4", str(raw),
    ], check=True)
    with pytest.raises(ValueError, match="no audio stream"):
        record_demo_live.convert_take(raw, output, *media_tools)
    assert raw.exists() and not output.exists()


def test_encoding_refuses_to_overwrite_an_earlier_take(tmp_path, movie, media_tools):
    # Re-running a failed attempt used to overwrite the proof of what broke.
    output = tmp_path / "existing.mp4"
    output.write_bytes(b"earlier attempt")
    with pytest.raises(subprocess.CalledProcessError):
        record_demo_live.convert_take(movie, output, *media_tools)
    assert output.read_bytes() == b"earlier attempt"


def test_failed_capture_keeps_raw_evidence_and_a_failed_receipt(tmp_path, monkeypatch):
    # A recorder failure cannot print a passed demo or discard the failed take.
    monkeypatch.setattr(record_demo_live, "check_output_directory", lambda path: None)
    monkeypatch.setattr(record_demo_live.shutil, "which", lambda name: name)

    def failed_capture(command, **kwargs):
        Path(command[-1]).write_bytes(b"partial capture")
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(record_demo_live.subprocess, "run", failed_capture)
    directory = tmp_path / "failed-take"
    with pytest.raises(subprocess.CalledProcessError):
        record_demo_live.record_take(directory, 285, False)
    assert (directory / "raw.mov").read_bytes() == b"partial capture"
    assert json.loads((directory / "capture.json").read_text())["status"] == "capture_failed"
    assert not (directory / "showcase.mp4").exists()


def test_capture_refuses_a_git_destination_before_recording(tmp_path, monkeypatch):
    # Screen captures can contain private projects, even when Git ignores them.
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(["git", "init", "--quiet", str(repository)], check=True)
    monkeypatch.setattr(record_demo_live.shutil, "which", lambda name:
                        pytest.fail("Recorder reached capture preflight inside Git"))
    with pytest.raises(ValueError, match="outside Git"):
        record_demo_live.record_take(repository / ".runtime" / "take", 285, True)
    assert not (repository / ".runtime").exists()


def test_capture_refuses_an_existing_take_without_changing_its_raw_file(tmp_path):
    # Failed dry runs remain available when the operator starts another take.
    directory = tmp_path / "existing-take"
    directory.mkdir()
    raw = directory / "raw.mov"
    raw.write_bytes(b"earlier failed take")
    with pytest.raises(ValueError, match="new output directory"):
        record_demo_live.record_take(directory, 285, True)
    assert raw.read_bytes() == b"earlier failed take"


@pytest.mark.parametrize("seconds", [0, 301])
def test_capture_refuses_lengths_outside_the_five_minute_limit(tmp_path, seconds, monkeypatch):
    monkeypatch.setattr(record_demo_live.shutil, "which", lambda name:
                        pytest.fail("Recorder reached capture preflight with an invalid length"))
    with pytest.raises(ValueError, match="1 and 300"):
        record_demo_live.record_take(tmp_path / "take", seconds, False)
    assert not (tmp_path / "take").exists()


@pytest.mark.parametrize("duration", ["nan", "inf", "0", "300.01"])
def test_media_check_refuses_unmeasured_or_overlong_takes(tmp_path, monkeypatch, duration):
    # The limit applies to the saved movie, not merely the requested timer.
    metadata = {"format": {"duration": duration}, "streams": [
        {"codec_type": "video", "width": 320, "height": 180},
        {"codec_type": "audio", "channels": 1},
    ]}
    monkeypatch.setattr(record_demo_live.subprocess, "run", lambda *args, **kwargs:
                        subprocess.CompletedProcess(args[0], 0, json.dumps(metadata)))
    with pytest.raises(ValueError, match="duration"):
        record_demo_live.media_info(tmp_path / "take.mov", "ffprobe")


def test_legacy_recorder_uses_the_same_passive_entry_point():
    # The older filename must not revive its automatic plugin mutation sequence.
    assert record_demo_video.main is record_demo_live.main
