# KENN Stage 2/3 integration evidence — 11 October 2026

The branch adds guarded, generic individual-parameter control across tracks, returns, master and nested racks; conversation target clarification; and offline qualification tooling. This receipt records engineering evidence. Stage 2/3 release gates remain open.

Branch: `codex/kenn-stage2-stage3-integration`. Fixed base: `00f2ad60`. Source commits: `18c15c38`, `aecac1de`. The implementation uses existing owners, dependencies and action policy. No model run, index rebuild, service restart, producer-session write, autonomous writer or direct C++ writer was performed. The dirty main checkout and its `KENN_PLAN.md` were preserved.

Exact changed paths and their behavior groups are in [changed-files.json](stage2-stage3-2026-10-11/changed-files.json). Test results and artifact hashes are in [verification.json](stage2-stage3-2026-10-11/verification.json). This receipt proposes plan entries below; it is not another roadmap.

## Behavior and limits

The existing action service accepts a typed, non-executable candidate containing an observed address and names, parameter index, value, unit and session. It validates complete metadata, sparse indices, exposed or qualified choices, supported physical conversions and protection flags before issuing confirmation. It never invents a range or clamps an invalid request. A physical request cannot silently become raw.

The bundled AbletonOSC handler retains original object references and checks topology through discovery, Apply, readback and Undo. Tokens bind names, address, raw before/after values, ranges, units, protection flags and readable displays. Apply rereads the retained target; renamed, moved, removed, replaced, expired, automated or disabled controls refuse. The protocol uses query nonces and a single-use writer observation. A lost acknowledgement triggers inspection, not a repeated setter. Failed reconciliation produces an unknown outcome; the frontend offers no blind retry or automatic Undo.

Production clients require this negotiated handler. Legacy device setup, compound-EQ Apply, device-parameter recipes and positional recovery refuse before writes because those formats lack retained target references. Migrating those formats remains **implementation work**, independent of real-Live qualification. Individual addressed changes are the supported alternative. The legacy fake recipe results below do not qualify those production formats.

Conversation context remembers selected track position as well as name. Duplicate device names and “the other compressor” show observed device numbers instead of selecting the first match. Ambiguous “that one” and incompatible “make it slower” requests remain clarification/refusal paths. Explicit Apply is still required. Session clearing revokes confirmations; project context, explicit preferences and late background answers remain owned by their requesting session. Model context is bounded to four relevant devices and 32 observed parameters, with limitations rather than the complete installed catalog.

HTTP and MCP inspection/proposal tools use the existing policy and shared service. Actual bundled handler registration and UDP serialization are tested. Existing action and recipe cards distinguish discussion/proposals from applied, verified, partial and unknown results, and show address paths, physical displays or choice labels.

## Coverage and examples

[parameter-coverage.json](stage2-stage3-2026-10-11/parameter-coverage.json) records **25 devices, 92 parameters, 184 actual fake writes**: proposal → Apply → observed readback → replay refusal → Undo → exact restoration → out-of-range refusal. Twelve device metadata fixtures are previously recorded reset metadata; thirteen devices and their permission flags/chooser values are explicitly modeled and unqualified. Locations include track, return, master and a four-level path through Instrument, Audio Effect, MIDI Effect and Drum Racks. Sparse chooser raw values are `2`, `7`, `11`; they are synthetic contract examples, not measured host mappings.

All 53 remaining stock entries have an explicit reason in that JSON. Packs, Max for Live and third-party plug-in inventory remain unknown. Current Live observations and real-Live qualification are zero in this run. [installed-catalog.json](stage2-stage3-2026-10-11/installed-catalog.json) records 78 installed stock entries from Live `12.4.6 (2026-09-10_0de5c8fa9a)`, with observation unknown for each. This worktree has no private knowledge notes or retrieval index; its zero note matches do not describe the main checkout's corpus. The existing nine-device/21-parameter profile list remains declared mapping evidence, separate from current observation.

[recipe-recheck.json](stage2-stage3-2026-10-11/recipe-recheck.json) reuses the 15 existing recipe cases: **15/15 fake lifecycles pass** with shared command/Apply handlers, receipt-journal Undo and comparison of mixer state, device parameters and insertions. It uses the investor-demo fake and recorded reset insertion templates. Producer usability and all 15 supervised real-Live recipe qualifications remain open.

[conversation-examples.json](stage2-stage3-2026-10-11/conversation-examples.json) names the executable API tests and their asserted outcomes. Representative examples:

| Journey | Asserted integration behavior |
|---|---|
| Knowledge → suggestion → inspect → proposal → Apply | Two synthetic knowledge replies have no receipt; actual HTTP inspection reports raw `0.25`; proposal to `0.75` writes nothing; explicit Apply performs one verified fake write. |
| Inspect → wrong device → corrected proposal → revised relative value → Apply → Undo | A return's second Test Filter, parameter index `4`, starts at `0.25`; imaginary device refuses; relative `+0.1 raw` proposes `0.35`; Apply verifies `0.35`; confirmed Undo restores `0.25`. |
| Duplicate Compressor → clarification → device 2 → revision → read-only inspection → Apply | Choices are actual device numbers `1` and `2`; only the revised second device changes. |
| Duplicate Vocal tracks → select track 3 → other Compressor | Choices come from track 3's devices, even when the earlier Vocal has a different device layout. |
| Undo with intervening manual edit | Normal Undo restores raw exactly. A manual change to `0.6` after the Undo card is prepared refuses restoration and preserves the producer's value. |

The tests cover all ten requested journey families using actual API handlers and deterministic/fake state. Knowledge text and model candidates are declared stubs. Failed-job classification is tested at the job-store boundary; the five unrun-analysis follow-ups use the real no-analysis guard through HTTP. These checks establish delivery and authority contracts, not useful model prose or natural-language qualification.

## Verification

The backend used the existing main-checkout Python environment through a temporary worktree symlink. No dependency installation occurred. Frontend verification used the existing ARM Node runtime; an earlier x64 Node attempt lacked its architecture-specific rolldown module, then the installed ARM runtime passed without installing anything.

| Check | Result |
|---|---|
| Full backend: `KENN_LIVE_BACKEND=fake ../.venv/bin/python -m pytest -q -p no:randomly` from `apps/backend/src` | **4,527 passed, 137 skipped, 1 pre-existing failure**, 5 warnings, 105.14 s. |
| Final context/journey scoped checks | 183 passed, 2 warnings. |
| Frontend: ARM Node `node_modules/vitest/vitest.mjs run` | 77 passed in 9 files. |
| ARM Node `node_modules/vue-tsc/bin/vue-tsc.js -b` and `node_modules/vite/bin/vite.js build` | Both passed. |
| [Mutation checks](stage2-stage3-2026-10-11/mutation-results.json) | 14/14 faults caught; exact source bytes restored after each fault. |
| Offline packet/forms/progress CLIs | Five cases retained, five unreviewed; full adjudication of blank forms rejects with exit 2. |

The failure is `test_query_typo_correction.py::test_typo_query_routes_to_production_and_avoids_weak_match_early_return`: the typo query routes to `unknown` rather than `production`. It was separately reproduced at fixed base `00f2ad60` (1 failed, 9 passed). Retrieval ranking and grounding thresholds were not changed to mask it. The 137 skips remain visible; index-dependent qualification cannot run in this index-free worktree. Warnings concern existing Starlette/AnyIO, bundled pythonosc and audioread compatibility.

## Capture, review and later qualification

[synthetic-delivery-contracts.json](stage2-stage3-2026-10-11/synthetic-delivery-contracts.json) contains 24 separate reports: four surfaces × cold/warm fixture labels × three repeats. Each retains accepted, rejected, busy, timeout and not-attempted cases in an eligible denominator of five. There were zero provider calls and zero HTTP requests. Cache clearing was stubbed; native phases, paint/usefulness, memory pressure and swap remain unknown. Fixture elapsed time is not a performance result.

[review/packet.json](stage2-stage3-2026-10-11/review/packet.json) and [blank forms](stage2-stage3-2026-10-11/review/forms/reviewer-a.json) demonstrate offline blinding. The private capture and unblinding key are outside the packet at `/tmp/kenn-stage23-review-private/`, with mode `0600`. The five exposed regression cases are not an independent qualification set. [progress.json](stage2-stage3-2026-10-11/review/progress.json) reports zero correct/clarify/wrong judgments and five unreviewed cases. Accepted-but-wrong, disagreement, malformed/incomplete review, duplicate IDs and packet/build mismatch refusals have regression tests.

Reproduce fake coverage from the repository root with the existing backend Python environment (`$KENN_BACKEND_PYTHON`). These commands do not build an index or contact Live:

```sh
"$KENN_BACKEND_PYTHON" products/kenn/tooling/scripts/qualify_parameter_targets.py --output /tmp/kenn-parameter-coverage.json
"$KENN_BACKEND_PYTHON" products/kenn/tooling/scripts/recheck_recipes_fake.py --output /tmp/kenn-recipe-recheck.json
"$KENN_BACKEND_PYTHON" products/kenn/docs/evidence/stage2-stage3-2026-10-11/run_mutation_checks.py
"$KENN_BACKEND_PYTHON" products/kenn/docs/evidence/stage2-stage3-2026-10-11/capture_synthetic_delivery.py
```

After Claude finishes and the machine is free, use the integrated finished checkout and its existing qualified index. Fill [qualification-manifest.template.json](stage2-stage3-2026-10-11/qualification-manifest.template.json) with measured identities; supply externally authored case files and an existing matching companion. Run one job at a time, three repeats per route/cache condition, retaining each report separately:

```sh
for surface in stream payload foreground background; do
  for cache in cold warm; do
    for repeat in 1 2 3; do
      http_args=()
      if [[ "$surface" == foreground || "$surface" == background ]]; then
        http_args=(--endpoint "$KENN_COMPANION_URL")
      fi
      "$KENN_BACKEND_PYTHON" products/kenn/tooling/scripts/measure_chat_latency.py \
        --cases "$KENN_QUALIFICATION_CASES" --limit 500 --surface "$surface" \
        --cache-condition "$cache" --build-manifest "$KENN_FINAL_MANIFEST" \
        --receipt "$KENN_PRIVATE_OUTPUT/$surface-$cache-$repeat.json" \
        --review-capture "$KENN_PRIVATE_OUTPUT/$surface-$cache-$repeat-capture.json" "${http_args[@]}"
    done
  done
done
```

Local cold runs clear only the existing semantic answer-cache tiers; warm runs retain them. HTTP cold/warm labels require independent server-side cache attestation, and neither establishes model residency. Live-open timing requires the plan's owner-supervised M3/16 GB conditions. These commands request knowledge answers and never Apply. Do not run them during Claude's active benchmark, rebuild an index, or start/restart the companion as part of this receipt. Rejected candidate text may be unavailable from HTTP; preserve that limitation rather than substituting the delivered fallback as the candidate.

Build a separate packet per route/build/dataset split from a private completed capture; retain keys outside reviewer-visible directories. Export new forms for each packet, then adjudicate only independently completed forms:

```sh
"$KENN_BACKEND_PYTHON" products/kenn/tooling/scripts/build_human_review_packet.py --capture "$KENN_CAPTURE" --output "$KENN_PACKET" --key-output "$KENN_PRIVATE_KEY"
"$KENN_BACKEND_PYTHON" products/kenn/tooling/scripts/export_human_review_forms.py --packet "$KENN_PACKET" --output-dir "$KENN_FORMS"
"$KENN_BACKEND_PYTHON" products/kenn/tooling/scripts/adjudicate_human_review.py --packet "$KENN_PACKET" --reviewer-a "$KENN_FORMS/reviewer-a.json" --reviewer-b "$KENN_FORMS/reviewer-b.json" --output "$KENN_ADJUDICATION"
```

## Proposed plan entries and exact Claude hooks

| Entry | Proposed recorded progress; remaining work |
|---|---|
| C1 | Separate four-surface provenance/all-outcome capture and synthetic repetitions implemented. Finished-model, supervised Live-open timings, native missing phases and display/memory measurements remain open. |
| C2 | Compact observed context, metadata reuse, exact proposal authority and session-owned late-answer tests implemented. No measured speed claim; real quality/performance comparison remains open. |
| C3 | Ten five-turn families and API/UI authority boundaries tested with fakes/stubs. Model-in-the-loop explanation and language qualification remain open. |
| C4 | Offline captures, blinded packets, independent blank forms, outcome/partial/disagreement denominators and strict bindings implemented. Independent human reviews and adjudication remain open. |
| C5 | Observation, unsupported mapping, proposal, verified action, saved preference and unrun-analysis distinctions tested. Existing grounding/ranking unchanged; useful-answer and sealed-quality gates remain open. |
| L1 | Generic retained targets and guarded semantics reach 25 devices/92 parameters in fake evidence. Remaining 53 stock entries listed; host exposure, additional inventories and physical mappings need evidence. Legacy production format migration remains implementation work. |
| L2 | Bundled adapter follows documented Live Object Model flags while treating Python availability as unknown. Version-applicable chooser raw maps, runtime protection flags, plug-in units and missing conversion facts need focused qualification; no scrape/index rebuild. |
| L3 | Existing 15 recipes pass fresh fake Apply/Undo checks. Guarded migration of production device recipe steps, supervised qualification of at least 15 recipes and producer usability remain open. |
| L4 | Typed candidates enter existing deterministic services; model-supplied confirmation fields refuse. Clear commands remain the fast path and model planner remains shadow. Actual blind action accuracy remains open. |
| L5 | Client plus registered bundled handler, nonces, fresh original-object checks, one setter, readback, unknown outcomes and exact Undo tested. Actual Live Python handler exposure, reconnect/host behavior and release soak remain open. |

Claude's candidate hook is the strict `POST /api/ableton/parameter/proposal` contract: `session_id`, `address` (`kind`, `index`, odd-length alternating device/chain `device_path`, at most four rack hops), `parameter_index`, observed `parameter_name` and `device_name`, `value`, `unit`, optional boolean `relative`. It cannot include approval tokens, executable OSC, invented host IDs or extra fields. Inspect with `/api/ableton/parameter/inspect` first. Unsupported conversion or addressing must remain a refusal; do not replace it with a schema-valid guess.

For qualification, Claude must provide the finished source revision/diff and model digest, resolved prompt hash, exact index/corpus hashes, generation/cache settings and hardware identity. Preserve existing native usage events. Missing hooks are: server admission/busy reason, queue/context/verification durations, rejected-candidate plus evidence capture for HTTP/background jobs, and frontend first-useful/final-paint timestamps with memory-pressure/swap samples. They must retain session/turn ownership and cancellation; traces or caches from superseded work cannot persist. No decode/residency/prompt change was made here.

The official [DeviceParameter documentation](https://docs.cycling74.com/apiref/lom/deviceparameter/) defines enabled/state/automation and value labels; [Device documentation](https://docs.cycling74.com/apiref/lom/device/) describes device containment. Those descriptions do not prove the bundled Python runtime exposes every field, and chooser labels alone do not prove raw positions. The adapter withholds writes when required flags are unknown. Focused note/measurement candidates should resolve exactly those runtime fields, chooser maps and physical conversions for the applicable device/version; no broad scrape is justified by this evidence.

All release gates remain open: ≥150 independent cases with ≥90% useful, supported accepted answers; sealed correctness ≥95%; ≥70% eligible accepted model answers within 15 s on supervised M3/16 GB with Live open (busy/rejected/timeout retained); ≥500 fresh blind phrasings from ≥3 authors and 2 reviewers with ≥95% correct and zero wrong actionable plans; real-Live controls and ≥15 recipes plus producer usability. No fabricated grades or generated blind-set claim appears in this receipt.

Final independent read-only Standards and Spec reviews found no new actionable defects in the source or delivery artifacts. Both retain production legacy-format migration as unfinished implementation and distinguish fake engineering evidence from open release gates. The branch is unmerged.
