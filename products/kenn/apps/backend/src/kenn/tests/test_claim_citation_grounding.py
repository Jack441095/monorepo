"""Every number in an answer has to name the excerpt it came from, and that excerpt has to hold it.

Across two independent 29-query runs on 2 Oct 2026, unsupported measurements accounted for 8 of 9 rejections and
then 5 of 7. The only other one was an answer claiming it had changed the Live set. So the failure is one thing
precisely: the model writes a figure the notes never contained, and the gate can only notice after the fact and
throw the whole answer away.

These tests pin the claim-level check that replaced that. The model is asked to tag every number with the id of
the excerpt it came from, the excerpt tag now carries that id, and generated_answer_validation() checks the cited
chunk's own body for the value. A wrong number is then caught at the claim and can be repaired, rather than
poisoning an otherwise good answer.
"""

from __future__ import annotations

import re

from kenn.core.chat_grounding import (
    _AMBIGUOUSLY_ATTRIBUTED,
    _CITATION_AGREES,
    _CITATION_CITES_UNSHOWN_ID,
    _CITATION_MISATTRIBUTES,
    _FABRICATED_ATTRIBUTION,
    _UNATTRIBUTED,
    _UNIQUELY_ATTRIBUTED,
    _UNSHOWN_CITATION,
    explicit_abstain_gap,
    generated_answer_validation,
    verify_claim_citations,
)
from kenn.core.chat_grounding import _evidence_chunks as _shown_for
from kenn.knowledge.reasoning import get_chunk_id
from kenn.llm.llm_rewrite import (
    CLAIM_CITATION_RE,
    STATIC_CORE_SYSTEM_PROMPT,
    SYSTEM_PROMPT_TEMPLATE,
    _build_synthesis_messages,
    build_raw_context_block,
)

# Two chunks from the same note, so a number in one of them can be attributed to the other. That is the mistake
# this whole phase exists to catch: both excerpts are real, both ids were printed, and only the body tells them
# apart.
SIDECHAIN_NOTE = {
    "kind": "note",
    "title": "Sidechain Bass To Kick",
    "source": "sidechain-bass-to-kick.md",
    "topics": ["sidechain", "bass", "compression"],
    "tags": ["sidechain", "ducking", "compression"],
    "status": "Approved",
    "section": "Try this",
    "text": (
        "Put a compressor on the bass bus and key it from the kick. Release around 150 ms so the "
        "bass recovers before the next hit, take 5 ms of attack to let the transient through, and "
        "stop at 6 dB of depth, which is past where it reads as an artefact. A ratio of 4:1 holds "
        "the pumping shallow."
    ),
}
CLEANING_NOTE = {
    "kind": "note",
    "title": "Vocal Cleanup Chain",
    "source": "vocal-cleanup-chain.md",
    "topics": ["de-essing", "vocal", "cleanup"],
    "tags": ["de-esser", "vocal", "chain"],
    "status": "Approved",
    "section": "Order of operations",
    "text": (
        "Gate the breath noise before the compressor, not after, and duck the send to the "
        "reverb to 12% while the de-esser works above 6 kHz."
    ),
}
RESULTS = [(1030.88, SIDECHAIN_NOTE), (980.11, CLEANING_NOTE)]

# Two excerpts that both state 250 ms, which is what an ambiguous attribution looks like from the gate's side: the
# figure is grounded either way, so nothing in the existing eight conditions can fire on it, and there is no single
# passage it came from. The 6 dB sits in only one of the two and the 45% in neither, so all three classes come out
# of one fixture pair. Room-note audio figures are deliberately the ones _MEASUREMENT_RE recognises.
ROOM_NOTE = {
    "kind": "note",
    "title": "Vocal Booth Treatment",
    "source": "vocal-booth-treatment.md",
    "topics": ["room", "vocal", "treatment"],
    "tags": ["room", "booth", "absorb"],
    "status": "Approved",
    "section": "Treatment",
    "text": (
        "Absorb the first reflection points and high-pass the room mic before the compressor, "
        "then pull the vocal up 6 dB once the room is under control. A 250 ms decay reads as "
        "controlled from the listening position."
    ),
}
CONTROL_NOTE = {
    "kind": "note",
    "title": "Control Room Monitoring",
    "source": "control-room-monitoring.md",
    "topics": ["monitoring", "room", "level"],
    "tags": ["monitoring", "level", "trim"],
    "status": "Approved",
    "section": "Trim",
    "text": (
        "A 250 ms decay is where a small treated room stops sounding boxy on the low end. Trim "
        "against the untreated bounce rather than against the reference."
    ),
}
ROOM_RESULTS = [(1012.4, ROOM_NOTE), (975.2, CONTROL_NOTE)]

QUERY = "What release time should I use for sidechain compression on bass?"
SIDECHAIN_ID = get_chunk_id(SIDECHAIN_NOTE)
CLEANING_ID = get_chunk_id(CLEANING_NOTE)
ROOM_ID = get_chunk_id(ROOM_NOTE)
CONTROL_ID = get_chunk_id(CONTROL_NOTE)


def validate(answer: str) -> dict:
    return generated_answer_validation(
        QUERY,
        RESULTS,
        answer,
        route="production",
        confidence="high",
        answer_mode="mix_diagnosis",
    )


def validate_room(answer: str) -> dict:
    """The same gate over the fixture pair that carries a shared 250 ms.

    The query moves with the fixtures: grounding keys on source-topic match, and asking a room question about the
    sidechain notes would fail that check for a reason that has nothing to do with attribution.
    """
    return generated_answer_validation(
        "How long should the room decay before I high-pass the room mic?",
        ROOM_RESULTS,
        answer,
        route="production",
        confidence="high",
        answer_mode="mix_diagnosis",
    )


def _answer(body: str) -> str:
    return f"Short answer: {body}\n\nTry this:\n1. Do the first thing.\n2. Do the second thing.\n\nCheck: Compare in context.\n"


# The chunk id was not in the prompt before this phase, so a prompt asking for a citation would have been asking
# for something the model cannot produce. These three assertions are the reason the excerpt tag carries an id.
def test_the_excerpt_tag_carries_the_chunk_id_the_rules_block_asks_the_model_to_cite() -> None:
    block = build_raw_context_block(RESULTS, lambda chunk: f"{chunk['title']} ({chunk['source']})")

    assert f'id="{SIDECHAIN_ID}"' in block
    assert f'id="{CLEANING_ID}"' in block
    # The id the model can read has to be the id the gate recomputes, or the check compares two different things.
    assert get_chunk_id(SIDECHAIN_NOTE) == SIDECHAIN_ID


def test_both_prompts_ask_for_the_citation_and_the_abstain_in_the_same_words() -> None:
    """The MLX path runs the static prompt and the chat path the template, so a rule in one is a rule missing in
    the other. They drifted before over answer structure, so the wording is asserted on both."""
    for prompt in (SYSTEM_PROMPT_TEMPLATE, STATIC_CORE_SYSTEM_PROMPT):
        assert "Tag every number you state with the id of the excerpt" in prompt
        assert "Insufficient context:" in prompt
        # The example has to be a real 12-hex id, or the model is shown a shape the gate will not parse.
        example = re.search(r"\[#([0-9a-f]{12})\]", prompt)
        assert example, prompt
        assert CLAIM_CITATION_RE.search(example.group(0)), example.group(0)


def test_the_answer_prompt_reaches_the_model_with_the_ids_in_it() -> None:
    messages, shown = _build_synthesis_messages(
        QUERY, "Short answer: set the release to 150 ms.", RESULTS, None, "",
        lambda chunk: f"{chunk['title']} ({chunk['source']})", lambda _history: [],
    )
    user_message = messages[-1]["content"]

    assert f'id="{SIDECHAIN_ID}"' in user_message
    assert f'id="{CLEANING_ID}"' in user_message
    # The body still holds the figure, so the id did not come out of the budget the measurements live in.
    assert "150 ms" in user_message
    assert len(shown) == len(RESULTS)


def test_a_correctly_cited_number_is_verified_against_its_own_excerpt() -> None:
    result = validate(
        _answer(f"Back the release off to 150 ms [#{SIDECHAIN_ID}] and take 5 ms of attack [#{SIDECHAIN_ID}].")
    )

    citations = result["claim_citations"]
    assert citations["total"] == 2
    assert citations["cited"] == 2
    assert citations["verified"] == 2
    assert citations["uncited"] == 0
    assert citations["fabricated_attributions"] == []
    assert result["accepted"] is True
    assert "generated answer attributes a measurement to an excerpt that does not contain it" \
        not in result["warnings"]


def test_a_ratio_is_not_a_claim_because_the_gate_has_never_tracked_one() -> None:
    """4:1 is the number in the real note and _MEASUREMENT_RE has no unit for a ratio, so a claim count that
    included it would be counting something the aggregate check can never contradict."""
    result = validate(_answer("Hold the ratio at 4:1."))

    assert result["claim_citations"]["total"] == 0


def test_a_number_cited_to_an_excerpt_that_does_not_hold_it_is_a_fabricated_attribution() -> None:
    """150 ms is in one note. The 12% send is in the other. Attributing one to the other is a lie about provenance
    that the aggregate measurement check cannot see, because both numbers are somewhere in the evidence."""
    result = validate(_answer(f"Duck the reverb send to 12% [#{SIDECHAIN_ID}]."))

    citations = result["claim_citations"]
    assert citations["verified"] == 0
    assert [claim["value"] for claim in citations["fabricated_attributions"]] == ["12%"]
    assert citations["fabricated_attributions"][0]["cited_chunk"] == SIDECHAIN_ID
    assert result["accepted"] is False
    assert result["unsupported_measurements"] == [], "12% is real, it is just from the other note"
    assert "generated answer attributes a measurement to an excerpt that does not contain it" in result["warnings"]


def test_an_uncited_number_is_counted_separately_and_is_not_called_verified() -> None:
    """The dominant real failure: a figure that is in the evidence, so the aggregate check passes it, with nothing
    saying which note it came from. Counted, never counted as verified."""
    result = validate(_answer("Back the release off to 150 ms and take 5 ms of attack."))

    citations = result["claim_citations"]
    assert citations["total"] == 2
    assert citations["cited"] == 0
    assert citations["verified"] == 0
    assert citations["uncited"] == 2
    assert all(claim["reason"] == "uncited" for claim in citations["claims"])
    # Still accepted: an uncited number is already covered by the aggregate check when it is invented, and warning
    # on it twice would drop answers that are currently fine for no extra rejection power.
    assert result["accepted"] is True


def test_a_citation_to_an_id_we_never_printed_is_caught() -> None:
    """The case this phase exists for. The number is real and in the evidence, so every check that existed before
    passed it; only the id says the model made the provenance up."""
    result = validate(_answer("Back the release off to 150 ms [#deadbeefcafe]."))

    citations = result["claim_citations"]
    assert citations["cited"] == 1
    assert citations["verified"] == 0
    assert [claim["value"] for claim in citations["unshown_citations"]] == ["150ms"]
    assert citations["unshown_citations"][0]["reason"] == _UNSHOWN_CITATION
    assert result["accepted"] is False
    assert "generated answer cites an excerpt id that was never shown" in result["warnings"]
    assert result["unsupported_measurements"] == [], "the number itself is real, only the attribution is not"


def test_a_malformed_id_is_reported_as_unshown_rather_than_silently_downgraded_to_uncited() -> None:
    """A strict 12-hex pattern would swallow this and hand the claim to the uncited pile, which is the one
    category we are not trying to grow."""
    result = validate(_answer("Back the release off to 150 ms [#sidechain]."))

    assert result["claim_citations"]["unshown_citations"], result["claim_citations"]["claims"]


def test_an_abstain_that_names_the_gap_is_accepted_rather_than_warned_on() -> None:
    """All 36 items in tooling/data/eval_must_abstain_v1.jsonl are meant to produce this, and 12 of them are
    Related-questions echo attacks where the only overlapping chunk holds no figure at all."""
    result = validate("Insufficient context: we hold no note on parallel compression for this bus.")

    assert result["abstained"] is True
    assert result["abstain_gap"] == "we hold no note on parallel compression for this bus."
    assert result["claim_citations"]["total"] == 0
    assert result["accepted"] is True
    assert result["warnings"] == []
    # The reports are still computed, so the branch that clears the warnings hides nothing from a caller.
    assert "score" in result["grounding"] and "score" in result["quality"]


def test_an_abstain_prefix_with_no_gap_named_is_not_an_abstain() -> None:
    assert explicit_abstain_gap("Insufficient context:") == ""
    assert explicit_abstain_gap("Insufficient context:   ") == ""


def test_an_abstain_carrying_a_number_is_not_laundered_into_an_abstain() -> None:
    """The gap-filling shape: the model says the context is thin and then answers anyway. 12 of the 36 must-abstain
    items are exactly this trap, a Related-questions chunk that echoes the question and holds no figure."""
    result = validate("Insufficient context: we hold no note on it, but you want a 45% send.")

    assert result["abstained"] is False
    assert result["abstain_gap"], "the line is still recorded, it just does not buy a pass"
    assert result["claim_citations"]["total"] == 1
    assert result["claim_citations"]["verified"] == 0
    assert "45%" in result["unsupported_measurements"]
    assert result["accepted"] is False


def test_an_abstain_cannot_excuse_a_claim_that_it_changed_the_set() -> None:
    """The one non-numeric rejection in the 29-query runs, and an abstain is not a licence to hand back a receipt
    for a change that never happened."""
    result = validate("Insufficient context: we hold no note on the send.\n\nI've already muted the hats.")

    assert result["abstained"] is True
    assert result["claims_live_change"] is True
    assert result["accepted"] is False
    assert "generated answer claims it changed the Live set" in result["warnings"]


def test_a_citation_written_before_its_number_still_counts() -> None:
    """A model that leads with its source is citing honestly, and the backward pass exists so it is not charged for
    a different word order."""
    result = validate(_answer(f"Set the release to [#{SIDECHAIN_ID}] 150 ms."))

    assert result["claim_citations"]["verified"] == 1
    assert result["accepted"] is True


def test_a_citation_far_past_its_number_does_not_attach_to_it() -> None:
    """80 characters is roughly a clause. Past that the marker is discussing something else, and attaching it would
    let a citation launder an uncited figure into a verified one."""
    filler = " and then level-match the whole thing against the untreated bounce in a proper listening pass"
    result = validate(_answer(f"Back the release off to 150 ms{filler} [#{SIDECHAIN_ID}]."))

    assert result["claim_citations"]["verified"] == 0
    assert result["claim_citations"]["uncited"] == 1


def test_one_citation_is_never_shared_by_two_claims() -> None:
    """Otherwise a single real id at the end of a paragraph would make every number before it look verified."""
    result = validate(_answer(f"Use 150 ms, 5 ms and 6 dB, all from the same note [#{SIDECHAIN_ID}]."))

    citations = result["claim_citations"]
    assert citations["total"] == 3
    assert citations["cited"] == 1
    assert citations["verified"] == 1
    assert citations["uncited"] == 2


def test_the_two_failure_kinds_stay_distinguishable_in_the_reported_counts() -> None:
    """One real id on a wrong number and one invented id on a right number are different defects, and a report
    that collapsed them into a single "cited: no" would not say which to fix."""
    result = validate(_answer(f"Set 12% [#{SIDECHAIN_ID}] and 150 ms [#0123456789ab]."))

    citations = result["claim_citations"]
    assert citations["total"] == 2
    assert citations["verified"] == 0
    assert [claim["value"] for claim in citations["fabricated_attributions"]] == ["12%"]
    assert citations["fabricated_attributions"][0]["reason"] == _FABRICATED_ATTRIBUTION
    assert [claim["value"] for claim in citations["unshown_citations"]] == ["150ms"]
    assert result["warnings"].count(
        "generated answer attributes a measurement to an excerpt that does not contain it"
    ) == 1
    assert result["warnings"].count("generated answer cites an excerpt id that was never shown") == 1


def test_the_validator_reads_the_same_excerpt_bodies_the_prompt_was_built_from() -> None:
    """model_evidence() is the single list both sides read. If the claim check derived its own list it would
    verify a number against a body the model never saw, which is the 3-against-12 seam that took acceptance from
    41% to 27% on 2 Oct."""
    shown = _shown_for(RESULTS)
    report = verify_claim_citations(f"150 ms [#{SIDECHAIN_ID}]", shown)

    assert report["verified"] == 1
    assert SIDECHAIN_ID in {get_chunk_id(chunk) for _score, chunk, _body in shown}


# The citation turned out to be the part the 8B would not do. Measured 2 Oct 2026 on the 36-item must-abstain set:
# 2 of 11 numeric claims carried an excerpt id, 5 of 28 answers carried an explicit "Insufficient context:" line,
# and 82.1% answered anyway. Across all 28 the validator itself was clean, 0 fabricated attributions and 0 invented
# chunk ids. So the tests below do not ask the model for provenance at all: the gate derives which shown body holds
# each number, and the citation is only cross-checked against that.


def test_a_number_in_one_shown_excerpt_is_placed_however_little_the_model_cited() -> None:
    """150 ms is in the sidechain note and nowhere else, so its attribution is determined without any model input.
    This is the claim the citation pass got wrong 9 times out of 11."""
    result = validate(_answer("Back the release off to 150 ms."))

    citations = result["claim_citations"]
    assert citations["total"] == 1
    assert citations["uniquely_attributed"] == 1
    assert citations["ambiguously_attributed"] == 0
    assert citations["unattributed"] == 0
    assert citations["claims"][0]["attribution"] == _UNIQUELY_ATTRIBUTED
    assert citations["claims"][0]["attributed_chunks"] == [SIDECHAIN_ID]
    # Nothing was cited, so the cross-check has nothing to say, and the count says so rather than claiming success.
    assert citations["citation_absent"] == 1
    assert citations["citation_agreed"] == 0
    assert result["accepted"] is True


def test_a_number_in_two_shown_excerpts_is_ambiguous_and_is_not_a_rejection() -> None:
    """250 ms is in both room notes. It is grounded, so no existing warning can fire on it, and inventing one
    would only drop answers the aggregate check already lets through."""
    result = validate_room(_answer("Trim the room to a 250 ms decay."))

    citations = result["claim_citations"]
    assert citations["uniquely_attributed"] == 0
    assert citations["ambiguously_attributed"] == 1
    assert citations["unattributed"] == 0
    assert citations["claims"][0]["attribution"] == _AMBIGUOUSLY_ATTRIBUTED
    # Prompt order, so the first holder is the excerpt the model saw first.
    assert citations["claims"][0]["attributed_chunks"] == [ROOM_ID, CONTROL_ID]
    assert result["unsupported_measurements"] == []
    assert result["accepted"] is True
    # And naming one of the two holders, which is the strongest attribution an answer can carry, buys nothing more.
    assert validate_room(_answer(f"Trim the room to a 250 ms decay [#{ROOM_ID}]."))["warnings"] == result["warnings"]


def test_a_number_no_shown_excerpt_holds_is_unattributed_and_still_lands_in_unsupported_measurements() -> None:
    """The 45% send is in neither room note. The derived class says so, and the existing unsupported-measurements
    condition still rejects on exactly the same number."""
    result = validate_room(_answer("Duck the reverb send to 45%."))

    citations = result["claim_citations"]
    assert citations["unattributed"] == 1
    assert citations["uniquely_attributed"] == 0
    assert citations["claims"][0]["attribution"] == _UNATTRIBUTED
    assert citations["claims"][0]["attributed_chunks"] == []
    assert result["unsupported_measurements"] == ["45%"]
    assert "generated answer introduced unsupported measurements" in result["warnings"]
    assert result["accepted"] is False


def test_one_answer_with_no_citations_still_gets_all_three_classes_from_arithmetic() -> None:
    """The point of the rework: 250 ms sits in both notes, 6 dB in one, 45% in neither, and not one of the three is
    tagged by the model. The four citation buckets sum to total, so a capture can score cooperation separately from
    traceability."""
    result = validate_room(_answer("Trim to 250 ms, pull the vocal up 6 dB and duck the send to 45%."))

    citations = result["claim_citations"]
    assert citations["total"] == 3
    assert citations["uniquely_attributed"] == 1
    assert citations["ambiguously_attributed"] == 1
    assert citations["unattributed"] == 1
    assert citations["cited"] == 0
    assert citations["citation_absent"] == 3
    assert (
        citations["citation_agreed"]
        + citations["citation_contradicted"]
        + citations["citation_absent"]
        + citations["citation_unshown"]
        == citations["total"]
    )
    assert [claim["value"] for claim in citations["claims"]] == ["250ms", "6db", "45%"]


def test_a_citation_naming_an_excerpt_that_does_not_hold_the_number_is_a_misattribution() -> None:
    """12% is in the cleaning note and the model named the sidechain note for it. Both ids were printed, so this is
    a wrong pointer rather than an invented one, and it has to be reported as its own thing."""
    result = validate(_answer(f"Duck the reverb send to 12% [#{SIDECHAIN_ID}]."))

    citations = result["claim_citations"]
    assert citations["citation_contradicted"] == 1
    assert citations["claims"][0]["citation_relation"] == _CITATION_MISATTRIBUTES
    # The derived holders know where it really came from, which the fabricated-attribution list alone cannot say.
    assert citations["claims"][0]["attributed_chunks"] == [CLEANING_ID]
    assert citations["unshown_citations"] == [], "both ids were printed"


def test_an_invented_id_is_reported_apart_from_a_misattribution() -> None:
    """One answer, one wrong pointer and one pointer to nothing. Collapsing them into a single "cited: no" would
    not say which to fix: the first is a claim about provenance, the second is a shape the parser accepted."""
    result = validate(
        _answer(f"Duck the send to 12% [#{SIDECHAIN_ID}] and the release to 150 ms [#0123456789ab].")
    )

    citations = result["claim_citations"]
    relations = {claim["value"]: claim["citation_relation"] for claim in citations["claims"]}
    assert relations["12%"] == _CITATION_MISATTRIBUTES
    assert relations["150ms"] == _CITATION_CITES_UNSHOWN_ID
    assert citations["citation_contradicted"] == 1
    assert citations["citation_unshown"] == 1
    assert citations["citation_absent"] == 0


def test_a_citation_that_agrees_with_the_derived_attribution_is_reported_as_agreement() -> None:
    """Cooperation is still worth recording: the model named the one excerpt that holds 150 ms, and the derived
    holders put it in the same place independently."""
    result = validate(_answer(f"Back the release off to 150 ms [#{SIDECHAIN_ID}]."))

    citations = result["claim_citations"]
    assert citations["citation_agreed"] == 1
    assert citations["claims"][0]["citation_relation"] == _CITATION_AGREES
    assert citations["claims"][0]["cited_chunk"] in citations["claims"][0]["attributed_chunks"]


def test_an_answer_with_no_numbers_reports_zero_counts_instead_of_erroring() -> None:
    """Most abstains and plenty of plain answers carry no figure at all, and an abstain is scored on this path."""
    result = validate(
        "Short answer: gate before you compress.\n\nTry this:\n1. Gate it.\n2. Then duck.\n\nCheck: Listen.\n"
    )

    citations = result["claim_citations"]
    assert citations["total"] == 0
    assert citations["claims"] == []
    assert (
        citations["uniquely_attributed"],
        citations["ambiguously_attributed"],
        citations["unattributed"],
    ) == (0, 0, 0)
    assert (
        citations["citation_agreed"],
        citations["citation_contradicted"],
        citations["citation_absent"],
        citations["citation_unshown"],
    ) == (0, 0, 0, 0)


def test_the_derived_pass_adds_no_warning_of_its_own() -> None:
    """Rejection power is not what is broken: re-scoring every rejection on 2 Oct 2026 found 0 false positives,
    and the failure the gate does have is the 82.1% that answered anyway. A figure placed by arithmetic must not
    start rejecting answers the citation pass would have let through."""
    derived_only = validate(_answer("Back the release off to 150 ms with no tag at all."))
    cited_and_right = validate(_answer(f"Back the release off to 150 ms [#{SIDECHAIN_ID}]."))

    assert derived_only["accepted"] is True
    assert derived_only["warnings"] == cited_and_right["warnings"]
