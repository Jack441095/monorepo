from pathlib import Path
import pytest

def test_training_data_notes_exist():
    notes_dir = Path(__file__).resolve().parents[1] / "Training_Data_Notes"
    if not notes_dir.is_dir():
        pytest.skip("Local knowledge corpus is intentionally excluded from public CI")
    notes = list(notes_dir.glob("*.md"))
    assert len(notes) > 50, f"Expected at least 50 notes, found {len(notes)}"
