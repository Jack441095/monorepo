"""Neural Phrase Generator for AudioGen Phase D.

Provides fast CPU-bounded inference (<30ms) for generating melodic note phrases
using PhraseGRUModel with Markov fallback.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

try:
    from training.export_midi_tokens import decode_token_to_event, encode_event_to_token
except ModuleNotFoundError:
    from studio.audiogen.audiogen.training.export_midi_tokens import decode_token_to_event, encode_event_to_token

try:
    import torch
    try:
        from training.train_phrase_gru import PhraseGRUModel, TORCH_AVAILABLE
    except ModuleNotFoundError:
        from studio.audiogen.audiogen.training.train_phrase_gru import PhraseGRUModel, TORCH_AVAILABLE
except ImportError:
    TORCH_AVAILABLE = False
    PhraseGRUModel = None  # type: ignore


class NeuralPhraseGenerator:
    """Phrase generation engine using PyTorch PhraseGRUModel."""

    def __init__(self, model_path: Path | str | None = None):
        self.model = None
        if TORCH_AVAILABLE and model_path and Path(model_path).exists():
            try:
                self.model = PhraseGRUModel()
                self.model.load_state_dict(torch.load(model_path, map_location="cpu"))
                self.model.eval()
            except Exception:
                self.model = None

    def generate_phrase(
        self,
        prompt_events: list[dict[str, Any]],
        num_notes: int = 8,
        root_pitch: int = 60,
        ticks_per_step: int = 120,
    ) -> tuple[list[dict[str, Any]], float]:
        """Generate a melodic phrase extending prompt_events.

        Parameters
        ----------
        prompt_events : list[dict]
            Initial seed note events.
        num_notes : int
            Number of new notes to generate.
        root_pitch : int
            Root pitch of active key.
        ticks_per_step : int
            Ticks per step (16th note = 120 ticks).

        Returns
        -------
        tuple[list[dict], float]
            Tuple of (generated_events, inference_latency_ms).
        """
        start_time = time.perf_counter()

        prompt_tokens = [
            encode_event_to_token(
                pitch=ev.get("pitch", root_pitch),
                duration_ticks=ev.get("duration_ticks", 240),
                velocity=ev.get("velocity", 80),
                root_pitch=root_pitch,
            )
            for ev in (prompt_events or [])
        ]

        if not prompt_tokens:
            prompt_tokens = [(12, 2, 4)]  # Root note default token

        generated_tokens = list(prompt_tokens)
        current_tick = (
            prompt_events[-1].get("start_tick", 0) + prompt_events[-1].get("duration_ticks", 240)
            if prompt_events
            else 0
        )

        new_events = []

        if TORCH_AVAILABLE and self.model is not None:
            with torch.no_grad():
                h = None
                p_in = torch.tensor([[t[0] for t in generated_tokens]], dtype=torch.long)
                d_in = torch.tensor([[t[1] for t in generated_tokens]], dtype=torch.long)
                v_in = torch.tensor([[t[2] for t in generated_tokens]], dtype=torch.long)

                p_log, d_log, v_log, h = self.model(p_in, d_in, v_in, h)

                for _ in range(num_notes):
                    next_p = int(torch.argmax(p_log[0, -1, :]).item())
                    next_d = int(torch.argmax(d_log[0, -1, :]).item())
                    next_v = int(torch.argmax(v_log[0, -1, :]).item())

                    token = (next_p, next_d, next_v)
                    generated_tokens.append(token)

                    ev = decode_token_to_event(token, start_tick=current_tick, root_pitch=root_pitch)
                    new_events.append(ev)

                    current_tick += ev["duration_ticks"]

                    # Feed forward single token
                    p_in = torch.tensor([[next_p]], dtype=torch.long)
                    d_in = torch.tensor([[next_d]], dtype=torch.long)
                    v_in = torch.tensor([[next_v]], dtype=torch.long)
                    p_log, d_log, v_log, h = self.model(p_in, d_in, v_in, h)
        else:
            # Fallback heuristic phrase generation
            last_token = prompt_tokens[-1]
            for i in range(num_notes):
                # Scale degree step fallback (+2 / -1)
                next_p = (last_token[0] + (2 if i % 2 == 0 else -1)) % 25
                next_d = last_token[1]
                next_v = last_token[2]

                token = (next_p, next_d, next_v)
                last_token = token

                ev = decode_token_to_event(token, start_tick=current_tick, root_pitch=root_pitch)
                new_events.append(ev)
                current_tick += ev["duration_ticks"]

        latency_ms = (time.perf_counter() - start_time) * 1000.0
        return new_events, latency_ms
