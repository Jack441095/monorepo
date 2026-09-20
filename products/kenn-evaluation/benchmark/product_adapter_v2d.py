"""Read-only product-pipeline adapter used to prove V2-D integration parity."""
from __future__ import annotations
import io, sys, wave
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[1]; PRODUCT=ROOT.parent/'Audio_Too'
sys.path[:0]=[str(PRODUCT),str(PRODUCT/'business'/'app'),str(PRODUCT/'business'/'agents'),str(PRODUCT/'studio'/'audio_analysis')]
from audio_analysis.utils.audio_io_api import decode_audio_bytes  # real product decoder
from measured_candidates_v2c import clipping_candidate, headroom_candidate, lr_imbalance_candidate

def product_candidates(wav_bytes: bytes, *, scope: str) -> tuple[list, dict]:
    """Product decode seam plus the frozen V2-C measurement semantics."""
    decoded=decode_audio_bytes(wav_bytes,'fixture.wav')
    with wave.open(io.BytesIO(decoded['wav_bytes']),'rb') as w:
        frames=w.readframes(w.getnframes()); sr=w.getframerate(); channels=w.getnchannels()
    if channels not in (1,2): raise ValueError(f'unsupported channel count: {channels}')
    pcm=np.frombuffer(frames,dtype='<i2').astype(np.float64)
    audio=pcm.reshape(-1,channels)/32767.
    if channels==1: audio=np.repeat(audio,2,axis=1)
    return [clipping_candidate(audio,scope),headroom_candidate(audio,scope),lr_imbalance_candidate(audio,sr,scope)], decoded
