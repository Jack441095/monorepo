"""Drafted clarify seeds for the C6 command corpus (owner review pending).

The reviewed seeds (``build_kenn_command_training.records``) teach KENN to
refuse unsupported or out-of-range requests, but not the commonest vague
request in the planner holdouts: a target and a direction with no amount
("Vocals louder."), or no clear referent ("Turn it up."). KENN's contract is
to ask, never to guess an amount or a target; these seeds teach that.

They are deliberately written with different idioms and track names from the
evaluation phrasings (``tooling/data/natural_holdout*.jsonl``), so a
fine-tune has to generalise the pattern rather than recall a phrase; the
corpus builder's overlap guard still checks every generated query. The
corpus includes them only with ``--include-drafted``, and every row carries
``source_kind`` so they stay distinguishable until reviewed.

``{t0}``..``{t4}`` are the scenario snapshot's track names.
"""

from __future__ import annotations

from typing import Any

SOURCE_KIND = "claude_drafted_owner_review_pending"

AMOUNT = "How much? Give an amount, for example 2 dB."
PAN = "How far? Give a pan position, for example 20% left."
PARAMETER = "To what value? Give the exact parameter value."
SEND = "How much, and to which return? Give a send level, for example -12 dB to A-Reverb."
VAGUE = "Which exact change should I make? Name the track, the setting and the amount."
REFERENT = "Which track do you mean? Name it, and give an amount if you want a change."

# (record_id, category, query template, clarification)
DRAFTED_CLARIFY_SEEDS: tuple[tuple[str, str, str, str], ...] = (
    ("draft-amount-01", "incomplete", "{t0} needs to come up", AMOUNT),
    ("draft-amount-02", "incomplete", "Bump {t2} a smidge", AMOUNT),
    ("draft-amount-03", "incomplete", "Drop {t1} slightly", AMOUNT),
    ("draft-amount-04", "incomplete", "Can {t3} be a tad softer", AMOUNT),
    ("draft-amount-05", "incomplete", "Raise {t4} somewhat", AMOUNT),
    ("draft-pan-01", "incomplete", "Shift {t0} over to the right a little", PAN),
    ("draft-pan-02", "incomplete", "Pan {t2} somewhere off-centre", PAN),
    ("draft-param-01", "incomplete", "Ease off the ratio on the {t1} Compressor", PARAMETER),
    ("draft-param-02", "incomplete", "Bring the attack down on the {t3} Glue Compressor", PARAMETER),
    ("draft-send-01", "incomplete", "Send {t0} to the reverb a little", SEND),
    ("draft-send-02", "incomplete", "Give {t2} some echo", SEND),
    ("draft-vague-01", "ambiguity", "{t0} sounds thin", VAGUE),
    ("draft-vague-02", "ambiguity", "Warm up {t2}", VAGUE),
    ("draft-vague-03", "ambiguity", "Make {t1} hit harder", VAGUE),
    ("draft-vague-04", "ambiguity", "Clean up the low end on {t2}", VAGUE),
    ("draft-vague-05", "ambiguity", "Brighten the whole thing", VAGUE),
    ("draft-vague-06", "ambiguity", "Glue the drums together", VAGUE),
    ("draft-referent-01", "incomplete", "Bring that one up", REFERENT),
    ("draft-referent-02", "incomplete", "Mute them", REFERENT),
    ("draft-referent-03", "incomplete", "Same again on the other track", REFERENT),
    ("draft-referent-04", "incomplete", "Softer", REFERENT),
)


# Clear commands in varied idioms (C6 run 3). The reviewed seeds have one or
# two examples per track action; the holdouts use slang and fragments.
# (record_id, query template, action, track index, fields). Volume is stated
# in dB, as the planner may now do (KENN converts); pan uses percent / 100.
DRAFTED_ACTION_SEEDS: tuple[tuple[str, str, str, int, dict[str, Any]], ...] = (
    ("draft-mute-01", "Kill {t1}", "set_mute", 1, {"value": True, "unit": "boolean"}),
    ("draft-mute-02", "Silence {t2} for now", "set_mute", 2, {"value": True, "unit": "boolean"}),
    ("draft-mute-03", "{t0} off", "set_mute", 0, {"value": True, "unit": "boolean"}),
    ("draft-mute-04", "Bring {t3} back in", "set_mute", 3, {"value": False, "unit": "boolean"}),
    ("draft-mute-05", "Unmute {t4}", "set_mute", 4, {"value": False, "unit": "boolean"}),
    ("draft-solo-01", "Let me hear {t1} on its own", "set_solo", 1, {"value": True, "unit": "boolean"}),
    ("draft-solo-02", "Solo out {t2}", "set_solo", 2, {"value": True, "unit": "boolean"}),
    ("draft-solo-03", "Unsolo {t0}", "set_solo", 0, {"value": False, "unit": "boolean"}),
    ("draft-solo-04", "Take the solo off {t3}", "set_solo", 3, {"value": False, "unit": "boolean"}),
    ("draft-vol-01", "{t2} up 2 dB", "set_volume", 2, {"value": 2.0, "unit": "dB", "relative": True}),
    ("draft-vol-02", "Nudge {t0} down 1.5 dB", "set_volume", 0, {"value": -1.5, "unit": "dB", "relative": True}),
    ("draft-vol-03", "Take 4 dB off {t1}", "set_volume", 1, {"value": -4.0, "unit": "dB", "relative": True}),
    ("draft-vol-04", "Put {t3} at minus 12 dB", "set_volume", 3, {"value": -12.0, "unit": "dB"}),
    ("draft-vol-05", "{t4} to -6", "set_volume", 4, {"value": -6.0, "unit": "dB"}),
    ("draft-vol-06", "Boost {t1} by 3 dB", "set_volume", 1, {"value": 3.0, "unit": "dB", "relative": True}),
    ("draft-pan-03", "{t0} hard left", "set_pan", 0, {"value": -1.0, "unit": "normalized"}),
    ("draft-pan-04", "Hard right on {t2}", "set_pan", 2, {"value": 1.0, "unit": "normalized"}),
    ("draft-pan-05", "Centre {t3}", "set_pan", 3, {"value": 0.0, "unit": "normalized"}),
    ("draft-pan-06", "Pan {t1} 40% left", "set_pan", 1, {"value": -0.4, "unit": "normalized"}),
)


def drafted_records(snapshot: dict[str, Any], plan: Any) -> list[dict[str, Any]]:
    """Seed rows in the reviewed seeds' shape, filled with this snapshot's track names."""
    names = {f"t{index}": track["name"] for index, track in enumerate(snapshot["tracks"][:5])}
    rows = [
        {"record_id": record_id, "category": category, "query": template.format(**names),
         "label": plan("clarify", clarification=clarification), "source_kind": SOURCE_KIND}
        for record_id, category, template, clarification in DRAFTED_CLARIFY_SEEDS
    ]
    rows += [
        {"record_id": record_id, "category": "supported_control", "query": template.format(**names),
         "label": plan(action, track_index=index, track_name=names[f"t{index}"], **fields), "source_kind": SOURCE_KIND}
        for record_id, template, action, index, fields in DRAFTED_ACTION_SEEDS
    ]
    return rows


__all__ = ["DRAFTED_ACTION_SEEDS", "DRAFTED_CLARIFY_SEEDS", "SOURCE_KIND", "drafted_records"]
