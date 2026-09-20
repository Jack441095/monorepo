"""Event catalog registry — mirrors PRODUCT_ANALYTICS_EVENT_CATALOG.md V1."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PrivacyLevel(str, Enum):
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"


L0 = "L0"


class Product(str, Enum):
    SLO = "slo"
    KENN = "kenn"
    THURSDAY = "thursday"
    WEBSITE = "website"
    PLATFORM = "platform"


SEARCH_MODES = frozenset({"text", "filter", "similar", "hybrid"})
RESULT_COUNT_BUCKETS = frozenset({"0", "1-10", "11-50", ">50"})
LATENCY_BUCKETS = frozenset({"<50", "50-200", "200-1000", ">1000"})
FILE_COUNT_BUCKETS = frozenset({"<1k", "1k-10k", "10k-100k", ">100k"})
CONFIDENCE_BUCKETS = frozenset({"high", "med", "low"})
ISSUE_TYPES = frozenset(
    {
        "level_imbalance",
        "freq_masking",
        "dynamics_overload",
        "stereo_narrow",
        "mono_compatibility",
        "phase",
        "harshness",
        "mud",
        "other",
    }
)
ALERT_KINDS = frozenset({"watcher", "daw", "health", "security"})
RISK_CLASSES = frozenset({"low", "medium", "high"})
APPROVAL_RESPONSES = frozenset({"approved", "denied", "deferred"})
DATA_GAP_CLASSES = frozenset(
    {"credentials", "files_unavailable", "service_offline", "ambiguous_request"}
)
BLOCK_REASON_CLASSES = frozenset({"missing_data", "permission", "dependency", "external_down"})
WEB_TIERS = frozenset({"slo", "bundle"})
DOC_AREAS = frozenset({"getting_started", "licensing", "faq", "api"})
SUPPORT_TOPICS = frozenset({"license", "install", "bug", "other"})
OS_CLASSES = frozenset({"macOS", "Windows"})


@dataclass(frozen=True)
class EventSpec:
    action: str
    product: Product
    privacy_level: PrivacyLevel
    params: tuple[tuple[str, frozenset[str]], ...]

    @property
    def param_map(self) -> dict[str, frozenset[str]]:
        return dict(self.params)


def _spec(
    action: str,
    product: Product,
    level: PrivacyLevel = PrivacyLevel.L2,
    **params: frozenset[str],
) -> EventSpec:
    return EventSpec(
        action=action, product=product, privacy_level=level, params=tuple(params.items())
    )


CATALOG: dict[str, EventSpec] = {
    spec.action: spec
    for spec in (
        # --- SLO ---
        _spec("slo.library.first_added", Product.SLO, library_count_bucket=frozenset({"1", "2-5", "6+"})),
        _spec("slo.scan.started", Product.SLO, file_count_bucket=FILE_COUNT_BUCKETS, scan_kind=frozenset({"initial", "incremental", "manual"})),
        _spec("slo.scan.completed", Product.SLO, duration_bucket_s=frozenset({"<10", "10-60", "60-300", ">300"}), indexed_count_bucket=FILE_COUNT_BUCKETS),
        _spec("slo.scan.failed", Product.SLO, file_count_bucket=FILE_COUNT_BUCKETS, scan_kind=frozenset({"initial", "incremental", "manual"})),
        _spec("slo.search.executed", Product.SLO, search_mode=SEARCH_MODES, result_count_bucket=RESULT_COUNT_BUCKETS, latency_bucket_ms=LATENCY_BUCKETS),
        _spec("slo.search.no_result", Product.SLO, search_mode=SEARCH_MODES),
        _spec("slo.search.result_auditioned", Product.SLO, time_to_audition_bucket_ms=frozenset({"<500", "500-2000", ">2000"}), position_in_results_bucket=frozenset({"1-5", "6-20", ">20"})),
        _spec("slo.similar.requested", Product.SLO, seed_confidence_bucket=CONFIDENCE_BUCKETS),
        _spec("slo.complement.requested", Product.SLO, seed_confidence_bucket=CONFIDENCE_BUCKETS),
        _spec("slo.favorite.toggled", Product.SLO, direction=frozenset({"on", "off"})),
        _spec("slo.daw.drag_export", Product.SLO, target_class=frozenset({"daw", "finder_export", "clipboard"}), drag_latency_bucket_ms=frozenset({"<250", "250-1000", ">1000"})),
        _spec("slo.classification.corrected", Product.SLO, category_from=frozenset({"kick", "snare", "vocal", "bass", "pad", "fx"}), category_to=frozenset({"kick", "snare", "vocal", "bass", "pad", "fx"}), model_confidence_bucket=CONFIDENCE_BUCKETS),
        _spec("slo.classification.ood_interaction", Product.SLO, interaction=frozenset({"viewed_detail", "overrode_anyway", "dismissed"}), uncertainty_bucket=frozenset({"high", "med"})),
        _spec("slo.perf.sampled", Product.SLO, PrivacyLevel.L3, cpu_pct_bucket=frozenset({"<25", "25-50", "50-80", ">80"}), ui_freeze_max_ms_bucket=frozenset({"<250", "250-1000", ">1000"})),
        # --- KENN ---
        _spec("kenn.analysis.completed", Product.KENN, analysis_scope=frozenset({"full_mix", "stems", "region"}), track_count_bucket=frozenset({"1-8", "9-32", ">32"}), duration_bucket_s=frozenset({"<5", "5-30", ">30"})),
        _spec("kenn.analysis.issue_detected", Product.KENN, issue_type=ISSUE_TYPES, count_bucket=frozenset({"1", "2-5", ">5"}), confidence_bucket=CONFIDENCE_BUCKETS),
        _spec("kenn.recommendation.shown", Product.KENN, issue_type=ISSUE_TYPES, evidence_attached=frozenset({"true", "false"})),
        _spec("kenn.evidence.viewed", Product.KENN, issue_type=ISSUE_TYPES, view_duration_bucket_ms=frozenset({"<2k", "2k-10k", ">10k"})),
        _spec("kenn.proposal.accepted", Product.KENN, proposal_family=frozenset({"eq", "comp", "gain", "pan", "other"}), param_count_bucket=frozenset({"1", "2-4", ">4"})),
        _spec("kenn.proposal.rejected", Product.KENN, proposal_family=frozenset({"eq", "comp", "gain", "pan", "other"}), param_count_bucket=frozenset({"1", "2-4", ">4"})),
        _spec("kenn.automix.previewed", Product.KENN, change_count_bucket=frozenset({"1-3", "4-10", ">10"}), preview_latency_bucket_ms=frozenset({"<500", "500-2000", ">2000"})),
        _spec("kenn.automix.applied", Product.KENN, change_count_bucket=frozenset({"1-3", "4-10", ">10"}), undo_armed=frozenset({"true", "false"})),
        _spec("kenn.automix.rejected", Product.KENN, change_count_bucket=frozenset({"1-3", "4-10", ">10"})),
        _spec("kenn.automix.undone", Product.KENN, time_to_undo_bucket_min=frozenset({"<1", "1-10", ">10"})),
        _spec("kenn.feedback.false_positive", Product.KENN, issue_type=ISSUE_TYPES, confidence_bucket=CONFIDENCE_BUCKETS),
        # --- Thursday ---
        _spec("thu.brief.opened", Product.THURSDAY, brief_section_count_bucket=frozenset({"1-3", "4-6", ">6"}), open_hour_utc_bucket=frozenset({"0-5", "6-11", "12-17", "18-23"})),
        _spec("thu.brief.blocked_task_surfaced", Product.THURSDAY, block_reason_class=BLOCK_REASON_CLASSES),
        _spec("thu.capability.succeeded", Product.THURSDAY, capability_id=frozenset({"audio.mix.analyze", "util.library.search", "biz.summary"}), duration_bucket_ms=frozenset({"<250", "250-1000", "1-5k", ">5k"})),
        _spec("thu.capability.failed", Product.THURSDAY, capability_id=frozenset({"audio.mix.analyze", "util.library.search", "biz.summary"})),
        _spec("thu.approval.responded", Product.THURSDAY, risk_class=RISK_CLASSES, approval_response=APPROVAL_RESPONSES, decision_latency_bucket_ms=frozenset({"<2k", "2k-30k", ">30k"})),
        _spec("thu.delegation.completed", Product.THURSDAY, agent_id=frozenset({"research_agent", "ops_agent"}), step_count_bucket=frozenset({"1-3", "4-10", ">10"})),
        _spec("thu.delegation.failed", Product.THURSDAY, agent_id=frozenset({"research_agent", "ops_agent"})),
        _spec("thu.task.missing_data_response", Product.THURSDAY, data_gap_class=DATA_GAP_CLASSES),
        _spec("thu.alert.dismissed", Product.THURSDAY, alert_kind=ALERT_KINDS, age_bucket_h=frozenset({"<1", "1-24", ">24"})),
        _spec("thu.alert.marked_useful", Product.THURSDAY, alert_kind=ALERT_KINDS),
        # --- Website (cookieless aggregates, no session ids) ---
        _spec("web.landing.view", Product.WEBSITE, PrivacyLevel.L1, entry_path_class=frozenset({"root", "campaign"})),
        _spec("web.product.view", Product.WEBSITE, PrivacyLevel.L1, from_page_class=frozenset({"landing", "nav", "pricing", "docs"})),
        _spec("web.pricing.view", Product.WEBSITE, PrivacyLevel.L1, price_tier_focus=WEB_TIERS),
        _spec("web.checkout.started", Product.WEBSITE, PrivacyLevel.L1, tier=WEB_TIERS),
        _spec("web.checkout.completed", Product.WEBSITE, PrivacyLevel.L1, tier=WEB_TIERS),
        _spec("web.account.created", Product.WEBSITE, PrivacyLevel.L1, flow=frozenset({"pre_purchase", "post_purchase"})),
        _spec("web.download.started", Product.WEBSITE, PrivacyLevel.L1, os_class=OS_CLASSES, channel=frozenset({"direct", "account"})),
        _spec("web.docs.viewed", Product.WEBSITE, PrivacyLevel.L1, doc_area=DOC_AREAS),
        _spec("web.support.opened", Product.WEBSITE, PrivacyLevel.L1, topic_class=SUPPORT_TOPICS),
        # --- Diagnostics (shared L3 shapes) ---
        _spec("diag.crash", Product.PLATFORM, PrivacyLevel.L3, thread_category=frozenset({"main", "audio", "index", "network"}), app_phase=frozenset({"startup", "scan", "search", "playback", "shutdown"})),
    )
}
