# KENN Ableton Assistant Readiness Report — 2026-09-01 (current addendum 2026-09-08)

## Decision: supervised pilot ready; qualified beta not ready

Current 2026-09-10 evidence supersedes the historical counts below. The
release-scoped Python regression suite passes **1,162 tests**. The qualified
release gate currently has **7 passed, 1 failed, and 6 pending** gates. The
failed gate is the stale real-Live assistant receipt, bound to an older
source/planner revision; it needs a fresh Ableton-enabled qualification.
Pending gates require genuine external or elapsed-time evidence: independent
human review/adjudication; signed, notarized, clean-host-validated plug-ins;
the reconnect-aware soak; consented real-mix review; the ten-session pilot;
and final provenance once those artifacts exist. A fresh `--check-live` run
remains mandatory immediately before an actual supervised session.

The installed universal AU passed Apple `auval`; the installed VST3 passed
pluginval at strictness 5 and 10. Ableton Live 12.4.5 also discovered,
instantiated, and cleanly removed both formats in an unsaved disposable set on
macOS 26.6.2; this is current host evidence, not an automatic expansion of the
26.5.2 support-matrix entry. KENN now also measures BS.1770-4 integrated
LUFS/LRA and 4x-oversampled true peak with explicit dependency/input
abstention. Those are locally reference-tested measurements, not substitutes
for the still-required independent real-mix review.

Runtime-state hardening now bounds the Live planner to 1,000 unexpired pending
proposals and the persistent Mix Review registry to 500 metadata-only receipts
(with mode-`0600` atomic writes). This closes the remaining obvious unbounded
growth in those beta-facing registries.

### Historical 2026-09-01 baseline

KENN is useful for internal local development: it can answer grounded audio-production questions, analyse supported PCM WAV files with measured time/stereo/FFT evidence, and construct guarded Ableton proposals. The deterministic Ableton boundary/coverage holdout passes 108/108 with precision/recall/F1 and clarification/abstention/refusal accuracy of 1.00; the public chat coverage fixture passes 128/128 (84 answer cases and 44 expected abstentions); the broader repository suite passes 213 tests; and the VST3 project builds in the available local tree.

The 213-test figure in that baseline sentence is historical. The latest
verified full suite on 2026-09-03 passes 262 tests.

The latest Mix Review benchmark detects the synthetic fault set with 100%
precision and recall, 0% false positives, 100% corrupted-input recovery, and
3.40 ms mean latency against the documented <100 ms target. The evaluator now
passes this performance gate; the result is still bounded synthetic evidence,
not a claim of full mix intelligence.

The executable Internal Beta 0.1 pilot gate now passes 5/5 required gates on
the captured configuration after a fresh `python3 -m pytest -q` run with 262
tests passing and a current Live read-only preflight. This
supports supervised disposable-set piloting only; the qualified profile
remains not ready pending independent human review and a reviewed source
snapshot. The machine-readable result is
[`ABLETON_INTERNAL_BETA_0.1_GATE_2026-09-03.json`](ABLETON_INTERNAL_BETA_0.1_GATE_2026-09-03.json).

With the current Live runtime included, the same gate passes 5/5 required
gates: `AbletonOSC` answered a fresh read-only snapshot and the repeatable
track/transport mutation runner passed all seven supported operations with
restoration and replay rejection.

This is not an Ableton beta approval. A real Live 12 read-only round trip, the
supported track/transport subset, and real EQ Eight, Compressor, and Utility
device-parameter mutations have now passed on the captured
disposable local set. Native Live Edit Undo and manual stale-change rejection
also passed for the EQ Eight parameter; Live loss during a pending proposal
returned a non-success failure receipt with no readback. Saved-set
retained-state crash/restart recovery also passed for the named disposable
`.als` with an identical post-recovery snapshot hash. Mock passes are not
Live evidence.

At this baseline, the analyzer measured sample peak, RMS, crest factor,
clipping runs, silence, DC offset, channel balance, correlation, stereo width,
mono cancellation, FFT peaks, bandwidth/confidence, and broad band energy.
The baseline did not claim calibrated LUFS, LRA, true peak, source-aware
masking, or professional mastering approval; the current addendum above records
the subsequently implemented calibrated measurements.

AutoMix rendering, stem separation, voice, destructive project operations, and Auto mode remain disabled. The public web beta and Ableton assistant beta are separate decisions; existing public chat/Mix Review results do not qualify Live integration.

Remaining blockers: additional device-matrix and wider crash qualification,
larger human-reviewed language/evidence evaluation, and calibrated
loudness/true-peak algorithms if required. The bounded long-file/high-rate/
concurrency benchmark now passes for the newly exposed spectral analysis
path, but it is synthetic runtime evidence rather than real-mix quality
qualification. Legacy AudioGen clip-loading side effects are also disabled
until a typed reversible proposal path exists; the legacy batch-device
executor is likewise fail-closed outside explicit compatibility tests.
Supported legacy HTTP
track/transport writes now route through the shared safety boundary;
unsupported direct mutations are disabled until they can meet the same
contract.

The 2026-09-02 follow-up verified the local companion status endpoint, the
real Live snapshot, the compiled plug-in command client, and the
confirmation-only explicit EQ-band proposal path. That write boundary was
subsequently qualified on 2026-09-03, including the natural-language absolute
compound form and restoration of the original values; broader device/OS
coverage and hosted-UI verification remain open.

The subsequent 2026-09-02 HTTP lifecycle qualification closed that gap on the
same disposable set. A typed request for `4-Audio -> EQ Eight -> 2 Gain A`
was proposed from 0 dB to -3 dB, explicitly confirmed, applied, and verified
by real Live readback. An exact replay was rejected with HTTP 409. The fresh
undo proposal was then executed through the corrected schema-specific device
executor and verified by real Live readback at 0 dB. This proves the companion
HTTP route for one EQ parameter, including confirmation, replay protection,
readback, and undo. The same lifecycle was then repeated using the natural
command `set EQ Eight 2 Gain A to -3 dB on track 4`; KENN resolved the exact
parameter and `2A` band from the Live snapshot before applying it. This does
not yet qualify arbitrary EQ wording or arbitrary device parameters.

The human-review workflow is prepared at
[`ABLETON_ASSISTANT_HUMAN_REVIEW_PACKET_2026-09-08.json`](ABLETON_ASSISTANT_HUMAN_REVIEW_PACKET_2026-09-08.json); it requires two independent reviewers and remains pending until scores are entered and adjudicated.
Once scores exist, `scripts/adjudicate_human_review.py` validates complete
case/criterion coverage and produces agreement statistics; it does not replace
the independent review or adjudication decision.

Prompt-injection fixtures now cover Live names, WAV metadata/filenames, and
retrieved-note excerpts. The latter are marked as untrusted reference text in
the optional LLM context block; these tests establish boundary handling, not
an unconditional guarantee against every future model or integration.

The paired rewrite gate also exercises one factual paraphrase and one
unsupported/fabricated candidate against the same retrieved evidence. It is a
deterministic validator test; no external LLM quality or human usefulness
score is claimed.
