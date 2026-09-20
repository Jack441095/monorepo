# KENN Next Milestone Build Prompt

## Objective

Finish qualification of the first GLM-like Ableton workflow: a user enters a
natural-language Live command, KENN resolves the exact current
track/device/parameter, shows a reversible proposal, waits for explicit
confirmation, applies one bounded change or one explicit compound EQ edit,
reads it back, and returns an undo-capable receipt.

## Scope for this milestone

- Support existing EQ Eight band-gain requests such as:
  `reduce amplitude by 3 dB at 200 Hz on track 4 band 1B`.
- Support explicit compound EQ requests such as:
  `retune EQ Eight band 1A to 300 Hz and reduce gain by 3 dB on track 4`.
  The proposal must show frequency and gain before/after values and both
  writes must be verified by readback.
- A frequency-only request may proceed only when exactly one band matches;
  otherwise KENN must list the available bands and ask for an explicit band.
- If the requested frequency is not configured, KENN must clarify rather than
  retune a nearby band implicitly. For example, `250 Hz` must remain a safe
  clarification when no band is tuned to 250 Hz.
- Resolve only an EQ Eight that exists exactly once on the requested track.
- Resolve only a band whose inspected frequency is an unambiguous match for the
  requested frequency. Never silently choose a nearby band.
- Change the gain parameter through `LiveActionService`, preserving the
  existing confirmation token, stale-state check, idempotency, readback, and
  receipt/undo guarantees.
- Support `add EQ on track N` only as an append-only, allow-listed EQ Eight
  proposal with explicit confirmation, post-insert identity check, and
  identity-bound rollback.
- Add deterministic fake-Live tests for proposal-only behavior, confirmation,
  readback, ambiguity, missing EQ Eight, and no-write guarantees.
- Run the focused Python suite and the existing C++/real-Live qualification
  checks where the local Ableton session is available.

## Non-goals

- No implicit or compound device insertion; every insertion remains an
  explicit proposal and confirmation.
- No implicit multi-band EQ edits; compound commands must name one exact band.
- No direct LLM write path: an LLM may suggest a structured plan, but the
  snapshot-bound command gateway remains the authority.
- No bypass of the KENN confirmation or receipt boundary.

## Acceptance criteria

1. A recognized EQ request produces a proposal and performs zero writes before
   confirmation.
2. Confirmation changes exactly one inspected EQ Eight gain parameter.
3. Live readback must verify the requested value before KENN reports success.
4. A missing, duplicate, or frequency-mismatched target produces a
   clarification and performs zero writes.
5. The response identifies the one-based user track number, Live track name,
   EQ device, band, frequency, before/after gain, and receipt ID when applied.
6. Device insertion remains limited to the exact allow-listed EQ Eight and
   refuses duplicate or stale targets without writing.

## Current real-Live finding

The disposable Live 12 set now returns compact EQ telemetry with original Live
parameter indices and visible Hz. The real server and compiled C++ client both
produce the exact proposal for `4-Audio / EQ Eight / band 1A / 300 Hz / gain
0 dB → -3 dB`. Real confirmation, two-parameter readback, replay rejection,
and reversible undo have now passed, with the original values restored. Real
append-only insertion has also passed the same lifecycle on disposable
`3-Audio`, which is back to an empty device list.

This milestone is complete. The next milestone is broader device coverage:
inspect a device's live parameter map, select one exact reversible control,
and qualify the same lifecycle for each supported device family and Live/OS
combination. Keep the command planner above this deterministic boundary.

Implement the smallest vertical slice that satisfies these criteria, then
report the files changed, tests run, and any real-Live limitation separately.
