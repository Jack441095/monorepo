"""The ordered rule stages of the deliberate Ableton parser.

``live_intent._parse_request_rules`` is a flat if/elif chain whose order is the
behaviour: on a single chain, which rule matches first decides the parse, so
"set the hats quieter" landing on ``set_volume`` rather than
``set_device_parameter`` is a function of position and nothing else. Splitting
that chain across modules only stays safe if the cross-module order reproduces
the original exactly, which is why the stages live here behind one documented
call sequence instead of a dispatch table.

The order is written out as four sequential calls in ``_parse_request_rules``
rather than kept as a table here. A table would have to be a list because the
chain interleaves these stages with rules that never left the original function,
so the call site and the table could disagree. Sequential calls cannot.

Each stage returns the finished intent dictionary, or ``None`` to mean "no rule
here matched, carry on". The dictionary is built once by the caller and passed in,
so a stage mutates the same object the flat chain mutated.

The stage modules import the pattern vocabulary from ``kenn.core.live_intent``, so
``_parse_request_rules`` imports them from inside its own body: reaching this
package from the top of ``live_intent`` would ask for patterns that module has not
defined yet.
"""

from __future__ import annotations

from kenn.core.live_intent_rules.device_rules import resolve_device_rules
from kenn.core.live_intent_rules.refusals import refuse_unsafe
from kenn.core.live_intent_rules.session_rules import resolve_session_rules
from kenn.core.live_intent_rules.track_values import resolve_track_values

__all__ = [
    "refuse_unsafe",
    "resolve_device_rules",
    "resolve_session_rules",
    "resolve_track_values",
]