"""Demucs v4 stem separation core.

Wraps Meta's Demucs (htdemucs, the default 4-stem model) behind a single
``separate()`` call: mixed stereo WAV in, {drums, bass, vocals, other} WAV
files out. This module assumes torch + demucs are installed -- it only ever
runs inside this package's own isolated venv (see scripts/setup_venv.sh),
never the shared project environment, which deliberately excludes torch (see
this package's pyproject.toml for why).
"""

from __future__ import annotations

from pathlib import Path

STEM_NAMES = ("drums", "bass", "vocals", "other")


def resolve_device(requested: str | None = None) -> str:
    """CUDA -> MPS -> CPU fallback, mirroring the device-selection pattern
    already used for KENN's LoRA fine-tune
    (studio/kenn/kenn/finetune/finetune_lora.py) -- this repo runs no cloud
    GPU (native macOS deploy via launchd), so in practice this resolves to
    MPS on Apple Silicon or CPU otherwise."""
    if requested:
        return requested
    import torch

    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def separate(
    input_path: str | Path,
    output_dir: str | Path,
    *,
    model_name: str = "htdemucs",
    device: str | None = None,
) -> dict[str, str]:
    """Separate a mixed stereo track into drums/bass/vocals/other stems.

    Returns a dict mapping each stem name to its written WAV path. Raises on
    failure -- the CLI entry point (main_separate.py) is responsible for
    catching and reporting errors as JSON.
    """
    import numpy as np
    import soundfile as sf
    import torch
    import torchaudio
    from demucs.apply import apply_model
    from demucs.pretrained import get_model

    input_path = Path(input_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    resolved_device = resolve_device(device)
    model = get_model(model_name)
    model.eval()
    model.to(resolved_device)

    # soundfile, not torchaudio.load: recent torchaudio moved its default
    # file-I/O backend to a separate `torchcodec` package this module
    # doesn't depend on (see pyproject.toml's note) -- torchaudio.functional
    # below is a pure tensor op and doesn't need it.
    samples, sr = sf.read(str(input_path), dtype="float32", always_2d=True)  # (n_samples, n_channels)
    wav = torch.from_numpy(np.ascontiguousarray(samples.T))  # (n_channels, n_samples)
    if wav.shape[0] == 1:
        wav = wav.repeat(2, 1)  # Demucs expects stereo input
    elif wav.shape[0] > 2:
        wav = wav[:2]

    if sr != model.samplerate:
        wav = torchaudio.functional.resample(wav, sr, model.samplerate)
        sr = model.samplerate

    # Demucs' own reference separation script normalizes by the mono mix's
    # mean/std before inference and denormalizes after -- keeps the model
    # operating in the amplitude range it was trained on regardless of the
    # input file's own loudness.
    ref = wav.mean(0)
    normalized = (wav - ref.mean()) / ref.std()
    with torch.no_grad():
        sources = apply_model(model, normalized[None], device=resolved_device, progress=False)[0]
    sources = sources * ref.std() + ref.mean()

    stem_paths: dict[str, str] = {}
    for name, source in zip(model.sources, sources):
        if name not in STEM_NAMES:
            continue  # e.g. a 6-stem model's extra guitar/piano sources
        out_path = output_dir / f"{name}.wav"
        sf.write(str(out_path), source.cpu().numpy().T, sr)
        stem_paths[name] = str(out_path)
    return stem_paths
