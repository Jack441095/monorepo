"""Before/after spectral-match evidence report — the QA + client artifact."""

from __future__ import annotations

import io
import sys
import wave
from pathlib import Path

import numpy as np
import pytest

from audio_analysis.mix_review.match_report import (
    build_match_evidence, render_match_report_html,
)

SR = 44100

_KENN_ROOT = Path(__file__).resolve().parent.parent.parent / "studio" / "kenn"
sys.path.insert(0, str(_KENN_ROOT))
from kenn.retrieval.index_store import active_artifact_path  # noqa: E402

_KENN_INDEX_BUILT = active_artifact_path("chunks.jsonl").exists()
requires_kenn_index = pytest.mark.skipif(
    not _KENN_INDEX_BUILT,
    reason="KENN index not built — run studio/kenn/kenn/retrieval/build_index.py first.",
)


def _wav(sig: np.ndarray) -> bytes:
    pcm = (np.clip(sig, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm)
    return out.getvalue()


def _tones(weights: dict[float, float], seconds: float = 5.0) -> np.ndarray:
    t = np.linspace(0, seconds, int(SR * seconds), endpoint=False)
    sig = sum(a * np.sin(2 * np.pi * f * t) for f, a in weights.items())
    return (sig + 0.01 * np.random.default_rng(2).standard_normal(len(t))).astype(np.float64)


def _fixtures(tmp_path: Path):
    """before = bass-light, after = bass-corrected, reference = bass-forward."""
    before = _wav(_tones({60: 0.03, 250: 0.06, 3000: 0.40}))
    after = _wav(_tones({60: 0.30, 250: 0.25, 3000: 0.22}))
    ref = tmp_path / "ref.wav"
    ref.write_bytes(_wav(_tones({60: 0.45, 250: 0.30, 3000: 0.15})))
    return before, after, ref


def test_evidence_shows_the_match_improved_the_score(tmp_path: Path) -> None:
    before, after, ref = _fixtures(tmp_path)
    ev = build_match_evidence(before, after, ref)

    assert ev["score_after"] > ev["score_before"], "matched mix should score closer to the target"
    assert ev["score_delta"] == round(ev["score_after"] - ev["score_before"], 1)
    for key in ("bands_before", "bands_after", "bands_target"):
        assert set(ev[key]) >= {"sub", "bass", "mids", "presence"}
    # the corrected mix should sit closer to the target in the low end
    assert abs(ev["bands_after"]["bass"] - ev["bands_target"]["bass"]) < \
           abs(ev["bands_before"]["bass"] - ev["bands_target"]["bass"])


def test_report_html_is_self_contained_and_complete(tmp_path: Path) -> None:
    before, after, ref = _fixtures(tmp_path)
    ev = build_match_evidence(before, after, ref, applied_bands=[
        {"type": "peaking", "frequency": 60.0, "gain_db": 4.5, "q": 1.4, "reason": "Ref match 60Hz"},
    ])
    html = render_match_report_html(ev, mix_label="Test Mix", ref_label="Pop")

    # self-contained: no external assets of any kind
    for external in ('src="http', 'href="http', "<script", "@import"):
        assert external not in html, f"report must not reference {external}"
    for section in ("Match score", "Tonal balance", "Corrections applied", "<svg", "Test Mix"):
        assert section in html
    assert str(ev["score_after"]) in html
    assert "60 Hz" in html and "+4.5 dB" in html


def test_genre_folder_target_is_labelled_as_median(tmp_path: Path) -> None:
    before, after, _ = _fixtures(tmp_path)
    d = tmp_path / "pop"
    d.mkdir()
    for i, sub in enumerate((0.45, 0.40, 0.50)):
        (d / f"r{i}.wav").write_bytes(_wav(_tones({60: sub, 250: 0.30, 3000: 0.15})))

    ev = build_match_evidence(before, after, d)
    assert ev["n_references"] == 3
    html = render_match_report_html(ev, mix_label="M", ref_label="Pop")
    assert "3 reference tracks, median target" in html


# ── KENN grounding (Stage 9.8-equivalent: was computed/tested, never wired) ──


@requires_kenn_index
def test_evidence_grounds_applied_moves_and_reference_profile_via_kenn(tmp_path: Path) -> None:
    """The applied match-EQ move and the reference's own tonal profile should
    each get a real, cited explanation — same grounded pipeline already wired
    into mixdown/mix_delivery.py's report, reused here rather than duplicated."""
    before, after, ref = _fixtures(tmp_path)
    ev = build_match_evidence(
        before, after, ref,
        applied_bands=[
            {"type": "lowshelf", "frequency": 300.0, "gain_db": 4.0, "q": 1.4,
             "reason": "Ref match 300Hz +4.0 dB (validated low-shelf correction)."},
        ],
        genre="electronic",
    )
    explanations = ev["kenn_explanations"]
    assert explanations, "expected at least one grounded KENN explanation"
    parameters = {e["parameter"] for e in explanations}
    assert "master bus EQ band" in parameters
    assert "reference track profile" in parameters
    for item in explanations:
        assert item["answer"], "a KENN explanation card must not be blank"
        assert item["sources"], f"{item['parameter']} answer must cite a real note"


@requires_kenn_index
def test_kenn_explanations_render_in_the_html(tmp_path: Path) -> None:
    before, after, ref = _fixtures(tmp_path)
    ev = build_match_evidence(before, after, ref, genre="pop")
    html = render_match_report_html(ev, mix_label="Test Mix", ref_label="Pop")
    assert "What KENN says" in html
    from html import escape as _esc
    assert any(_esc(e["answer"]) in html for e in ev["kenn_explanations"])


def test_kenn_lookup_failure_never_blocks_the_evidence_report(tmp_path: Path, monkeypatch) -> None:
    """A KENN/index problem must never prevent the evidence report itself —
    same never-block-delivery contract as every other kenn_handoff call site."""
    import audio_analysis.integration.kenn_handoff as kenn_handoff

    def _boom(*_a, **_kw):
        raise RuntimeError("simulated KENN outage")

    monkeypatch.setattr(kenn_handoff, "annotate_bus_eq_bands_with_kenn", _boom)
    monkeypatch.setattr(kenn_handoff, "annotate_reference_track_profiles_with_kenn", _boom)

    before, after, ref = _fixtures(tmp_path)
    ev = build_match_evidence(before, after, ref, applied_bands=[
        {"type": "peaking", "frequency": 60.0, "gain_db": 4.5, "q": 1.4, "reason": "Ref match 60Hz"},
    ])
    assert ev["kenn_explanations"] == []
    assert ev["score_after"] > ev["score_before"]  # the actual measurement is unaffected

    html = render_match_report_html(ev, mix_label="M", ref_label="Ref")
    assert "What KENN says" not in html
