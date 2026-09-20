"""Unit tests for Mix Review Lab's memory-efficient chunked parsing and anti-aliased downsampling."""

from __future__ import annotations

import io
import math
import struct
import sys
import wave
from pathlib import Path

# Add Website directory to path
BUSINESS_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BUSINESS_ROOT / "server" / "app"))
sys.path.insert(0, str(BUSINESS_ROOT / "studio" / "audio_analysis"))

from audio_analysis.mix_review import mix_review


def test_consecutive_clipping_logic() -> None:
    # Generate custom frames:
    # 1. 200 normal samples (amplitude 0.5)
    # 2. 1 isolated peak at 0.999 (should NOT trigger flatline count)
    # 3. 200 normal samples (amplitude 0.5)
    # 4. 4 consecutive peaks at 0.999 (should trigger EXACTLY 1 flatline count)
    # 5. 200 normal samples (amplitude 0.5)
    
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(44100)
        
        frames = []
        
        # 1. Normal samples
        for _ in range(200):
            frames.append(struct.pack("<h", int(0.5 * 32767)))
            
        # 2. Isolated peak
        frames.append(struct.pack("<h", 32767))
        
        # 3. Normal samples
        for _ in range(200):
            frames.append(struct.pack("<h", int(0.5 * 32767)))
            
        # 4. 4 consecutive flatlined samples
        for _ in range(4):
            frames.append(struct.pack("<h", 32767))
            
        # 5. Normal samples
        for _ in range(200):
            frames.append(struct.pack("<h", int(0.5 * 32767)))
            
        wav.writeframes(b"".join(frames))
        
    wav_bytes = buffer.getvalue()
    
    # Analyze with max_samples set large enough so step is 1 (no downsampling)
    data = mix_review.read_wav_mono(wav_bytes, max_samples=1000)
    
    # Assert clipping logic
    # Single isolated peak should not count, but the 4 consecutive ones should count as exactly 1 clipped event.
    assert data["clipped_frames_estimate"] == 1


def test_anti_aliased_downsampling() -> None:
    # Generate a high-frequency tone near Nyquist (e.g. 20,000 Hz at 44100 Hz sample rate)
    # Under downsampling by 16 (Nyquist becomes 1378 Hz), without filtering this tone would alias
    # and show high amplitude in the downsampled array.
    # With the low-pass filter, it should be heavily attenuated.
    
    fs = 44100
    freq = 20000.0
    seconds = 0.5
    
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(fs)
        frames = []
        for index in range(int(seconds * fs)):
            val = int(0.9 * 32767 * math.sin(2.0 * math.pi * freq * index / fs))
            frames.append(struct.pack("<hh", val, val))
        wav.writeframes(b"".join(frames))
        
    wav_bytes = buffer.getvalue()
    
    # We want max_samples to force downsampling step = 16
    # 0.5 seconds at 44100 is 22050 frames. Setting max_samples = 1378 yields step = 16.
    data = mix_review.read_wav_mono(wav_bytes, max_samples=1378)
    
    # Verify downsampled step size
    # Check that the anti-aliasing filter has attenuated the 20 kHz tone in the downsampled samples
    # Without filter, peak would be near 0.9. With filter, it should be heavily attenuated (< 0.25)
    assert max(abs(s) for s in data["samples"]) < 0.25



def test_chunked_parsing_correctness() -> None:
    # Generate a simple 1 kHz sine wave
    fs = 44100
    freq = 1000.0
    seconds = 1.0
    
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(fs)
        frames = []
        for index in range(int(seconds * fs)):
            val = int(0.6 * 32767 * math.sin(2.0 * math.pi * freq * index / fs))
            frames.append(struct.pack("<hh", val, val))
        wav.writeframes(b"".join(frames))
        
    wav_bytes = buffer.getvalue()
    
    # Verify chunked read mono returns correct sample rate, duration, and channels
    data = mix_review.read_wav_mono(wav_bytes, max_samples=65536)
    
    assert data["channels"] == 2
    assert data["sample_rate"] == 44100
    assert abs(data["duration_seconds"] - 1.0) < 0.05
    assert abs(data["peak"] - 0.6) < 0.05


def test_sibilance_band_and_accurate_peaks() -> None:
    # Generate a WAV file with:
    # 1. A peak sample at amplitude 0.8
    # 2. A 7 kHz tone (sibilance frequency) at amplitude 0.4
    fs = 44100
    freq = 7000.0
    seconds = 0.5
    
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(fs)
        frames = []
        
        # Single isolated sample peak at 0.8
        frames.append(struct.pack("<h", int(0.8 * 32767)))
        
        # Sibilance tone
        for index in range(1, int(seconds * fs)):
            val = int(0.4 * 32767 * math.sin(2.0 * math.pi * freq * index / fs))
            frames.append(struct.pack("<h", val))
        wav.writeframes(b"".join(frames))
        
    wav_bytes = buffer.getvalue()
    
    # Analyze the WAV.
    report = mix_review.analyze_wav(wav_bytes, "sibilance-peak-test.wav")
    
    # Assert peak is captured correctly on full-resolution
    assert abs(report["metrics"]["peak_dbfs"] - 20 * math.log10(0.8)) < 0.2
    
    # Assert sibilance band is present and has a share
    assert "sibilance" in report["metrics"]["bands"]
    assert report["metrics"]["bands"]["sibilance"] > 0.0


def test_chord_and_key_detection() -> None:
    # 1. Test clean C Major and A Minor chord synthesis
    fs = 44100
    seconds = 2.0
    
    c_freqs = [261.63, 329.63, 392.00]
    a_freqs = [220.00, 261.63, 329.63]
    
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(fs)
        
        frames = []
        # Synthesize C Major chord
        for index in range(int(seconds * fs)):
            val = sum(0.25 * math.sin(2.0 * math.pi * f * index / fs) for f in c_freqs)
            val_int = int(max(-1.0, min(1.0, val)) * 32767)
            frames.append(struct.pack("<h", val_int))
            
        # Synthesize A Minor chord
        for index in range(int(seconds * fs)):
            val = sum(0.25 * math.sin(2.0 * math.pi * f * index / fs) for f in a_freqs)
            val_int = int(max(-1.0, min(1.0, val)) * 32767)
            frames.append(struct.pack("<h", val_int))
            
        wav.writeframes(b"".join(frames))
        
    wav_bytes = buffer.getvalue()
    
    # Analyze the WAV.
    report = mix_review.analyze_wav(wav_bytes, "chords-key-test.wav")
    
    metrics = report["metrics"]
    assert "chords" in metrics
    chords_data = metrics["chords"]
    
    # Assert estimated key exists and is non-empty
    assert chords_data["estimated_key"] != "Unknown"
    assert "Major" in chords_data["estimated_key"] or "Minor" in chords_data["estimated_key"]
    
    # Verify the progression timeline contains C Maj and A Min
    detected_chords = [seg["chord"] for seg in chords_data["progression"] if seg["chord"] != "N.C."]
    assert len(detected_chords) > 0
    assert "C Maj" in detected_chords
    assert "A Min" in detected_chords
    
    # Verify interval mapping
    intervals = chords_data["intervals"]
    assert len(intervals) >= 1
    c_to_a_iv = next((iv for iv in intervals if iv["from_chord"] == "C Maj" and iv["to_chord"] == "A Min"), None)
    if c_to_a_iv:
        assert c_to_a_iv["interval"] == "Major 6th"
        assert c_to_a_iv["semitones"] == 9


