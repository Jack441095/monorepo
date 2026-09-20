import json


def test_merge_emotion_reference_dataset_normalizes_rows(tmp_path):
    from scripts.merge_emotion_reference_dataset import _normalize_reference_row

    ref = tmp_path / "refs.jsonl"
    row = _normalize_reference_row(
        {
            "emotion": "grief",
            "section_role": "a",
            "melody": [[0, 1.0], [-1, 0.5], [6, 1.0], [5, 2.0]],
            "contour": "desc",
            "emotion_match_score": 0.91,
        },
        source_path=ref,
        row_index=1,
    )

    assert row is not None
    assert row["source"] == "curated_emotion_reference"
    assert row["emotion"] == "grief"
    assert row["section_role"] == "a"
    assert row["phrase_contours"] == ["desc"]
    assert row["phrase_roles"] == ["reference"]
    assert row["chord_sequence"]
    assert row["accept_score"] == 0.91
    assert row["melody"][0] == [0, 1.0]


def test_merge_emotion_reference_dataset_cli_repeats_reference_rows(tmp_path):
    from scripts.merge_emotion_reference_dataset import main

    base = tmp_path / "base.jsonl"
    refs = tmp_path / "refs.jsonl"
    out = tmp_path / "merged.jsonl"
    base.write_text(
        json.dumps(
            {
                "emotion": "neutral",
                "section_role": "a",
                "melody": [[0, 1.0], [1, 1.0], [2, 1.0]],
                "phrase_contours": ["asc"],
                "phrase_roles": ["opening"],
                "chord_sequence": ["I"],
                "accept_score": 1.0,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    refs.write_text(
        json.dumps(
            {
                "emotion": "joy",
                "section_role": "b",
                "melody": [[0, 0.5], [2, 0.5], [4, 1.0]],
                "contour": "asc",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    import sys

    old = sys.argv
    try:
        sys.argv = [
            "merge_emotion_reference_dataset.py",
            "--base",
            str(base),
            "--references",
            str(refs),
            "--out",
            str(out),
            "--reference-weight",
            "2",
        ]
        assert main() == 0
    finally:
        sys.argv = old

    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == 3
    assert rows[0]["emotion"] == "neutral"
    assert rows[1]["source"] == "curated_emotion_reference"
    assert rows[2]["source"] == "curated_emotion_reference"
