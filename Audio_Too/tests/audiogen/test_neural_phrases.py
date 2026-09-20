import unittest
import torch
from pathlib import Path
from types import SimpleNamespace
from ai.markov.melody.note_generator._core import NoteGenerator, HAS_TORCH, PhraseGRU

class NeuralPhrasesTests(unittest.TestCase):
    def test_pytorch_available(self):
        self.assertTrue(HAS_TORCH, "PyTorch must be available in this environment.")

    def test_phrase_gru_forward(self):
        if not HAS_TORCH:
            self.skipTest("PyTorch not available")
            
        model = PhraseGRU(num_emotions=2, pitch_emb_dim=8, dur_emb_dim=8, emotion_emb_dim=4, hidden_size=16, num_layers=1)
        
        # [batch_size=2, seq_len=16]
        x_pitch = torch.zeros((2, 16), dtype=torch.long)
        x_dur = torch.ones((2, 16), dtype=torch.long) * 4
        emotion_idx = torch.tensor([0, 1], dtype=torch.long)
        
        pitch_logits, dur_logits = model(x_pitch, x_dur, emotion_idx)
        
        # Verify output shapes
        self.assertEqual(pitch_logits.shape, (2, 13))
        self.assertEqual(dur_logits.shape, (2, 65))

    def test_note_generator_load_and_neural_fallback(self):
        markov_models = SimpleNamespace(
            interval=SimpleNamespace(order=1),
            rhythm=SimpleNamespace(order=1)
        )
        gen = NoteGenerator(markov_models, None, None)
        
        has_loaded = gen._load_neural_model()
        
        root_dir = Path(__file__).resolve().parents[2] / "studio" / "audiogen" / "audiogen"
        model_path = root_dir / "training_data" / "active_models" / "phrase_gru.pt"
        
        if model_path.exists():
            self.assertTrue(has_loaded)
            self.assertIsNotNone(gen._neural_model)
            self.assertGreater(len(gen._neural_emotions), 0)
        else:
            self.assertFalse(has_loaded)
            self.assertIsNone(gen._neural_model)

    def test_generate_phrase_neural_output_types(self):
        markov_models = SimpleNamespace(
            interval=SimpleNamespace(order=1),
            rhythm=SimpleNamespace(order=1)
        )
        gen = NoteGenerator(markov_models, None, None)
        
        if not HAS_TORCH:
            self.skipTest("PyTorch not available")
            
        class MockModel(torch.nn.Module):
            def forward(self, x_pitch, x_dur, emotion_idx):
                # Returns high probability for pitch 2 and duration 4 (1 beat)
                p_logits = torch.zeros((1, 13))
                p_logits[0, 2] = 100.0
                d_logits = torch.zeros((1, 65))
                d_logits[0, 4] = 100.0
                return p_logits, d_logits
                
        gen._neural_model = MockModel()
        gen._neural_emotions = ["joy"]
        gen._emotion_to_idx = {"joy": 0}
        
        emotion = SimpleNamespace(name="joy", scale_intervals=[0, 2, 4, 5, 7, 9, 11])
        melody, intervals, rhythms = gen._generate_phrase_neural(
            start_degree=0,
            num_notes=4,
            plan=SimpleNamespace(contour="static"),
            temperature=1.0,
            emotion=emotion,
            start_beat=0.0,
            chords=["I"],
            roots=[60],
            beats_per_bar=4.0,
            chord_weights_per_bar=None,
            beat_positions_out=[],
            grid=0.25,
            initial_interval_context=None,
            initial_rhythm_context=None,
            bass_notes=None,
            total_beats=16.0,
            target_melody_notes=None
        )
        
        # Verify note generation
        self.assertEqual(len(melody), 4)
        for deg, dur in melody:
            # We mocked pitch to delta 2. Scale index closest to delta 2 in [0, 2, 4, 5, 7, 9, 11] is degree index 1 (value 2)
            self.assertEqual(deg, 1)
            self.assertEqual(dur, 1.0)

if __name__ == "__main__":
    unittest.main()
