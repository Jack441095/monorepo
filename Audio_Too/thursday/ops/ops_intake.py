"""Shared parser for the Thursday Ops upgrade's pipe-delimited structured
intake commands (marketing plans, ad campaign plans, and any future one
of the same shape).

Syntax: ``<prefix> <objective> | <field>: <value> | <field>: <value> ...``

e.g. ``create marketing plan: Prepare Submit launch content | audience:
beta testers and early adopters | channels: website, linkedin``

Deliberately not a general-purpose parsing framework -- just the one
pattern these commands actually share, factored out once a second real
caller (thursday.ops.advertising_ops) needed the identical logic
thursday.ops.marketing_ops already had. See task_ledger.py's simpler
colon-only parser for the (different, single-field) task-creation
command, which doesn't need this.
"""

from __future__ import annotations


def parse_structured_command(
    text: str,
    prefixes: list[str],
    field_aliases: dict[str, str],
    list_fields: set[str],
) -> tuple[str, dict] | None:
    """Returns (objective, fields) if ``text`` starts with one of
    ``prefixes`` (case-insensitive), else None. Raises ValueError if the
    prefix matches but the objective (the text between the prefix and the
    first ``|``) is empty -- a real error, not a routing miss.

    ``field_aliases`` maps a lowercased "key" (as typed after ``|``, before
    the next ``:``) to a canonical field name; unrecognized keys are
    silently ignored (typos in an optional field shouldn't hard-fail plan
    creation). ``list_fields`` names which canonical fields should be
    split on ``,`` into a list rather than kept as a single string.
    """
    stripped = text.strip()
    lower = stripped.lower()
    matched_prefix = next((p for p in prefixes if lower.startswith(p.lower())), None)
    if matched_prefix is None:
        return None

    rest = stripped[len(matched_prefix):]
    parts = [seg.strip() for seg in rest.split("|")]
    objective = parts[0] if parts else ""
    if not objective:
        raise ValueError("empty objective")

    fields: dict = {}
    for seg in parts[1:]:
        if ":" not in seg:
            continue
        key, _, value = seg.partition(":")
        canonical = field_aliases.get(key.strip().lower())
        if not canonical:
            continue
        value = value.strip()
        if canonical in list_fields:
            fields[canonical] = [v.strip() for v in value.split(",") if v.strip()]
        else:
            fields[canonical] = value

    return objective, fields
