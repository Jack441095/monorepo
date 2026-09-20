from __future__ import annotations

import csv
import unittest
from pathlib import Path
from unittest.mock import patch

from audiogen_core.config import ConfigurationManager
from midi.midi_range_limiter import RANGE_LIMITER
from composition.analysis_feedback_adapter import feedback_adaptation_context, adapt_song_sections
from audio.render_to_wav import render_song_to_wav_file
from audio.auto_analyze import analyze_rendered_wav
from composition.song_rerank_model import append_audio_rerank_row
from composition.song_generator import SongGenerator, SongSectionSpec, SongRender

class Phase11ClosedLoopTests(unittest.TestCase):
    def test_feedback_adaptation_context_applies_and_restores(self):
        config = ConfigurationManager()
        # Save baseline values
        baseline_bass_min = RANGE_LIMITER.configs[0].min_note
        baseline_bass_max = RANGE_LIMITER.configs[0].max_note
        baseline_bass_vel_mult = getattr(config.composition, "bass_velocity_multiplier", 1.0)
        baseline_vel_curves_strength = config.composition.velocity_curves_strength
        baseline_melody_rest_prob_mult = config.composition.melody_rest_prob_mult
        baseline_melody_register_bias = config.composition.emotion_melody_register_bias_semitones
        baseline_counter_octave_offset = getattr(config.composition, "counter_melody_octave_offset", 0)

        # Test flag: "Heavy sub"
        with feedback_adaptation_context(config, ["Heavy sub"]):
            self.assertEqual(config.composition.bass_velocity_multiplier, 0.70)
            self.assertEqual(RANGE_LIMITER.configs[0].min_note, 24)
            self.assertEqual(RANGE_LIMITER.configs[0].max_note, 53)
        # Verify restore
        self.assertEqual(RANGE_LIMITER.configs[0].min_note, baseline_bass_min)
        self.assertEqual(RANGE_LIMITER.configs[0].max_note, baseline_bass_max)
        self.assertEqual(config.composition.bass_velocity_multiplier, baseline_bass_vel_mult)

        # Test flag: "Low dynamics"
        with feedback_adaptation_context(config, ["Low dynamics"]):
            self.assertEqual(config.composition.velocity_curves_strength, 0.85)
            self.assertEqual(config.composition.melody_rest_prob_mult, 1.35)
        # Verify restore
        self.assertEqual(config.composition.velocity_curves_strength, baseline_vel_curves_strength)
        self.assertEqual(config.composition.melody_rest_prob_mult, baseline_melody_rest_prob_mult)

        # Test flag: "Low presence"
        with feedback_adaptation_context(config, ["Low presence"]):
            self.assertEqual(config.composition.emotion_melody_register_bias_semitones, 12)
        # Verify restore
        self.assertEqual(config.composition.emotion_melody_register_bias_semitones, baseline_melody_register_bias)

        # Test flag: "Frequency masking"
        with feedback_adaptation_context(config, ["Frequency masking"]):
            self.assertEqual(config.composition.counter_melody_octave_offset, -12)
        # Verify restore
        self.assertEqual(config.composition.counter_melody_octave_offset, baseline_counter_octave_offset)

    def test_adapt_song_sections(self):
        sections = [
            SongSectionSpec("joy", bars=4, root_note=60, target_notes_per_bar=2.0),
            SongSectionSpec("sadness", bars=4, root_note=60, target_notes_per_bar=3.0)
        ]
        
        # Low presence flag -> boost target notes per bar by 1.3
        adapted = adapt_song_sections(sections, ["Low presence"])
        self.assertEqual(len(adapted), 2)
        self.assertAlmostEqual(adapted[0].target_notes_per_bar, 2.6)
        self.assertAlmostEqual(adapted[1].target_notes_per_bar, 3.9)

        # Other unrelated flag -> no change
        adapted_no_change = adapt_song_sections(sections, ["Heavy sub"])
        self.assertEqual(len(adapted_no_change), 2)
        self.assertEqual(adapted_no_change[0].target_notes_per_bar, 2.0)
        self.assertEqual(adapted_no_change[1].target_notes_per_bar, 3.0)

    @patch("audio.render_to_wav.write_full_song_outputs")
    def test_render_song_to_wav_file(self, mock_write):
        # Setup mock return value
        mock_write.return_value = {"wav": "/fake/path/song.wav"}
        
        # We need to make sure the code thinks the file exists if it checks Path.exists()
        with patch.object(Path, "exists", return_value=True):
            song_render = SongRender(sections=[], events=[], tempo_map=[], metadata={})
            path = render_song_to_wav_file(song_render, export_dir=Path("/fake/export"), name_prefix="test_prefix")
            self.assertEqual(path, Path("/fake/path/song.wav"))
            mock_write.assert_called_once()

    @patch("audio.auto_analyze.save_review")
    def test_analyze_rendered_wav(self, mock_save_review):
        mock_save_review.return_value = {
            "ok": True,
            "review": {"title": "Test Track", "flags": [{"label": "Low dynamics"}]}
        }
        
        with patch.object(Path, "read_bytes", return_value=b"fake_bytes"):
            res = analyze_rendered_wav(Path("/fake/song.wav"), mix_goal="club")
            self.assertEqual(res["title"], "Test Track")
            self.assertEqual(res["flags"][0]["label"], "Low dynamics")
            mock_save_review.assert_called_once_with(
                file_bytes=b"fake_bytes",
                filename="song.wav",
                title="song",
                mix_goal="club",
                background=False
            )

    def test_append_audio_rerank_row(self):
        import tempfile
        import os
        
        fd, temp_csv = tempfile.mkstemp(suffix=".csv")
        os.close(fd)
        try:
            # Create a mock SongRender with candidate metrics metadata
            song_render = SongRender(sections=[], events=[], tempo_map=[], metadata={
                "candidate_metrics": {
                    "in_key_primary_ratio": 0.95,
                    "lead_activity": 0.4,
                    "emotion_match_score": 95.0,
                }
            })
            
            audio_metrics = {
                "technical_score": 82.5,
                "crest_factor_db": 12.0,
                "stereo_width_ratio": 0.65,
                "integrated_lufs": -14.2
            }
            
            append_audio_rerank_row(song_render, audio_metrics, csv_path=temp_csv)
            
            # Read CSV and verify
            with open(temp_csv, "r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                
            self.assertEqual(len(rows), 1)
            row = rows[0]
            self.assertEqual(float(row["in_key_primary_ratio"]), 0.95)
            self.assertEqual(float(row["lead_activity"]), 0.4)
            self.assertEqual(float(row["emotion_match_score"]), 95.0)
            self.assertEqual(float(row["spectral_balance_score"]), 82.5)
            self.assertEqual(float(row["crest_factor"]), 12.0)
            self.assertEqual(float(row["stereo_width"]), 0.65)
            self.assertEqual(float(row["perceived_loudness_distribution"]), -14.2)
            self.assertEqual(float(row["target_quality_score"]), 82.5)
        finally:
            if os.path.exists(temp_csv):
                os.remove(temp_csv)

    @patch("audio.render_to_wav.render_song_to_wav_file")
    @patch("audio.auto_analyze.analyze_rendered_wav")
    @patch("composition.song_rerank_model.append_audio_rerank_row")
    def test_generate_song_best_of_k_closed_loop_no_flags(
        self, mock_append, mock_analyze, mock_render
    ):
        mock_render.return_value = Path("tmp/cl_temp_song.wav")
        mock_analyze.return_value = {
            "flags": [],
            "metrics": {"technical_score": 90.0, "crest_factor_db": 10.0}
        }
        
        sg = SongGenerator()
        sections = [SongSectionSpec("neutral", bars=2, root_note=60)]
        
        # Call generate_song_best_of_k with closed_loop=True, k=1
        song = sg.generate_song_best_of_k(
            sections,
            arrangement_form="default",
            seed=42,
            k=1,
            closed_loop=True,
            mix_goal="club"
        )
        
        self.assertIsNotNone(song)
        self.assertFalse(song.metadata.get("closed_loop_regenerated"))
        mock_render.assert_called_once()
        mock_analyze.assert_called_once()
        mock_append.assert_called_once()

    @patch("audio.render_to_wav.render_song_to_wav_file")
    @patch("audio.auto_analyze.analyze_rendered_wav")
    @patch("composition.song_rerank_model.append_audio_rerank_row")
    def test_generate_song_best_of_k_closed_loop_with_flags_triggering_regen(
        self, mock_append, mock_analyze, mock_render
    ):
        mock_render.return_value = Path("tmp/cl_temp_song.wav")
        # First call has "Low dynamics" flag, second call (after regen) has no flags
        mock_analyze.side_effect = [
            {
                "flags": [{"label": "Low dynamics"}],
                "metrics": {"technical_score": 75.0, "crest_factor_db": 6.0}
            },
            {
                "flags": [],
                "metrics": {"technical_score": 85.0, "crest_factor_db": 10.0}
            }
        ]
        
        sg = SongGenerator()
        sections = [SongSectionSpec("neutral", bars=2, root_note=60)]
        
        song = sg.generate_song_best_of_k(
            sections,
            arrangement_form="default",
            seed=42,
            k=1,
            closed_loop=True,
            mix_goal="club"
        )
        
        self.assertIsNotNone(song)
        self.assertTrue(song.metadata.get("closed_loop_regenerated"))
        self.assertEqual(song.metadata.get("closed_loop_flags_before"), ["Low dynamics"])
        self.assertEqual(song.metadata.get("closed_loop_flags_after"), [])
        self.assertEqual(mock_render.call_count, 2)
        self.assertEqual(mock_analyze.call_count, 2)
        mock_append.assert_called_once()
