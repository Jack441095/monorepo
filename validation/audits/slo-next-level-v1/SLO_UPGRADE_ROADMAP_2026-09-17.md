# SLO Upgrade Roadmap — 2026-09-17

## 1. Upgrade table
| Component | Current (cited) | Verdict | Trigger | Work | Effort | Payoff | Cost of doing nothing |
|---|---|---|---|---|---|---|---|
| Metric/claim contract | 96.5% vs 30.2% vs 57% coexisting; SUPERSEDED headers exist but no gate | harden now | any external claim | R-01 + CI split-label gate; archive-or-label stale reports | S | ends false-confidence; unblocks honest beta | another "96% accurate" message destroys trust |
| OOD gate | logic correct (`AcousticClassifier.h:338-343`), numbers wrong (72% false-known B-007) | harden | before any suggest/auto | R-02 re-fit + coverage@95/90 gate; keep UNKNOWN-visible + no-auto-move | M | unlocks suggest tier | silent mistags |
| Loop taxonomy | F1 0 loops; Vocal Loop 7.5% (B-008 residual) | refactor | producer beta | R-04 + F-07; filename never sole decider on loops | M | core JTBD works | loops unusable |
| Fusion weights | +32pp win, 0% adversarial | harden | before fusion claims | R-05 ablation; F-06 v2 | M | keep win, remove brittleness | adversarial embarrassment |
| SampleManagerEngine god-object | ~4.9k TU couples everything | refactor (seams, no rewrite) | before CLAP/taxonomy tracks | extract Decode/Resample/DSP/Embedder/Head+OOD/Cache/HNSW/Scan interfaces | L | 2× velocity on model work | every model change = full-regression risk |
| Scan formats | WAV-only, silent skip | harden msg now / scoped expand later | B-004 | visible skip-count now; R-08 then F-15 | S/M | DAW parity honesty | day-one Ableton complaints |
| Perf/memory | split evidence (2.4GB/170 vs 10k clean) | harden | large-library claims | R-06 regenerated receipt + ceiling + cancel | S | citable scale story | unprovable scale |
| Working-tree hygiene | 413 slo + 33 monorepo dirty | harden | B-002 Release qual | clean-tree + immutable Release + sweep receipt | S | unblocks signing/licensing/clean-mac | gates stay blocked |
| Licensing/entitlement | dev HTTP; db/keys in tree (B-003) | harden | revenue | HTTPS + offline-grace + E2E; ignore audit | M | can charge | cannot sell |
| Subtypes (B-014) | 92.9%/92.3% but half-gated, 5 conflicts | harden | subcat UX | R-09; resolve conflicts; graduate/retire advisory | S | shippable subcats | half-working tags |
| Encoder | PANNs frozen per 2026-09-15; CLAP +8.34pp unshippable (744MB, no C++/OOD/license) | keep PANNs / gated CLAP track | R-03 gates | F-14 only if all 7 gates pass | L | +5-8pp or principled kill | half-funded both = neither ships |
| RT/audio | design correct, matrix thin (B-004 OPEN) | harden (matrix, not arch) | DAW beta | Ableton matrix + multi-instance contention | M | qualified DAW claim | "works in Live" unproven |
| Docs truth | V2 register newest; older audits contradict | harden (truth-work) | this cycle | superseded headers + single status pointer; delete broken symlink | S | cheap future decisions | repeated re-audits |
| Build hygiene | tools/ 38k outputs; _build/_cache/build* untracked discipline | harden | now | ignore audit; hash-pointer receipts | S | clean scans, no accidental commits | bloat + leak risk |

Consolidation proposal: single SLO status pointer = `SLO_BETA_BLOCKER_REGISTER_V2.md`; single metric receipt = R-01 output; shared future: OnnxEmbedder+Head library for KENN/AudioGen (F-16); delete nothing in product source (read-only audit) — archive candidates: `products-archive/slo/` stub (confirm empty), broken symlink doc, superseded metric JSONs (after R-01 replaces them).

## 2. Sequencing
Lead with revenue-unblockers + harm-prevention (licensing/signing/clean-tree/OOD/UNKNOWN) → truth-work (metric contract, doc labels) → quality gated on research (R-01..R-10) → features (F-01..F-16) → new products only after.

## 3. 30/90/180 (each: RICE, owner, dep, done)
**Now (0–30d):** clean tree + Release sweep receipt (gate for all) · metric contract + CI split gate (R-01 start) · OOD re-fit start (R-02) · UNKNOWN queue F-01 + split display F-02 + rescan-diff F-03 + skip messaging (R-05 fix) · doc truth pass · licensing HTTPS E2E start (B-003) · perf regeneration (R-06). Done = receipts in this folder + dirty count 0 + CI red on missing split.
**Next (31–90d):** loop repair (R-04→F-07) · fusion v2 (R-05→F-06) · subtype graduation (R-09→F-10) · preprocessing ablation (R-07) · engine seam extraction (R-01 refactor) · Ableton matrix start (B-004) + XMP export pilot (F-11) · correction flywheel pilot (F-13) · CLAP C++ spike ONLY if R-03 interim holds. Done = loop F1 ≥0.70 + adversarial ≥40% + Ableton matrix partial.
**Later (91–180d):** CLAP go/no-go (R-03 full → F-14 or kill) · format expansion (R-08→F-15) · model registry OTA (F-12) · combined-query UX (R-10→F-08) · shared classifier service proposal (F-16) · B-001/B-002/B-005 close → read-only pilot → priced beta decision. Done = ship/no-ship with numbers, not adjectives.
