"""Unit tests for Phase D Neural Phrase Pipeline in AudioGen."""

from __future__ import annotations


try:
    from training.export_midi_tokens import (
        encode_event_to_token,
        decode_token_to_event,
        export_events_to_tokens_dataset,
    )
    from training.train_phrase_gru import train_phrase_gru_model
except ModuleNotFoundError:
    from studio.audiogen.audiogen.training.export_midi_tokens import (
        encode_event_to_token,
        decode_token_to_event,
        export_events_to_tokens_dataset,
    )
    from studio.audiogen.audiogen.training.train_phrase_gru import train_phrase_gru_model

from composition.neural_phrase_generator import NeuralPhraseGenerator


def test_token_encode_decode():
    # C4 = 60
    token = encode_event_to_token(pitch=60, duration_ticks=240, velocity=80, root_pitch=60)
    assert token[0] == 12  # 0 delta + 12 offset

    event = decode_token_to_event(token, start_tick=0, root_pitch=60)
    assert event["pitch"] == 60
    assert event["duration_ticks"] == 240
    assert event["velocity"] == 80


def test_export_dataset_and_training(tmp_path):
    phrase1 = [
        {"pitch": 60, "duration_ticks": 240, "velocity": 80},
        {"pitch": 62, "duration_ticks": 240, "velocity": 84},
        {"pitch": 64, "duration_ticks": 480, "velocity": 90},
    ]
    dataset_path = tmp_path / "tokens.jsonl"
    export_events_to_tokens_dataset([phrase1], dataset_path, root_pitch=60)
    assert dataset_path.exists()

    model_path = tmp_path / "phrase_gru.pt"
    saved_path = train_phrase_gru_model(dataset_path, model_path, epochs=2)
    assert saved_path.exists()


def test_neural_phrase_generator_latency_and_output():
    generator = NeuralPhraseGenerator()
    prompt = [
        {"pitch": 60, "start_tick": 0, "duration_ticks": 240, "velocity": 80},
        {"pitch": 62, "start_tick": 240, "duration_ticks": 240, "velocity": 84},
    ]

    events, latency_ms = generator.generate_phrase(prompt, num_notes=6, root_pitch=60)
    assert len(events) == 6
    assert "pitch" in events[0]
    assert "start_tick" in events[0]

    # Realtime performance target: CPU latency < 30ms per phrase
    assert latency_ms < 30.0
