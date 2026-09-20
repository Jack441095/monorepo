"""Pure, deterministic recommendation gate for KENN V2-B evaluation only."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum


class RecommendationState(StrEnum):
    NO_ACTION_RECOMMENDED = "no_action_recommended"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    CONTEXT_REQUIRED = "context_required"
    OBSERVATION_ONLY = "observation_only"
    RECOMMENDATION_JUSTIFIED = "recommendation_justified"


class GateAction(StrEnum):
    ABSTAIN = "abstain"
    OBSERVE = "observe"
    RECOMMEND = "recommend"
    STRONG_RECOMMEND = "strong_recommend"


@dataclass(frozen=True)
class IssueCandidate:
    issue_type: str
    score: float                 # calibrated score in [0, 1]
    severity: str
    evidence_kind: str = "measured"
    persistent: bool = True
    confounders: tuple[str, ...] = ()
    scope: str = "mix"


@dataclass(frozen=True)
class GateDecision:
    issue_type: str
    state: RecommendationState
    action: GateAction
    reason: str
    confidence: float

    def payload(self) -> dict:
        return asdict(self) | {"state": self.state.value, "action": self.action.value}


OBJECTIVE = {"clipping", "headroom", "dc", "lr_imbalance", "anti_phase", "wide_bass"}
CONTEXT_SENSITIVE = {"bass_excess", "mud", "harshness", "resonance", "over_compression", "transient_peaks"}
CONFUSABLE = {"intentional_bright", "intentional_dark", "intentional_saturation", "intentional_panning", "very_short", "near_silence", "test_signal"}


def decide(candidate: IssueCandidate, config: dict) -> GateDecision:
    """Side-effect-free policy. A measurement can never bypass this gate."""
    rules = config["detectors"].get(candidate.issue_type, config["default"])
    score = min(1.0, max(0.0, candidate.score))
    relevant_confounders = set(candidate.confounders) & CONFUSABLE
    if candidate.evidence_kind != "measured":
        return GateDecision(candidate.issue_type, RecommendationState.INSUFFICIENT_EVIDENCE, GateAction.ABSTAIN,
                            "Candidate lacks deterministic measured evidence.", score)
    if "very_short" in relevant_confounders or "near_silence" in relevant_confounders:
        return GateDecision(candidate.issue_type, RecommendationState.INSUFFICIENT_EVIDENCE, GateAction.ABSTAIN,
                            "Duration or level is insufficient for a stable mix-wide judgment.", score)
    if candidate.issue_type in CONTEXT_SENSITIVE and relevant_confounders:
        return GateDecision(candidate.issue_type, RecommendationState.CONTEXT_REQUIRED, GateAction.ABSTAIN,
                            "A known musical/contextual confounder prevents a corrective conclusion.", score)
    if not candidate.persistent and candidate.issue_type in CONTEXT_SENSITIVE:
        return GateDecision(candidate.issue_type, RecommendationState.OBSERVATION_ONLY, GateAction.OBSERVE,
                            "The condition is not persistent enough for mix-wide corrective advice.", score)
    if score < rules["observe"]:
        return GateDecision(candidate.issue_type, RecommendationState.NO_ACTION_RECOMMENDED, GateAction.ABSTAIN,
                            "No material issue exceeds the calibrated observation boundary.", score)
    if score < rules["recommend"]:
        return GateDecision(candidate.issue_type, RecommendationState.OBSERVATION_ONLY, GateAction.OBSERVE,
                            "Measured deviation is near the boundary; inspect in context before changing it.", score)
    if score < rules["strong"]:
        return GateDecision(candidate.issue_type, RecommendationState.RECOMMENDATION_JUSTIFIED, GateAction.RECOMMEND,
                            "Persistent measured deviation exceeds the calibrated intervention boundary.", score)
    return GateDecision(candidate.issue_type, RecommendationState.RECOMMENDATION_JUSTIFIED, GateAction.STRONG_RECOMMEND,
                        "Persistent measured deviation is severe and meets the strong-intervention boundary.", score)
