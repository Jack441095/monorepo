from __future__ import annotations

from pathlib import Path
from audiogen_core.config import CONFIG
from tools.full_song_render import write_full_song_outputs

def render_song_to_wav_file(song_render, export_dir: Path, name_prefix: str = "song_render") -> Path:
    """Render a SongRender object's MIDI events to a WAV file using the sampler synthesis engine."""
    total_bars = int(sum(int(s.bars) for s in song_render.sections)) if song_render.sections else 0
    res = write_full_song_outputs(
        config=CONFIG,
        song_events=list(song_render.events or []),
        total_bars=total_bars,
        song_render=song_render,
        export_dir=export_dir,
        name_prefix=name_prefix,
        write_wav=True,
        write_midi=False,
        write_report=False,
    )
    wav_path = res.get("wav")
    if not wav_path or not Path(wav_path).exists():
        raise RuntimeError("Failed to render song to WAV file")
    return Path(wav_path)
