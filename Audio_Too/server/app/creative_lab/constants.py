"""Shared paths and thresholds for the creative_lab_* modules.

Split out of creative_lab.py (was 1,261 lines) — see docs/BACKLOG.md.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = ROOT.parent
PYTHON = REPO_ROOT / ".venv" / "bin" / "python"
DATA_PATH = REPO_ROOT / "data" / "creative_lab_sessions.json"
PORTFOLIO_AUDIO = ROOT / "portfolio" / "audio"
KENN_ROOT = REPO_ROOT / "studio" / "kenn" / "kenn"
KENN_NOTES_DIR = KENN_ROOT / "Training_Data_Notes"
MAIN_EVAL_PATH = KENN_ROOT / "evals" / "questions.json"
CREATIVE_DRAFT_EVAL_PATH = KENN_ROOT / "evals" / "draft_creative_lab_cases.json"
CREATIVE_REPAIR_RECORDS_PATH = KENN_ROOT / "artifacts" / "training" / "creative_lab_repair_records.jsonl"
CREATIVE_APPROVED_REPAIR_RECORDS_PATH = KENN_ROOT / "artifacts" / "training" / "creative_lab_repair_records.approved.jsonl"
CREATIVE_APPROVED_REPAIR_MANIFEST_PATH = KENN_ROOT / "artifacts" / "training" / "creative_lab_repair_records.approved.manifest.json"
CREATIVE_REPAIR_REVIEW_PATH = KENN_ROOT / "artifacts" / "training" / "creative_lab_repair_reviews.json"
MAX_SESSIONS = 120
MAX_EVENTS = 80
MAX_FEEDBACK = 300
REPAIR_STOPWORDS = {
    "about",
    "after",
    "answer",
    "before",
    "could",
    "does",
    "from",
    "have",
    "into",
    "make",
    "should",
    "sound",
    "that",
    "this",
    "what",
    "when",
    "where",
    "with",
    "without",
    "would",
    "your",
}
