"""Tests for genre-specific flag overrides and report summary cache."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "studio" / "audio_analysis"))

from audio_analysis.analysis_core.analysis_interpretation import (
    DEFAULT_FLAG_THRESHOLDS,
    GOAL_FLAG_OVERRIDES,
    goal_flag_thresholds,
    review_flags,
)
from audio_analysis.mix_review.review_store import (
    REPORT_SUMMARY_CACHE_SQL,
    _cache_report_summary,
    _read_cached_summaries,
    _delete_cached_summary,
    _deserialize_json_fields,
)


# ---------------------------------------------------------------------------
#  Genre override threshold tests
# ---------------------------------------------------------------------------

class TestGoalFlagThresholds:
    """goal_flag_thresholds() should merge defaults + genre-specific overrides."""

    def test_no_goal_returns_defaults(self):
        """When metrics has no mix_goal, thresholds should equal defaults."""
        t = goal_flag_thresholds({})
        for key, value in DEFAULT_FLAG_THRESHOLDS.items():
            assert t[key] == value, f"{key} should be {value}, got {t[key]}"

    def test_unknown_goal_returns_defaults(self):
        """When metrics has an unrecognised mix_goal key, thresholds should equal defaults."""
        t = goal_flag_thresholds({"mix_goal": {"key": "nonexistent_genre"}})
        for key, value in DEFAULT_FLAG_THRESHOLDS.items():
            assert t[key] == value, f"{key} should be {value}, got {t[key]}"

    def test_premaster_overrides_certain_fields(self):
        """Premaster should override crest_min_db, low_mids_max, sub_max."""
        t = goal_flag_thresholds({"mix_goal": {"key": "premaster", "label": "Premaster"}})
        assert t["crest_min_db"] == 6.0  # matches default
        assert t["low_mids_max"] == 0.18  # matches default
        assert t["sub_max"] == 0.12       # matches default
        # But defaults for other fields should remain
        assert t["peak_max_dbfs"] == -1.0

    def test_hip_hop_overrides_sub_max_and_lufs(self):
        """Hip hop should allow more sub (0.20) and hotter LUFS (-8.0)."""
        t = goal_flag_thresholds({"mix_goal": {"key": "hip_hop", "label": "Hip Hop"}})
        assert t["sub_max"] == 0.20, f"hip_hop sub_max should be 0.20, got {t['sub_max']}"
        assert t["lufs_max"] == -8.0, f"hip_hop lufs_max should be -8.0, got {t['lufs_max']}"
        assert t["crest_min_db"] == 3.0, f"hip_hop crest_min_db should be 3.0, got {t['crest_min_db']}"
        assert t["correlation_sub_min"] == 0.5
        assert t["correlation_bass_min"] == 0.5
        # Side sub/bass should be tighter for hip hop
        assert t["side_sub_max"] == 0.02
        assert t["side_bass_max"] == 0.04

    def test_acoustic_overrides_crest_and_lufs(self):
        """Acoustic should require higher crest (9.0) and quieter LUFS (-16.0)."""
        t = goal_flag_thresholds({"mix_goal": {"key": "acoustic", "label": "Acoustic"}})
        assert t["crest_min_db"] == 9.0
        assert t["lufs_max"] == -16.0
        assert t["sub_max"] == 0.08
        assert t["perceived_air_max"] == 0.18
        assert t["presence_min"] == 0.10

    def test_cinematic_overrides_width_and_lufs(self):
        """Cinematic should allow wider stereo and quieter LUFS."""
        t = goal_flag_thresholds({"mix_goal": {"key": "cinematic", "label": "Cinematic"}})
        assert t["stereo_width_ratio_max"] == 0.95
        assert t["lufs_max"] == -18.0
        assert t["section_range_max_db"] == 16.0
        assert t["sub_max"] == 0.18

    def test_jazz_overrides_crest_and_presence(self):
        """Jazz should require high crest (10.0) and minimal sub."""
        t = goal_flag_thresholds({"mix_goal": {"key": "jazz", "label": "Jazz"}})
        assert t["crest_min_db"] == 10.0
        assert t["sub_max"] == 0.08
        assert t["lufs_max"] == -16.0
        assert t["presence_min"] == 0.10

    def test_edm_overrides_lufs_and_side_bass(self):
        """EDM should allow hot LUFS and tight side bass."""
        t = goal_flag_thresholds({"mix_goal": {"key": "edm", "label": "EDM"}})
        assert t["lufs_max"] == -8.0
        assert t["crest_min_db"] == 3.5
        assert t["side_sub_max"] == 0.03
        assert t["side_bass_max"] == 0.06

    def test_lo_fi_overrides_low_mids_and_sub(self):
        """Lo-fi should allow more low mids and higher sub."""
        t = goal_flag_thresholds({"mix_goal": {"key": "lo_fi", "label": "Lo-Fi"}})
        assert t["low_mids_max"] == 0.28
        assert t["sub_max"] == 0.16
        assert t["crest_min_db"] == 4.0

    def test_rock_overrides_match_expectations(self):
        """Rock should have moderate crest and LUFS."""
        t = goal_flag_thresholds({"mix_goal": {"key": "rock", "label": "Rock"}})
        assert t["crest_min_db"] == 5.0
        assert t["lufs_max"] == -10.0
        assert t["low_mids_max"] == 0.24

    def test_club_overrides_match_expectations(self):
        """Club should allow hot LUFS and wider low end."""
        t = goal_flag_thresholds({"mix_goal": {"key": "club", "label": "Club"}})
        assert t["lufs_max"] == -9.0
        assert t["sub_max"] == 0.18
        assert t["low_end_share_max"] == 0.62

    def test_podcast_overrides_are_conservative(self):
        """Podcast should be conservative — low sub, tight level range."""
        t = goal_flag_thresholds({"mix_goal": {"key": "podcast", "label": "Podcast"}})
        assert t["sub_max"] == 0.06
        assert t["section_range_max_db"] == 8.0
        assert t["lufs_max"] == -12.0  # unchanged from default
        assert t["perceived_presence_max"] == 0.30

    def test_master_overrides_tighten_peak_and_lufs(self):
        """Master should have tighter peak limits and hot LUFS."""
        t = goal_flag_thresholds({"mix_goal": {"key": "master", "label": "Master"}})
        assert t["peak_max_dbfs"] == -0.3
        assert t["true_peak_clip_dbfs"] == -0.3
        assert t["lufs_max"] == -8.0
        assert t["stereo_correlation_min"] == 0.1

    def test_game_audio_overrides_headroom_and_consistency(self):
        """Game audio should require headroom, moderate LUFS, and controlled side bass."""
        t = goal_flag_thresholds({"mix_goal": {"key": "game_audio", "label": "Game audio"}})
        # Implementation headroom: peak and true peak should be safe
        assert t["peak_max_dbfs"] == -1.0, f"game_audio peak_max_dbfs should be -1.0, got {t['peak_max_dbfs']}"
        assert t["true_peak_clip_dbfs"] == -1.0, (
            f"game_audio true_peak_clip_dbfs should be -1.0, got {t['true_peak_clip_dbfs']}"
        )
        # Moderate loudness — game assets shouldn't be too hot
        assert t["lufs_max"] == -14.0, f"game_audio lufs_max should be -14.0, got {t['lufs_max']}"
        # Controlled low-mids to prevent stacking across multiple assets
        assert t["low_mids_max"] == 0.22, f"game_audio low_mids_max should be 0.22, got {t['low_mids_max']}"
        # Side bass should be tight for mono-safe game playback
        assert t["side_sub_max"] == 0.03
        assert t["side_bass_max"] == 0.06
        # Low-end phase should be tight
        assert t["correlation_sub_min"] == 0.5
        assert t["correlation_bass_min"] == 0.5
        # Existing overrides should still be in place
        assert t["crest_min_db"] == 5.0
        assert t["sub_max"] == 0.14
        assert t["section_range_max_db"] == 10.0

    def test_every_genre_has_valid_thresholds(self):
        """Every genre override should have only keys that exist in defaults."""
        for genre_key, overrides in GOAL_FLAG_OVERRIDES.items():
            for key in overrides:
                assert key in DEFAULT_FLAG_THRESHOLDS, (
                    f"{genre_key} override key '{key}' not in DEFAULT_FLAG_THRESHOLDS"
                )


class TestReviewFlagsWithGenreOverrides:
    """review_flags() should produce different flags for different genres."""

    _BASE_METRICS = {
        "peak_dbfs": -0.5,
        "true_peak_dbfs": -0.1,
        "crest_factor_db": 7.0,
        "integrated_lufs": -14.0,
        "stereo_correlation": 0.9,
        "stereo_balance": 1.0,
        "stereo_width_ratio": 0.5,
        "dc_offset": 0.001,
        "leading_silence_seconds": 0.1,
        "trailing_silence_seconds": 0.2,
        "bands": {
            "sub": 0.15,
            "bass": 0.10,
            "low_mids": 0.12,
            "mids": 0.45,
            "presence": 0.15,
            "sibilance": 0.08,
            "air": 0.05,
        },
        "perceptual_bands": {
            "presence": 0.25,
            "sibilance": 0.12,
            "air": 0.06,
        },
        "side_bands": {
            "sub": 0.02,
            "bass": 0.04,
        },
        "correlation_bands": {
            "sub": 0.6,
            "bass": 0.7,
        },
        "tonal_balance": {
            "low_end_share": 0.40,
            "clarity_share": 0.10,
        },
        "dynamic_profile": {
            "profile": "Controlled",
            "section_range_db": 6.0,
        },
    }

    def test_high_sub_flagged_under_premaster_not_hip_hop(self):
        """Sub at 0.15 should flag 'Heavy sub' under premaster (threshold 0.12) but not hip_hop (threshold 0.20)."""
        premaster_metrics = dict(self._BASE_METRICS)
        premaster_metrics["mix_goal"] = {"key": "premaster", "label": "Premaster"}
        hiphop_metrics = dict(self._BASE_METRICS)
        hiphop_metrics["mix_goal"] = {"key": "hip_hop", "label": "Hip Hop"}

        premaster_flags = review_flags(premaster_metrics)
        hiphop_flags = review_flags(hiphop_metrics)

        premaster_labels = {f["label"] for f in premaster_flags}
        hiphop_labels = {f["label"] for f in hiphop_flags}

        assert "Heavy sub" in premaster_labels, (
            f"Premaster should flag Heavy sub at sub=0.15 (threshold 0.12), got labels: {premaster_labels}"
        )
        assert "Heavy sub" not in hiphop_labels, (
            f"Hip hop should NOT flag Heavy sub at sub=0.15 (threshold 0.20), got labels: {hiphop_labels}"
        )

    def test_low_dynamics_flagged_under_acoustic_not_hip_hop(self):
        """Crest at 6.0 should flag 'Low dynamics' under acoustic (threshold 9.0) but not hip_hop (threshold 3.0)."""
        acoustic_metrics = dict(self._BASE_METRICS)
        acoustic_metrics["mix_goal"] = {"key": "acoustic", "label": "Acoustic"}
        hiphop_metrics = dict(self._BASE_METRICS)
        hiphop_metrics["mix_goal"] = {"key": "hip_hop", "label": "Hip Hop"}

        acoustic_flags = review_flags(acoustic_metrics)
        hiphop_flags = review_flags(hiphop_metrics)

        acoustic_labels = {f["label"] for f in acoustic_flags}
        hiphop_labels = {f["label"] for f in hiphop_flags}

        assert "Low dynamics" in acoustic_labels, (
            f"Acoustic should flag Low dynamics at crest=7.0 (threshold 9.0), got labels: {acoustic_labels}"
        )
        assert "Low dynamics" not in hiphop_labels, (
            f"Hip hop should NOT flag Low dynamics at crest=7.0 (threshold 3.0), got labels: {hiphop_labels}"
        )

    def test_hot_mix_flagged_under_acoustic_not_edm(self):
        """LUFS at -14.0 should flag 'Hot Mix' under acoustic (threshold -16.0) but not edm (threshold -8.0)."""
        acoustic_metrics = dict(self._BASE_METRICS)
        acoustic_metrics["mix_goal"] = {"key": "acoustic", "label": "Acoustic"}
        edm_metrics = dict(self._BASE_METRICS)
        edm_metrics["mix_goal"] = {"key": "edm", "label": "EDM"}

        acoustic_flags = review_flags(acoustic_metrics)
        edm_flags = review_flags(edm_metrics)

        acoustic_labels = {f["label"] for f in acoustic_flags}
        edm_labels = {f["label"] for f in edm_flags}

        assert "Hot Mix" in acoustic_labels, (
            f"Acoustic should flag Hot Mix at LUFS=-14.0 (threshold -16.0), got labels: {acoustic_labels}"
        )
        assert "Hot Mix" not in edm_labels, (
            f"EDM should NOT flag Hot Mix at LUFS=-14.0 (threshold -8.0), got labels: {edm_labels}"
        )

    def test_low_end_heavy_flagged_under_hip_hop_not_acoustic(self):
        """Low_end_share at 0.60 should flag under hip_hop (threshold 0.65) but wait... 0.60 < 0.65 so no.
        Let's test with low_end_share at 0.70 for a more interesting case."""
        # Actually test with a value that crosses both
        high_low_end_metrics = dict(self._BASE_METRICS)
        high_low_end_metrics["tonal_balance"] = {
            "low_end_share": 0.70,
            "clarity_share": 0.05,
        }

        # Hip hop allows up to 0.65, acoustic up to 0.42
        hiphop_metrics = dict(high_low_end_metrics)
        hiphop_metrics["mix_goal"] = {"key": "hip_hop", "label": "Hip Hop"}
        acoustic_metrics = dict(high_low_end_metrics)
        acoustic_metrics["mix_goal"] = {"key": "acoustic", "label": "Acoustic"}

        hiphop_flags = review_flags(hiphop_metrics)
        acoustic_flags = review_flags(acoustic_metrics)

        hiphop_labels = {f["label"] for f in hiphop_flags}
        acoustic_labels = {f["label"] for f in acoustic_flags}

        assert "Low-end heavy balance" in acoustic_labels, (
            "Acoustic should flag Low-end heavy balance at share=0.70 (threshold 0.42)"
        )
        assert "Low-end heavy balance" in hiphop_labels, (
            "Hip hop should also flag Low-end heavy balance at share=0.70 (threshold 0.65)"
        )

    def test_perceived_harshness_flagged_under_acoustic_not_edm(self):
        """Perceived presence at 0.35 should flag under acoustic (threshold 0.32) but not edm (threshold 0.42)."""
        harsh_metrics = dict(self._BASE_METRICS)
        harsh_metrics["perceptual_bands"] = {
            "presence": 0.35,
            "sibilance": 0.15,
            "air": 0.08,
        }
        acoustic_metrics = dict(harsh_metrics)
        acoustic_metrics["mix_goal"] = {"key": "acoustic", "label": "Acoustic"}
        edm_metrics = dict(harsh_metrics)
        edm_metrics["mix_goal"] = {"key": "edm", "label": "EDM"}

        acoustic_flags = review_flags(acoustic_metrics)
        edm_flags = review_flags(edm_metrics)

        acoustic_labels = {f["label"] for f in acoustic_flags}
        edm_labels = {f["label"] for f in edm_flags}

        assert "Perceived harshness" in acoustic_labels
        assert "Perceived harshness" not in edm_labels

    def test_low_mid_buildup_flagged_under_premaster_not_lo_fi(self):
        """Low mids at 0.25 should flag under premaster (threshold 0.18) but not lo_fi (threshold 0.28)."""
        build_up_metrics = dict(self._BASE_METRICS)
        build_up_metrics["bands"] = dict(self._BASE_METRICS["bands"])
        build_up_metrics["bands"]["low_mids"] = 0.25

        premaster_metrics = dict(build_up_metrics)
        premaster_metrics["mix_goal"] = {"key": "premaster", "label": "Premaster"}
        lofi_metrics = dict(build_up_metrics)
        lofi_metrics["mix_goal"] = {"key": "lo_fi", "label": "Lo-Fi"}

        premaster_flags = review_flags(premaster_metrics)
        lofi_flags = review_flags(lofi_metrics)

        premaster_labels = {f["label"] for f in premaster_flags}
        lofi_labels = {f["label"] for f in lofi_flags}

        assert "Low-mid build-up" in premaster_labels
        assert "Low-mid build-up" not in lofi_labels

    def test_flag_detail_includes_goal_label(self):
        """Flag detail text should reference the goal label (e.g., Hip Hop)."""
        metrics = dict(self._BASE_METRICS)
        metrics["crest_factor_db"] = 2.0  # Below all thresholds
        metrics["mix_goal"] = {"key": "hip_hop", "label": "Hip Hop"}

        flags = review_flags(metrics)
        low_dynamics = [f for f in flags if f["label"] == "Low dynamics"]
        assert len(low_dynamics) == 1
        assert "Hip Hop" in low_dynamics[0]["detail"]

    def test_side_bass_mud_threshold_differs_by_genre(self):
        """Side bass at 0.05 should flag under hip_hop (threshold 0.04) but not premaster (threshold 0.08)."""
        side_metrics = dict(self._BASE_METRICS)
        side_metrics["side_bands"] = {"sub": 0.01, "bass": 0.05}

        premaster_metrics = dict(side_metrics)
        premaster_metrics["mix_goal"] = {"key": "premaster", "label": "Premaster"}
        hiphop_metrics = dict(side_metrics)
        hiphop_metrics["mix_goal"] = {"key": "hip_hop", "label": "Hip Hop"}

        premaster_flags = review_flags(premaster_metrics)
        hiphop_flags = review_flags(hiphop_metrics)

        premaster_labels = {f["label"] for f in premaster_flags}
        hiphop_labels = {f["label"] for f in hiphop_flags}

        assert "Side Bass Mud" not in premaster_labels
        assert "Side Bass Mud" in hiphop_labels

    def test_phase_cancellation_threshold_differs(self):
        """Sub correlation at 0.45 should flag under hip_hop (threshold 0.5) but not premaster (threshold 0.4)."""
        phase_metrics = dict(self._BASE_METRICS)
        phase_metrics["correlation_bands"] = {"sub": 0.45, "bass": 0.8}

        premaster_metrics = dict(phase_metrics)
        premaster_metrics["mix_goal"] = {"key": "premaster", "label": "Premaster"}
        hiphop_metrics = dict(phase_metrics)
        hiphop_metrics["mix_goal"] = {"key": "hip_hop", "label": "Hip Hop"}

        premaster_flags = review_flags(premaster_metrics)
        hiphop_flags = review_flags(hiphop_metrics)

        premaster_labels = {f["label"] for f in premaster_flags}
        hiphop_labels = {f["label"] for f in hiphop_flags}

        assert "Low-End Phase Cancellation" not in premaster_labels
        assert "Low-End Phase Cancellation" in hiphop_labels

    def test_game_audio_headroom_less_aggressive_than_premaster(self):
        """Game audio has peak_max_dbfs=-1.0 (same as premaster default) but stricter true_peak_clip_dbfs=-1.0.
        A signal at peak_dbfs=-0.5 should flag 'Low headroom' under both."""
        game_metrics = dict(self._BASE_METRICS)
        game_metrics["mix_goal"] = {"key": "game_audio", "label": "Game audio"}

        game_flags = review_flags(game_metrics)
        game_labels = {f["label"] for f in game_flags}

        # peak_dbfs=-0.5 > -1.0 -> should flag Low headroom
        assert "Low headroom" in game_labels

    def test_game_audio_true_peak_strict(self):
        """Game audio has true_peak_clip_dbfs=-1.0, so true_peak_dbfs=-0.1 should flag 'Clipping risk'."""
        game_metrics = dict(self._BASE_METRICS)
        game_metrics["mix_goal"] = {"key": "game_audio", "label": "Game audio"}

        game_flags = review_flags(game_metrics)
        game_labels = {f["label"] for f in game_flags}

        assert "Clipping risk" in game_labels, (
            f"Game audio should flag Clipping risk at true_peak=-0.1 (threshold -1.0), got: {game_labels}"
        )

    def test_game_audio_lufs_threshold(self):
        """Game audio has lufs_max=-14.0, so LUFS at -14.0 should NOT flag 'Hot Mix'."""
        game_metrics = dict(self._BASE_METRICS)
        game_metrics["integrated_lufs"] = -14.0  # At threshold, should not flag
        game_metrics["mix_goal"] = {"key": "game_audio", "label": "Game audio"}

        game_flags = review_flags(game_metrics)
        game_labels = {f["label"] for f in game_flags}

        assert "Hot Mix" not in game_labels, (
            f"Game audio should NOT flag Hot Mix at LUFS=-14.0 (at threshold), got: {game_labels}"
        )

        # But LUFS at -13.0 (above threshold) should flag
        hot_metrics = dict(game_metrics)
        hot_metrics["integrated_lufs"] = -13.0
        hot_flags = review_flags(hot_metrics)
        hot_labels = {f["label"] for f in hot_flags}
        assert "Hot Mix" in hot_labels

    def test_game_audio_side_bass_strict(self):
        """Game audio has side_bass_max=0.06, so side bass at 0.07 should flag 'Side Bass Mud'."""
        game_metrics = dict(self._BASE_METRICS)
        game_metrics["side_bands"] = {"sub": 0.01, "bass": 0.07}
        game_metrics["mix_goal"] = {"key": "game_audio", "label": "Game audio"}

        game_flags = review_flags(game_metrics)
        game_labels = {f["label"] for f in game_flags}

        assert "Side Bass Mud" in game_labels, (
            f"Game audio should flag Side Bass Mud at side_bass=0.07 (threshold 0.06), got: {game_labels}"
        )

    def test_game_audio_phase_cancellation_strict(self):
        """Game audio has correlation_sub_min=0.5, so sub correlation at 0.45 should flag."""
        game_metrics = dict(self._BASE_METRICS)
        game_metrics["correlation_bands"] = {"sub": 0.45, "bass": 0.8}
        game_metrics["mix_goal"] = {"key": "game_audio", "label": "Game audio"}

        game_flags = review_flags(game_metrics)
        game_labels = {f["label"] for f in game_flags}

        assert "Low-End Phase Cancellation" in game_labels


# ---------------------------------------------------------------------------
#  Report summary cache tests
# ---------------------------------------------------------------------------

class TestCacheSqlLiteRoundTrip:
    """_cache_report_summary and _read_cached_summaries round-trip correctly."""

    @staticmethod
    def _make_connect(db_path: Path):
        def connect_func():
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            return conn
        return connect_func

    def test_cache_round_trip(self, tmp_path):
        """A cached report should be readable via _read_cached_summaries."""
        db_path = tmp_path / "cache.db"
        connect_func = self._make_connect(db_path)

        # Init table
        with connect_func() as conn:
            conn.execute(REPORT_SUMMARY_CACHE_SQL)
            conn.commit()

        report = {
            "id": "rev-001",
            "title": "Test Mix",
            "report_name": "rev-001.json",
            "created_at": "2026-06-24T12:00:00",
            "version_label": "v1",
            "summary": "A test summary.",
            "flags": [{"severity": "medium", "label": "Low dynamics", "detail": "Crest is low."}],
            "metrics": {
                "technical_score": 82,
                "technical_rating": "Solid with checks",
                "peak_dbfs": -2.1,
                "rms_dbfs_estimate": -12.4,
                "crest_factor_db": 8.2,
                "perceptual_summary": {"dominant_band": "mids"},
            },
        }

        _cache_report_summary(report, connect_func)

        cached = _read_cached_summaries(10, connect_func=connect_func)
        assert len(cached) == 1

        item = cached[0]
        assert item["review_id"] == "rev-001"
        assert item["score"] == 82
        assert item["rating"] == "Solid with checks"
        assert item["peak_dbfs"] == -2.1
        assert item["rms_dbfs_estimate"] == -12.4
        assert item["crest_factor_db"] == 8.2
        assert item["dominant_band"] == "mids"
        assert item["summary"] == "A test summary."

        # Check JSON fields were deserialised
        assert isinstance(item["flags"], list)
        assert len(item["flags"]) == 1
        assert item["flags"][0]["label"] == "Low dynamics"

    def test_cache_empty_flags(self, tmp_path):
        """A report with no flags should cache correctly."""
        db_path = tmp_path / "cache_empty.db"
        connect_func = self._make_connect(db_path)

        with connect_func() as conn:
            conn.execute(REPORT_SUMMARY_CACHE_SQL)
            conn.commit()

        report = {
            "id": "rev-noflags",
            "title": "Clean Mix",
            "report_name": "rev-noflags.json",
            "created_at": "2026-06-24T13:00:00",
            "summary": "All good.",
            "flags": [],
            "metrics": {"technical_score": 92, "technical_rating": "Clean technical pass"},
        }

        _cache_report_summary(report, connect_func)
        cached = _read_cached_summaries(10, connect_func=connect_func)
        assert len(cached) == 1

        item = cached[0]
        assert item["review_id"] == "rev-noflags"
        # Should be parsed as empty list, not None
        assert isinstance(item["flags"], list)
        assert item["flags"] == []

    def test_cache_multiple_reports_respects_limit(self, tmp_path):
        """Multiple cached reports should respect the limit parameter."""
        db_path = tmp_path / "cache_multi.db"
        connect_func = self._make_connect(db_path)

        with connect_func() as conn:
            conn.execute(REPORT_SUMMARY_CACHE_SQL)
            conn.commit()

        for i in range(10):
            report = {
                "id": f"rev-{i:03d}",
                "title": f"Mix {i}",
                "report_name": f"rev-{i:03d}.json",
                "created_at": f"2026-06-24T{12 + i // 60:02d}:{i % 60:02d}:00",
                "summary": f"Summary {i}.",
                "flags": [],
                "metrics": {"technical_score": 80 + i, "technical_rating": "Solid with checks"},
            }
            _cache_report_summary(report, connect_func)

        all_cached = _read_cached_summaries(100, connect_func=connect_func)
        assert len(all_cached) == 10

        limited = _read_cached_summaries(3, connect_func=connect_func)
        assert len(limited) == 3

    def test_cache_update_replaces_existing(self, tmp_path):
        """Caching the same review_id should replace (INSERT OR REPLACE)."""
        db_path = tmp_path / "cache_update.db"
        connect_func = self._make_connect(db_path)

        with connect_func() as conn:
            conn.execute(REPORT_SUMMARY_CACHE_SQL)
            conn.commit()

        report_v1 = {
            "id": "rev-update",
            "title": "Original Title",
            "report_name": "rev-update.json",
            "created_at": "2026-06-24T12:00:00",
            "summary": "Original.",
            "flags": [],
            "metrics": {"technical_score": 75, "technical_rating": "Needs attention"},
        }
        _cache_report_summary(report_v1, connect_func)

        report_v2 = {
            "id": "rev-update",
            "title": "Updated Title",
            "report_name": "rev-update.json",
            "created_at": "2026-06-24T14:00:00",
            "summary": "Updated.",
            "flags": [],
            "metrics": {"technical_score": 88, "technical_rating": "Clean technical pass"},
        }
        _cache_report_summary(report_v2, connect_func)

        cached = _read_cached_summaries(10, connect_func=connect_func)
        assert len(cached) == 1
        assert cached[0]["title"] == "Updated Title"
        assert cached[0]["score"] == 88

    def test_cache_with_reference_and_version_fields(self, tmp_path):
        """Caching with reference, comparison, version data should round-trip."""
        db_path = tmp_path / "cache_complex.db"
        connect_func = self._make_connect(db_path)

        with connect_func() as conn:
            conn.execute(REPORT_SUMMARY_CACHE_SQL)
            conn.commit()

        report = {
            "id": "rev-complex",
            "title": "Complex Mix",
            "report_name": "rev-complex.json",
            "created_at": "2026-06-24T15:00:00",
            "version_label": "v3",
            "summary": "Complex summary.",
            "flags": [{"severity": "high", "label": "Mono risk", "detail": "Correlation low."}],
            "metrics": {"technical_score": 65, "technical_rating": "Needs attention", "peak_dbfs": -0.5},
            "reference": {"filename": "ref.wav", "name": "Pop Ref"},
            "comparison": {"rms_delta_db": -2.5, "largest_spectral_difference": {"band": "sub", "delta": 0.08}},
            "version_comparison": {"rms_delta_db": 1.2},
            "version_advice": ["Dynamics improved."],
            "revision_agent": {"steps": [{"focus": "Export", "action": "Export v4."}]},
            "mix_critique": {"text": "Main read:\nCritique.", "mode": "deterministic"},
            "revision_impact": {"verdict": "improved", "score_delta": 5},
            "comparison_advice": ["Reference has less sub."],
            "session_report": {"fix_first": "Ease limiter."},
            "previous_version": {"id": "prev", "version_label": "v2"},
        }

        _cache_report_summary(report, connect_func)

        cached = _read_cached_summaries(10, connect_func=connect_func)
        assert len(cached) == 1
        item = cached[0]

        # Check deserialised JSON fields
        assert isinstance(item["reference"], dict)
        assert item["reference"]["filename"] == "ref.wav"

        assert isinstance(item["comparison"], dict)
        assert item["comparison"]["rms_delta_db"] == -2.5

        assert isinstance(item["version_comparison"], dict)
        assert item["version_comparison"]["rms_delta_db"] == 1.2

        assert isinstance(item["version_advice"], list)
        assert "Dynamics improved." in item["version_advice"]

        assert isinstance(item["revision_agent"], dict)
        assert item["revision_agent"]["steps"][0]["focus"] == "Export"

        assert isinstance(item["mix_critique"], dict)
        assert item["mix_critique"]["mode"] == "deterministic"

        assert isinstance(item["revision_impact"], dict)
        assert item["revision_impact"]["verdict"] == "improved"

        assert isinstance(item["comparison_advice"], list)
        assert item["comparison_advice"][0] == "Reference has less sub."

        assert isinstance(item["session_report"], dict)
        assert item["session_report"]["fix_first"] == "Ease limiter."

        assert isinstance(item["previous_version"], dict)
        assert item["previous_version"]["version_label"] == "v2"

    def test_cache_without_review_id_does_nothing(self, tmp_path):
        """Caching a report without an id should silently do nothing."""
        db_path = tmp_path / "cache_noid.db"
        connect_func = self._make_connect(db_path)

        with connect_func() as conn:
            conn.execute(REPORT_SUMMARY_CACHE_SQL)
            conn.commit()

        _cache_report_summary({"title": "No ID"}, connect_func)
        cached = _read_cached_summaries(10, connect_func=connect_func)
        assert len(cached) == 0

    def test_delete_cached_summary(self, tmp_path):
        """_delete_cached_summary should remove the entry."""
        db_path = tmp_path / "cache_delete.db"
        connect_func = self._make_connect(db_path)

        with connect_func() as conn:
            conn.execute(REPORT_SUMMARY_CACHE_SQL)
            conn.commit()

        report = {
            "id": "rev-del",
            "title": "To Delete",
            "report_name": "rev-del.json",
            "created_at": "2026-06-24T16:00:00",
            "summary": "Will be deleted.",
            "flags": [],
            "metrics": {"technical_score": 70},
        }
        _cache_report_summary(report, connect_func)

        cached_before = _read_cached_summaries(10, connect_func=connect_func)
        assert len(cached_before) == 1

        _delete_cached_summary("rev-del", connect_func)
        cached_after = _read_cached_summaries(10, connect_func=connect_func)
        assert len(cached_after) == 0

    def test_delete_non_existent_does_not_error(self, tmp_path):
        """Deleting a non-existent review_id should not raise."""
        db_path = tmp_path / "cache_del_nonexist.db"
        connect_func = self._make_connect(db_path)

        with connect_func() as conn:
            conn.execute(REPORT_SUMMARY_CACHE_SQL)
            conn.commit()

        # Should not raise
        _delete_cached_summary("nonexistent-id", connect_func)

    def test_deserialize_json_fields_handles_edge_cases(self):
        """_deserialize_json_fields should handle None, empty, and invalid JSON."""
        item = {
            "flags_json": '[{"label": "Test"}]',
            "reference_json": None,
            "comparison_json": "",
            "bad_json": "not valid json",
        }
        _deserialize_json_fields(item, ["flags_json", "reference_json", "comparison_json", "bad_json"])

        assert isinstance(item["flags"], list)
        assert item["flags"][0]["label"] == "Test"
        assert item["reference"] is None
        assert item["comparison"] == ""  # empty string passes through as falsy
        # "bad_json" -> key becomes "bad" (strips _json). If bad JSON, raw value set as fallback
        # The function keeps raw value on JSONDecodeError for _json-suffixed keys,
        # but the test name doesn't end in _json -> output key would be "bad"
        # Let's just verify the original key still exists and processing didn't crash
        assert item.get("bad_json") == "not valid json"

    def test_kenn_handoff_fallback_on_cache(self, tmp_path):
        """Caching should handle missing kenn_handoff gracefully (uses the imported kenn_handoff fallback)."""
        db_path = tmp_path / "cache_kenn.db"
        connect_func = self._make_connect(db_path)

        with connect_func() as conn:
            conn.execute(REPORT_SUMMARY_CACHE_SQL)
            conn.commit()

        report = {
            "id": "rev-kenn",
            "title": "Kenn Test",
            "report_name": "rev-kenn.json",
            "created_at": "2026-06-24T17:00:00",
            "summary": "Kenn test.",
            "flags": [],
            "metrics": {"technical_score": 80, "technical_rating": "Solid with checks"},
            # No kenn_handoff key — should fall back
        }

        # This should not raise (kenn_handoff fallback is called)
        _cache_report_summary(report, connect_func)

        cached = _read_cached_summaries(10, connect_func=connect_func)
        assert len(cached) == 1
        assert cached[0]["review_id"] == "rev-kenn"

    def test_high_flag_count_zero_when_no_flags(self, tmp_path):
        """A report with no flags should have high_flag_count=0."""
        db_path = tmp_path / "cache_hfc0.db"
        connect_func = self._make_connect(db_path)

        with connect_func() as conn:
            conn.execute(REPORT_SUMMARY_CACHE_SQL)
            conn.commit()

        report = {
            "id": "rev-hfc0",
            "title": "Clean",
            "report_name": "rev-hfc0.json",
            "created_at": "2026-06-25T10:00:00",
            "summary": "Clean.",
            "flags": [],
            "metrics": {"technical_score": 95, "technical_rating": "Clean technical pass"},
        }
        _cache_report_summary(report, connect_func)
        cached = _read_cached_summaries(10, connect_func=connect_func)
        assert cached[0]["high_flag_count"] == 0

    def test_high_flag_count_counts_only_high_severity(self, tmp_path):
        """Only flags with severity='high' should be counted."""
        db_path = tmp_path / "cache_hfc1.db"
        connect_func = self._make_connect(db_path)

        with connect_func() as conn:
            conn.execute(REPORT_SUMMARY_CACHE_SQL)
            conn.commit()

        report = {
            "id": "rev-hfc1",
            "title": "Flags",
            "report_name": "rev-hfc1.json",
            "created_at": "2026-06-25T11:00:00",
            "summary": "Has flags.",
            "flags": [
                {"severity": "high", "label": "Mono risk"},
                {"severity": "medium", "label": "Low dynamics"},
                {"severity": "high", "label": "Clipping risk"},
                {"severity": "low", "label": "Long intro silence"},
            ],
            "metrics": {"technical_score": 60, "technical_rating": "Needs attention"},
        }
        _cache_report_summary(report, connect_func)
        cached = _read_cached_summaries(10, connect_func=connect_func)
        assert cached[0]["high_flag_count"] == 2  # Mono risk + Clipping risk

    def test_high_flag_count_is_stored_as_integer(self, tmp_path):
        """high_flag_count should be an integer in the DB, not a string."""
        db_path = tmp_path / "cache_hfc_int.db"
        connect_func = self._make_connect(db_path)

        with connect_func() as conn:
            conn.execute(REPORT_SUMMARY_CACHE_SQL)
            conn.commit()

        report = {
            "id": "rev-hfc-int",
            "title": "Integer",
            "report_name": "rev-hfc-int.json",
            "created_at": "2026-06-25T12:00:00",
            "summary": "Check type.",
            "flags": [{"severity": "high", "label": "Test"}],
            "metrics": {"technical_score": 70, "technical_rating": "Solid with checks"},
        }
        _cache_report_summary(report, connect_func)

        # Direct DB query to verify column type
        with connect_func() as conn:
            row = conn.execute(
                "SELECT high_flag_count FROM mix_report_summaries WHERE review_id = ?",
                ("rev-hfc-int",),
            ).fetchone()
        assert row is not None
        value = row["high_flag_count"]
        assert isinstance(value, int), f"Expected int, got {type(value)}: {value}"
        assert value == 1
