"""Static dashboard structure checks."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def read_js() -> str:
    static_dir = ROOT / "server" / "app" / "static"
    parts = []
    for filename in ["api_client.js", "dashboard_core.js", "crm_workspaces.js", "audio_features.js", "router.js"]:
        path = static_dir / filename
        if path.exists():
            parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)


def test_dashboard_contains_audiogen_workspace() -> None:
    html = (ROOT / "server" / "app" / "static" / "dashboard.html").read_text(encoding="utf-8")
    assert 'data-tab="audiogen"' in html
    assert 'id="audiogen-form"' in html
    assert 'id="audiogen-project"' in html
    assert "Generate loop" in html
    assert "Generate full song" in html
    assert 'data-audiogen-emotion="admiration"' in html
    assert 'data-audiogen-emotion="neutral"' in html
    assert 'id="audiogen-play"' in html
    assert 'id="audiogen-pause"' in html
    assert 'id="audiogen-stop"' in html
    assert 'id="audiogen-jobs"' in html
    assert "Render queue" in html
    assert 'id="audiogen-history"' in html
    assert "Render history" in html


def test_automix_uses_versioned_retry_safe_job_contract() -> None:
    script = (ROOT / "server" / "app" / "static" / "automix.js").read_text(encoding="utf-8")

    assert 'fetch("/api/v1/automix/jobs"' in script
    assert "`/api/v1/automix/jobs?id=${jobId}`" in script
    assert 'fetch("/api/v1/automix/revisions"' in script
    assert 'fetch("/api/v1/automix/uploads"' in script
    assert "automix-upload-${i + 1}" in script
    assert '"Idempotency-Key"' in script


def test_automix_surfaces_lineaged_kenn_advisor_review_controls() -> None:
    static_dir = ROOT / "server" / "app" / "static"
    html = (static_dir / "automix.html").read_text(encoding="utf-8")
    script = (static_dir / "automix.js").read_text(encoding="utf-8")

    assert 'id="advisorReview"' in html
    assert 'id="advisorReviewOperations"' in html
    assert "renderAdvisorReview(manifest, completedJobId)" in script
    assert "/api/v1/automix/advisor-previews/" in script
    assert 'fetch("/api/v1/automix/advisor-feedback"' in script
    assert "shadow_artifact_id: shadow.artifact_id" in script
    assert "operation_index: index" in script
    assert "preview_artifact_id: candidate?.preview_artifact_id" in script
    assert "advisorReviewOperations.replaceChildren()" in script
    review_function = script[script.index("function renderAdvisorReview") : script.index("// 11.")]
    assert ".innerHTML" not in review_function


def test_crm_uses_versioned_retry_safe_enquiry_conversion() -> None:
    script = read_js()
    assert 'api("/api/v1/business/enquiries/conversions"' in script
    assert '"Idempotency-Key": idempotencyKey("enquiry-conversion")' in script


def test_crm_uses_versioned_retry_safe_lead_conversion() -> None:
    script = read_js()
    assert 'api("/api/v1/business/leads/conversions"' in script
    assert '"Idempotency-Key": idempotencyKey("lead-conversion")' in script
    assert "data-convert-lead" in script


def test_crm_uses_versioned_retry_safe_draft_send() -> None:
    script = read_js()
    assert 'api("/api/v1/business/drafts/sends"' in script
    assert '"Idempotency-Key": idempotencyKey("draft-send")' in script
    assert "data-send-draft" in script


def test_crm_queues_reviewed_external_delivery_through_outbox() -> None:
    script = read_js()
    assert 'api("/api/v1/business/draft-deliveries"' in script
    assert '"Idempotency-Key": idempotencyKey("draft-delivery")' in script
    assert "data-queue-draft-delivery" in script
    assert "External email remains policy-controlled" in script


def test_hub_distinguishes_kenn_from_rewrite_status() -> None:
    html = (ROOT / "server" / "app" / "static" / "hub.html").read_text(encoding="utf-8")
    js = (ROOT / "server" / "app" / "static" / "hub.js").read_text(encoding="utf-8")
    assert "Website, Portfolio, Audio_Gen, and KENN services" in html
    assert "Open Audio_Gen" in js
    assert "KENN online" in js
    assert "Retrieval only" in js


def test_dashboard_audiogen_sends_project_id() -> None:
    js = read_js()
    assert "populateAudioGenProjects(data.records.projects || [])" in js
    assert "function selectedAudioGenProject()" in js
    assert "project_id: selectedAudioGenProject()" in js


def test_mix_review_has_direct_kenn_handoff() -> None:
    js = read_js()
    assert "data-ask-kenn-handoff" in js
    assert "data-kenn-context" in js
    assert "data-kenn-prompt" in js
    assert 'showTab("ableton")' in js
    assert "async function askAbleton(question, extraHistory = [])" in js


def test_dashboard_has_music_analysis_tab() -> None:
    html = (ROOT / "server" / "app" / "static" / "dashboard.html").read_text(encoding="utf-8")
    js = read_js()
    assert 'data-tab="music-analysis"' in html
    assert 'data-panel="music-analysis"' in html
    assert 'id="music-analysis-form"' in html
    assert 'id="music-analysis-file"' in html
    assert 'id="music-analysis-result"' in html
    assert "/api/admin/music-analysis" in js
    assert "function renderMusicAnalysis" in js
    assert "Chord Timeline" in js
    assert "Interval Movement" in js


def test_mix_review_surfaces_deeper_diagnostics() -> None:
    html = (ROOT / "server" / "app" / "static" / "dashboard.html").read_text(encoding="utf-8")
    js = read_js()
    assert 'id="mix-review-goal"' in html
    assert 'value="club"' in html
    assert "function renderMixDiagnostics" in js
    assert "function renderGoalTargetChecks" in js
    assert "function renderSourceHypotheses" in js
    assert "function renderFrequencyRepairMap" in js
    assert "function renderLessonCards" in js
    assert "function renderRevisionLesson" in js
    assert "function renderRevisionCoaching" in js
    assert "Deeper diagnostics" in js
    assert "Goal target checks" in js
    assert "Where to look first" in js
    assert "Frequency repair map" in js
    assert "Before/after coaching" in js
    assert "Reference coaching" in js
    assert "reference_coaching" in js
    assert "Educational notes" in js
    assert "Revision lesson" in js
    assert "tonal_balance" in js
    assert "dynamic_profile" in js
    assert "stereo_field" in js
    assert "spectral_features" in js
    assert "goal_target_checks" in js
    assert "source_hypotheses" in js
    assert "frequency_repair_map" in js
    assert 'form.append("mix_goal"' in js


def test_mix_review_dashboard_surfaces_closed_loop_controls() -> None:
    html = (ROOT / "server" / "app" / "static" / "dashboard.html").read_text(encoding="utf-8")
    js = read_js()
    routes = (ROOT / "server" / "app" / "routes" / "mix_review_routes.py").read_text(
        encoding="utf-8"
    )

    assert 'id="mix-review-qa-refresh"' in html
    assert 'id="mix-review-qa-result"' in html
    assert "Catalogue QA" in html
    assert "function renderClosedLoopPanel" in js
    assert "function renderRevisionWorkflow" in js
    assert "function renderQaSummary" in js
    assert 'data-tab="actions"' in js
    assert 'data-panel="actions"' in js
    assert "data-mix-feedback" in js
    assert "/api/admin/mix-review-feedback" in js
    assert "/api/admin/mix-review-qa" in js
    assert "/api/admin/mix-review-repair-chains" in js
    assert "/api/admin/mix-review-feedback" in routes
    assert "/api/admin/mix-review-qa" in routes
    assert "/api/admin/mix-review-repair-chains" in routes


def test_mix_review_feedback_controls_are_not_gated_behind_closed_loop_data() -> None:
    """Regression for a real bug found 2026-07-12: the "Useful"/"Not
    useful"/"Needs work" feedback buttons used to live only inside
    renderClosedLoopPanel(), which returns "" unless a closed-loop action
    plan or repair chain happened to exist for that specific review --
    silently hiding the only feedback UI in the app on every review that
    didn't trigger one. Root-caused while investigating why
    mix_feedback_features' real data was 100% "accepted" and 0% anything
    else. Now renderMixFeedbackControls() is a separate, always-called
    function in the review's default Dashboard tab, independent of
    closed-loop data."""
    js = read_js()
    assert "function renderMixFeedbackControls" in js

    dashboard_tab_start = js.index('data-panel="dashboard">')
    actions_tab_start = js.index('data-panel="actions">')
    feedback_call_index = js.index("${renderMixFeedbackControls(review)}")

    assert dashboard_tab_start < feedback_call_index < actions_tab_start, (
        "renderMixFeedbackControls(review) must be called in the always-visible "
        "Dashboard tab, not inside the conditional Actions/closed-loop panel"
    )

    closed_loop_fn_start = js.index("function renderClosedLoopPanel")
    closed_loop_fn_end = js.index("\n}", closed_loop_fn_start)
    closed_loop_body = js[closed_loop_fn_start:closed_loop_fn_end]
    assert "data-mix-feedback" not in closed_loop_body, (
        "the feedback buttons must not be re-gated behind "
        "renderClosedLoopPanel()'s closed-loop-data early return"
    )


def test_llm_improvement_has_repair_plan_panel() -> None:
    html = (ROOT / "server" / "app" / "static" / "dashboard.html").read_text(encoding="utf-8")
    js = read_js()
    css = (ROOT / "server" / "app" / "static" / "styles.css").read_text(encoding="utf-8")
    assert 'id="lm-repair-plan"' in html
    assert "Repair plan" in html
    assert "function renderRepairPlan" in js
    assert "data.repair_plan" in js
    assert ".lm-repair-plan-item" in css


def test_creative_lab_combines_kenn_and_audiogen_without_merging_portfolio() -> None:
    html = (ROOT / "server" / "app" / "static" / "creative-lab.html").read_text(encoding="utf-8")
    js = (ROOT / "server" / "app" / "static" / "creative-lab.js").read_text(encoding="utf-8")
    css = (ROOT / "server" / "app" / "static" / "styles.css").read_text(encoding="utf-8")
    routes = (
        (ROOT / "server" / "app" / "routes" / "static_routes.py").read_text(
            encoding="utf-8"
        )
        + (ROOT / "server" / "app" / "routes" / "creative_lab_routes.py").read_text(
            encoding="utf-8"
        )
    )

    assert "Audio_Gen" in html
    assert 'id="creative-ask-form"' in html
    assert 'id="creative-audiogen-form"' in html
    assert 'id="creative-history"' in html
    assert 'id="creative-sessions"' in html
    assert 'id="creative-quality"' in html
    assert 'id="creative-repair-quality"' in html
    assert 'id="creative-repair-recommendations"' in html
    assert 'id="creative-repair-queue"' in html
    assert 'id="creative-repair-comparison"' in html
    assert 'id="creative-training-records"' in html
    assert 'id="creative-training-refresh"' in html
    assert 'id="creative-prompt-leaderboard"' in html
    assert 'id="creative-session-replay"' in html
    assert 'id="creative-mix-review-result"' in html
    assert 'id="creative-player"' in html
    assert 'href="/portfolio"' in html
    assert 'href="/creative-lab"' in read_js()
    assert "/api/ableton/ask" in js
    assert "/api/admin/audiogen/generate" in js
    assert "/api/admin/audiogen/render-song" in js
    assert "/api/admin/creative-lab/session" in js
    assert "/api/admin/creative-lab/feedback" in js
    assert "/api/admin/creative-lab/mix-review" in js
    assert "/api/admin/creative-lab/repair" in js
    assert "/api/admin/creative-lab/repair/promote" in js
    assert "/api/admin/creative-lab/repair/promote-eval" in js
    assert "/api/admin/creative-lab/repair/run-recommendation" in js
    assert "/api/admin/creative-lab/repair/export-training" in js
    assert "/api/admin/creative-lab/repair/export-approved-training" in js
    assert "/api/admin/creative-lab/repair/validate-approved-training" in js
    assert "/api/admin/creative-lab/repair/training-records" in js
    assert "/api/admin/creative-lab/repair/review-training-record" in js
    assert "/api/admin/creative-lab/repair/comparison" in js
    assert "Create repair draft" in js
    assert "Promote repair" in js
    assert "Add to regression suite" in js
    assert "Export repair training" in js
    assert "Export approved only" in js
    assert "Validate approved export" in js
    assert "validation passed" in js
    assert "exportApprovedRepairTraining" in js
    assert "approved export ready" in js
    assert "no approved export yet" in js
    assert "renderTrainingRecords" in js
    assert "creative-training-record" in js
    assert "data-review-training-record" in js
    assert "reviewTrainingRecord" in js
    assert "renderRepairComparison" in js
    assert "Repair run history" in js
    assert "Source ranking report" in js
    assert "Repair note rank" in js
    assert "renderQualityMetrics" in js
    assert "repair pass rate" in js
    assert "top-3 repair source rate" in js
    assert "regressions added" in js
    assert "renderRepairRecommendations" in js
    assert "Repair recommendations" in js
    assert "Run next safe step" in js
    assert "renderRepairQueue" in js
    assert "renderPromptLeaderboard" in js
    assert "renderSessionReplay" in js
    assert "Send to Mix Review" in js
    assert "Good idea" in js
    assert "Wrong direction" in js
    assert "Bad source" in js
    assert "Publish to portfolio" in html
    assert ".creative-grid" in css
    assert ".creative-replay-step" in css
    assert ".creative-compare-grid" in css
    assert ".creative-repair-timeline" in css
    assert ".creative-ranking-report" in css
    assert ".creative-recommendation-list" in css
    assert '"/creative-lab"' in routes
    assert 'path == "/api/admin/creative-lab/repair"' in routes
    assert 'path == "/api/admin/creative-lab/repair/promote"' in routes
    assert 'path == "/api/admin/creative-lab/repair/promote-eval"' in routes
    assert 'path == "/api/admin/creative-lab/repair/run-recommendation"' in routes
    assert 'path == "/api/admin/creative-lab/repair/export-training"' in routes
    assert 'path == "/api/admin/creative-lab/repair/export-approved-training"' in routes
    assert 'path == "/api/admin/creative-lab/repair/validate-approved-training"' in routes
    assert 'path == "/api/admin/creative-lab/repair/training-records"' in routes
    assert 'path == "/api/admin/creative-lab/repair/review-training-record"' in routes
    assert 'path == "/api/admin/creative-lab/repair/comparison"' in routes


def test_automix_surfaces_ltas_spectrum_visualizer() -> None:
    static_dir = ROOT / "server" / "app" / "static"
    html = (static_dir / "automix.html").read_text(encoding="utf-8")
    script = (static_dir / "automix.js").read_text(encoding="utf-8")

    assert 'id="spectrumVisualizerSection"' in html
    assert 'id="spectrumSvg"' in html
    assert 'id="spectrumTooltips"' in html
    assert "renderSpectrumComparison(manifest)" in script
    assert "Math.log10(f / 20)" in script
    assert "renderSpectrumComparison(manifest)" in script
