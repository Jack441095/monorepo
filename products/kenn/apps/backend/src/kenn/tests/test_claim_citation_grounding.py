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
    _FABRICATED_ATTRIBUTION,
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

QUERY = "What release time should I use for sidechain compression on bass?"
SIDECHAIN_ID = get_chunk_id(SIDECHAIN_NOTE)
CLEANING_ID = get_chunk_id(CLEANING_NOTE)


def validate(answer: str) -> dict:
    return generated_answer_validation(
        QUERY,
        RESULTS,
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
