"""Creative Lab persistence and generated-audio handoff helpers.

This module used to be one 1,261-line file; it's now a thin re-export shim over
creative_lab_constants / creative_lab_storage / creative_lab_metrics /
creative_lab_eval / creative_lab_training / creative_lab_repair /
creative_lab_portfolio, split by concern (see docs/BACKLOG.md for the
decomposition record). Tests that monkeypatch a path constant or an internal
function (e.g. DATA_PATH, KENN_NOTES_DIR, _build_index) must patch the submodule
that owns the real call site, not this shim — patching the shim's copy of a name
doesn't affect another module's own import of that same name. demo_feedback and
mix_review are whole-module references, so patching their attributes (e.g.
`creative_lab.demo_feedback.record_feedback`) works from any module that holds
the same module object.
"""

from __future__ import annotations

import demo_feedback  # noqa: F401
from audio_analysis.mix_review import mix_review  # noqa: F401

from .constants import (  # noqa: F401
    CREATIVE_APPROVED_REPAIR_MANIFEST_PATH,
    CREATIVE_APPROVED_REPAIR_RECORDS_PATH,
    CREATIVE_DRAFT_EVAL_PATH,
    CREATIVE_REPAIR_RECORDS_PATH,
    CREATIVE_REPAIR_REVIEW_PATH,
    DATA_PATH,
    KENN_NOTES_DIR,
    KENN_ROOT,
    MAIN_EVAL_PATH,
    MAX_EVENTS,
    MAX_FEEDBACK,
    MAX_SESSIONS,
    PORTFOLIO_AUDIO,
    PYTHON,
    REPAIR_STOPWORDS,
    REPO_ROOT,
    ROOT,
)
from .storage import (  # noqa: F401
    _display_path,
    _load,
    _safe_int,
    _save,
    _slug,
    now,
)
from .metrics import (  # noqa: F401
    _repair_terms,
    prompt_leaderboard,
    quality_metrics,
    record_feedback,
    record_session_event,
    repair_comparison,
    repair_queue,
    repair_recommendations,
    session_replay,
    snapshot,
)
from .eval import (  # noqa: F401
    _draft_eval_case,
    _draft_eval_suite,
    _load_eval_suite,
    _save_draft_eval_suite,
    _save_eval_suite,
)
from .training import (  # noqa: F401
    _count_by,
    _load_repair_reviews,
    _read_repair_training_records,
    _repair_dataset_manifest,
    _repair_training_record,
    _save_repair_reviews,
    approved_repair_manifest_snapshot,
    export_approved_repair_training_records,
    export_repair_training_records,
    repair_training_export_snapshot,
    repair_training_records,
    review_repair_training_record,
    validate_approved_repair_training_export,
)
from .repair import (  # noqa: F401
    _approve_note,
    _build_index,
    _evaluate_repair_case,
    _python_cmd,
    _repair_note_template,
    _resolve_repair_note,
    _source_ranking_report,
    create_repair_artifacts,
    promote_repair,
    promote_repair_eval_case,
    run_repair_recommendation,
)
from .portfolio import (  # noqa: F401
    _portfolio_audio_path,
    review_generated_audio,
)
