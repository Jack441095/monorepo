# SLO Beta Execution Master Plan V1

**Planning date:** 2026-09-15  
**Product:** SLO — Sample Library Optimiser  
**Target:** invitation-only macOS private beta  
**Recommended first cohort:** 5–8 trusted producers after a 2–3 person internal pilot  
**Planning horizon:** 6 focused weeks once Apple credentials and a clean Mac are available; allow up to 12 calendar weeks for external dependencies and measured fixes  
**Decision owner:** Jack / NITE DSP  

**Live execution evidence:** `SLO_BETA_EXECUTION_STATUS_2026-09-15.md`

**Latest encoder research decision:** `SLO_ENCODER_RESEARCH_DECISION_2026-09-15.md`

## 1. Executive decision

SLO should move to beta through a deliberately narrow release, not through another broad classification-research cycle.

The first beta should prove that a producer can safely install SLO, index a real sample library, find useful sounds, preview them, and drag them into Ableton without file loss, host instability, or misleading confidence. It should not attempt to prove universal sample classification, public-launch readiness, paid commerce, Windows support, or the complete long-term taxonomy.

The critical path is:

1. consolidate the current dirty product work into a clean, reproducible beta candidate;
2. freeze the beta product contract and user-facing claims;
3. qualify the exact Release build and its model/taxonomy identity;
4. configure and test production HTTPS licensing and beta entitlements;
5. sign, notarise, package, and verify the exact artifacts;
6. pass clean-Mac and Ableton Live acceptance on those artifacts;
7. run a small internal pilot, then a 5–8 person private-beta cohort;
8. expand only when safety, activation, stability, and usefulness metrics pass.

Current decision: **not ready to distribute externally today**. Engineering foundations are strong, but the release is still gated by source hygiene, Apple signing/notarisation, production licensing, exact-artifact clean-machine testing, Ableton validation, and owner-authorised release operations.

## 2. What “beta” means

### 2.1 Included in Beta 1

- macOS on Apple Silicon.
- Standalone, AU, and VST3 from one immutable release candidate.
- Local-only library scan and analysis; no audio upload.
- WAV, AIFF and other formats actually supported by the shipping JUCE format registry, after direct qualification.
- Library browsing, search, filters, favourites/history where verified.
- Preview playback.
- Find Similar and the visual similarity map where verified.
- Visible scan progress, empty states, failures, Unknown/OOD states, and confidence bands.
- Drag-to-DAW workflow.
- Opt-in beta entitlement with a defined expiry and revocation path.
- Structured feedback and crash reporting with data minimisation.

### 2.2 Safety policy

- Scanning, analysis, classification, browsing, preview, and search remain read-only against source audio.
- No automatic delete, move, rename, or metadata write may occur during ordinary scanning.
- For the first external cohort, **Sort Library should be disabled by a beta feature flag unless its exact release build passes preview, Copy, Move, cancellation, durable journal, and Undo acceptance on disposable fixtures**.
- If enabled later, Copy is the default; Move requires explicit per-operation confirmation and a verified Undo path.
- Any source-file mutation report is a stop-the-line P0 incident.

### 2.3 Explicit non-goals

- Public or paid launch.
- Windows, Intel Mac, Logic, FL Studio, Reaper, or unsupported Ableton versions.
- A universal or “industry-leading” accuracy claim.
- Shipping experimental CLAP, foundation-model, V5, label-free, or physics-research branches as the production classifier.
- Completing every subtype and attribute in the future taxonomy.
- Uploading tester libraries or collecting telemetry by default.
- Refactoring internal `SmartSampleManager` C++ symbols solely for naming consistency.

## 3. Current baseline

### 3.1 Proven strengths

- The Release architecture already builds AU, VST3, and Standalone from the same JUCE target.
- Product-facing `PRODUCT_NAME` is currently `SLO`.
- The scan path is format-aware in the current working tree rather than WAV-only.
- Scan progress and user-visible empty/error handling exist in the current working tree.
- Read-only scan safety has a checksum-backed test.
- Sort preview, Copy/Move/Cancel, durable journal, and Undo have test coverage.
- The known duplicate-JUCE-symbol build failure is recorded as closed in the current blocker register.
- Existing evidence records scale tests at 100/1,000/10,000 files, a 30-iteration soak, and zero tracked real-time deadline misses/allocations in 2,000 callbacks.
- AU validation has passed on an installed arm64 component.
- Packaging, dependency-bundling, signing, manifest, install, and clean-machine scripts already exist.
- The current classifier has honest cross-vendor measurements and exposes uncertainty rather than silently forcing all labels.

### 3.2 Release-critical gaps

| ID | Gap | Current status | Beta consequence |
|---|---|---|---|
| G-01 | Dirty, research-heavy working tree | 107 tracked changes and 423 untracked entries observed on 2026-09-15 | No trustworthy candidate SHA can be cut yet |
| G-02 | Apple Developer ID signing/notarisation | Blocked on owner credentials | No normal external macOS distribution |
| G-03 | Clean-machine validation | Not complete for the exact candidate | Dependency and first-launch risk unknown |
| G-04 | Production HTTPS licensing and credentials | Not configured/qualified | Activation, expiry, revocation, and offline behavior unproven |
| G-05 | Ableton Live VST3 workflow | Not qualified end-to-end | Do not claim Ableton support yet |
| G-06 | Exact-build GUI acceptance | Current UI changes exist but are not frozen and release-qualified | Usability regressions could escape |
| G-07 | Release archive and exercised operations | Designed, not executed for an SLO artifact | No reliable distribution or rollback |
| G-08 | Protected blind review | Owner-controlled and incomplete | Blocks broad accuracy claims; does not block a narrow, honest usability beta |

### 3.3 Classification position

Classification quality is sufficient to test usefulness only if claims remain narrow and the product abstains visibly. Existing measurements must be attached to their actual corpus and evidence mode. Audio-only accuracy, filename/folder-assisted accuracy, subtype accuracy, and user-perceived usefulness are separate measures and must never be collapsed into one headline number.

For Beta 1:

- freeze the shipping model, head, centroids/gates, taxonomy, preprocessing, class order, and hashes;
- do not promote research weights or thresholds without a predeclared evaluation and owner approval;
- treat Unknown/OOD as successful safe behavior, not as a defect by default;
- prioritise task success and correction burden over a vanity top-line accuracy number;
- use protected blind review before publishing an external accuracy claim, not as a reason to delay a limited usability beta.

## 4. Release strategy and branch discipline

### 4.1 Separate product release work from research

The current tree mixes shipping changes, tests, reports, generated receipts, research scripts, and large result sets. Before release work continues:

1. inventory every tracked modification and untracked entry;
2. classify each as shipping source, shipping test, release tooling, required release evidence, research, generated result, local cache/build output, or unrelated platform/website work;
3. preserve all existing work—do not discard or rewrite provenance;
4. commit coherent shipping changes in reviewable groups;
5. move future generated outputs to the external artifact location specified by the qualification runbook;
6. keep research-only work off the beta release branch;
7. create `codex/slo-beta-1` or an owner-selected equivalent from the reconciled commit;
8. require a clean `git status` before every release-candidate build;
9. record root-repo gitlink and SLO submodule SHA together.

### 4.2 Candidate identity

Every candidate receives:

- semantic prerelease version, recommended `0.9.0-beta.N`;
- release ID, recommended `SLO-MAC-ARM64-0.9.0-BETA.N`;
- SLO commit SHA and root gitlink SHA;
- model, model-data, taxonomy, preprocessing, and class-order versions/hashes;
- build preset, toolchain, SDK, deployment target, and timestamp;
- hashes for AU, VST3, Standalone, installer, manifest, notices, and documentation;
- signed/notarised status and Apple Team ID;
- host/OS compatibility matrix;
- known-limitations snapshot;
- rollback predecessor.

No artifact built from a dirty tree may be distributed.

## 5. Workstreams

### Workstream A — Product contract and owner decisions

**Goal:** eliminate decisions that would otherwise cause late rebuilds or misleading communication.

Tasks:

- A-01: approve the Beta 1 scope in section 2.
- A-02: confirm the visible name `SLO` and defer internal-symbol/bundle-ID migration unless there is a legal or compatibility reason to change it before first signing.
- A-03: choose minimum supported macOS version and Apple Silicon-only support.
- A-04: name one supported Ableton Live 12 version for the initial claim.
- A-05: approve 2–3 internal testers and 5–8 Phase 1 external testers.
- A-06: confirm the monitored support address and incident owner.
- A-07: confirm no default telemetry and no audio upload.
- A-08: decide whether Sort Library is disabled in cohort 1 (recommended) or included after its dedicated gate.
- A-09: confirm entitlement duration, recommended 60–90 days.
- A-10: authorise Apple Developer Program/certificates and protected blind-review handling.

Exit criteria:

- one signed-off product-contract receipt;
- no unresolved naming, platform, cohort, mutation, or support-policy decision on the critical path.

### Workstream B — Source consolidation and release freeze

**Goal:** turn the current working tree into a reviewable, reproducible release lineage.

Tasks:

- B-01: produce a file-by-file dirty-tree inventory.
- B-02: split shipping code changes from research/benchmark work.
- B-03: verify that generated artifacts, caches, corpora, and build outputs are ignored or stored outside source where appropriate.
- B-04: review the 107 tracked changes for accidental product/research coupling.
- B-05: reconcile older audit statements against current code, especially product naming, format-aware scanning, scan progress, empty states, and sort/undo.
- B-06: commit product changes in small, attributable units with tests/receipts.
- B-07: create the beta branch and freeze model/taxonomy inputs.
- B-08: tag a non-distributed engineering candidate and reproduce it from a second clean worktree.
- B-09: back up/push the branch and verify repository object health before distribution.

Exit criteria:

- clean SLO beta worktree;
- reproducible build from an immutable commit;
- no untracked runtime dependency or local-only model file;
- root gitlink points to the intended SLO commit;
- research changes remain preserved but outside the shipping lineage.

### Workstream C — Functional beta hardening

**Goal:** ensure the narrow Beta 1 journey works as a coherent product.

Required journey:

1. install and activate;
2. launch Standalone;
3. choose a tester-owned library;
4. see immediate scan progress;
5. cancel and restart a scan;
6. reopen and resume/reuse the index;
7. browse, filter, search, favourite, and preview;
8. inspect category, subtype/attributes where supported, confidence, and Unknown/OOD;
9. use Find Similar;
10. drag a sample into Ableton;
11. save, close, reopen the Ableton project;
12. deactivate/revoke and confirm the client response;
13. uninstall or roll back without touching the source library.

Tasks:

- C-01: verify format admission and decode parity for WAV, AIFF, FLAC, and any other format claimed in the guide.
- C-02: make unsupported/corrupt files visible as counted failures without blocking the scan.
- C-03: verify progress totals, cancellation, completion, empty folder, no results, missing file, offline, degraded model, and cache-corruption states.
- C-04: verify preview start/stop, device loss, rapid selection, and switching samples during scan.
- C-05: verify index persistence, selective rescan, moved/missing files, app restart, and forced-quit recovery.
- C-06: verify Find Similar and filters on a realistic library, not only synthetic fixtures.
- C-07: verify drag-to-DAW for existing and missing files.
- C-08: feature-flag Sort Library off for cohort 1, or execute its separate mutation-safety gate.
- C-09: remove or update stale `Smart Sample Manager` user-facing text in the tester journey while preserving historical/internal identifiers where safe.
- C-10: ensure privacy, support, version, build ID, and diagnostics locations are discoverable in-app or in the tester pack.

Exit criteria:

- the complete journey passes twice on the release candidate;
- no P0/P1 defect;
- no silent scan failure or ambiguous destructive action;
- all user-facing claims match observed behavior.

### Workstream D — Automated qualification and evidence freeze

**Goal:** execute—not merely build—the full release test matrix on the exact candidate.

Tasks:

- D-01: configure from `ssm-release-candidate`/approved Release preset with auto-install disabled.
- D-02: clean-build `ssm_qual_full` serially if required by generated JUCE header ordering.
- D-03: run every native executable directly; CMake qualification targets alone do not execute tests.
- D-04: run `TestLicensing --url-policy` without credentials.
- D-05: run authorised end-to-end licensing activation separately once the service exists.
- D-06: rerun checksum-based read-only safety, cache guard, path traversal, malformed audio, multi-instance, persistence, sort/undo (if included), RT stress, similarity, taxonomy, format-aware scan, and acoustic parity tests.
- D-07: run 100/1,000/10,000 scale tiers or justify a still-current equivalent on the same engine/model lineage.
- D-08: run a 30-iteration soak and record peak/steady RSS, scan time, error count, and cache size.
- D-09: run a frozen, leakage-controlled classifier scorecard sufficient to document limitations; do not tune on its holdout.
- D-10: create a single qualification receipt binding every result to the candidate SHA and data class.

Minimum gate:

- 100% of required tests pass;
- licensing E2E may be `BLOCKED` only before the first distributable RC, never at release authorisation;
- no unexplained regression versus the accepted performance baseline;
- no generated result is mistaken for an independently reviewed label set.

### Workstream E — Licensing and platform

**Goal:** make beta access reliable without coupling audio analysis to the network.

Tasks:

- E-01: deploy/configure the production-like HTTPS licensing endpoint.
- E-02: provision signing keys and client verification material using secret storage; no secrets in git, logs, manifests, or screenshots.
- E-03: exercise beta entitlement issuance from an owner/admin account.
- E-04: test activation success, invalid key, expired entitlement, revoked entitlement, device limit, retry, timeout, offline grace, clock skew, malformed response, and server failure.
- E-05: ensure localhost/plain-HTTP configuration cannot appear in a production build.
- E-06: verify account → entitlement → authorised download → checksum flow.
- E-07: test revocation and deactivation end-to-end.
- E-08: verify backups and restore for entitlement/download metadata before inviting testers.
- E-09: add service health visibility and a manual fallback procedure that does not require emailing unsigned binaries.
- E-10: record data retention and privacy behavior for accounts, licenses, logs, and feedback.

Exit criteria:

- clean test account completes the whole flow;
- fail-closed security behavior is verified;
- ordinary server downtime does not damage local indexes or source audio;
- entitlement and download rollback are proven;
- no production secret is embedded in the client.

### Workstream F — macOS packaging, signing, and notarisation

**Goal:** produce an ordinary, verifiable macOS installation experience.

Tasks:

- F-01: complete Apple Developer Program enrollment and create Developer ID Application and Installer identities.
- F-02: run signing preflight and confirm Team ID, bundle IDs, entitlements, hardened runtime, deployment target, and version.
- F-03: clean-build AU/VST3/Standalone and bundle all non-system runtime dependencies.
- F-04: verify no Homebrew/local absolute-path dependency leaks.
- F-05: include third-party notices and exact model/license provenance.
- F-06: sign nested code from the inside out; verify every bundle with strict codesign checks.
- F-07: build and sign the chosen PKG/DMG distribution artifact.
- F-08: submit to Apple notarisation, staple, and verify with Gatekeeper.
- F-09: generate immutable manifest and SHA-256 files.
- F-10: archive the candidate plus logs, notarisation ID, manifests, checksums, and rollback package.

Exit criteria:

- all signatures valid;
- notarisation accepted and stapled;
- installation artifact checksum matches the archive and download listing;
- no build-machine-only dependency;
- uninstall/rollback procedure exists before shipment.

### Workstream G — Host and clean-machine qualification

**Goal:** validate the exact signed artifact in the environment testers will use.

Test machines:

- G-M1: oldest supported macOS on a clean Apple Silicon user account/machine.
- G-M2: current macOS on a clean Apple Silicon user account/machine.
- G-M3: development machine for diagnostic comparison only, never as the sole clean-machine proof.

Ableton matrix for the one claimed Live version:

- clean install;
- VST3 scan and discovery;
- AU scan and `auval`;
- create track and load plugin;
- scan a fixture library;
- preview during stopped and playing transport;
- drag a one-shot and loop to Session and Arrangement views;
- save project;
- close Live;
- reopen project;
- verify plugin state, library/index state, and missing-file behavior;
- change sample rate/buffer size;
- exercise offline licensing behavior;
- remove/reinstall/upgrade candidate;
- collect crash/hang logs if anything fails.

Standalone matrix:

- first launch;
- audio device selection/loss;
- small and large scan;
- cancel/restart;
- relaunch and cache hydration;
- corrupted disposable cache recovery;
- uninstall and reinstall;
- source library hashes unchanged.

Exit criteria:

- exact signed/notarised candidate passes on G-M1 and G-M2;
- Ableton matrix passes twice with zero crash/hang/state-loss failures;
- AU claim is backed by `auval`; VST3 claim by actual Live behavior and validator where available;
- tester guide names only the versions/formats that passed.

### Workstream H — Beta operations and tester experience

**Goal:** make the beta observable, supportable, and reversible.

Tasks:

- H-01: finalise welcome guide, install guide, first-run walkthrough, known limitations, troubleshooting, uninstall, rollback, privacy summary, and bug report form.
- H-02: make the support mailbox live and assign daily triage ownership during the first week.
- H-03: define severity and response targets.
- H-04: create a release archive and access-controlled download.
- H-05: issue one internal entitlement, install from the real download path, and complete the whole journey.
- H-06: perform a rollback drill before the first external invitation.
- H-07: create a beta ledger covering invite, download, install, activation, first scan, first useful find, crash, safety concern, support ticket, and exit survey.
- H-08: prepare release notes and limitations for the exact build.
- H-09: define feedback prompts around usefulness rather than asking only “was the label correct?”
- H-10: schedule 24-hour and 7-day check-ins without requesting audio by default.

Severity policy:

| Severity | Examples | Response |
|---|---|---|
| P0 | file loss/mutation outside explicit operation, security/license bypass, malicious package, widespread activation outage | freeze downloads immediately; preserve evidence; notify all affected testers |
| P1 | repeatable DAW crash, index corruption, cannot install/activate for multiple testers, state loss | stop cohort expansion; triage same day; patch or rollback |
| P2 | broken workflow with workaround, severe misclassification pattern, high memory on supported library size | fix before next cohort/release where practical |
| P3 | cosmetic issue, copy problem, low-impact UX friction | backlog with evidence |

Exit criteria:

- real distribution path has been rehearsed;
- every tester has a support and rollback route;
- operator can identify who has which release;
- beta can be frozen within one hour without deleting user data.

## 6. Milestones and gates

### M0 — Scope locked

**Target:** days 1–2  
**Gate:** section 2 approved; owner decisions A-01 through A-10 recorded.  
**Deliverable:** beta product contract and decision receipt.

### M1 — Clean engineering candidate

**Target:** week 1  
**Gate:** clean branch, immutable SHA, model/taxonomy freeze, reproducible Release build.  
**Deliverable:** `0.9.0-beta.1` engineering candidate; not distributed.

### M2 — Product-qualified candidate

**Target:** week 2  
**Gate:** automated suite, safety, scale/soak, UI journey, restart/recovery, and documentation truth pass.  
**Deliverable:** candidate qualification receipt and blocker register refresh.

### M3 — Platform-connected candidate

**Target:** weeks 2–3, parallel with M2  
**Gate:** production-like HTTPS licensing, issue/activate/offline/revoke, entitled download, backup/restore pass.  
**Deliverable:** platform/licensing E2E receipt.

### M4 — Signed release candidate

**Target:** week 3 or when Apple credentials arrive  
**Gate:** dependencies bundled; Developer ID signatures valid; notarisation/stapling accepted; manifest/checksums archived.  
**Deliverable:** `0.9.0-beta.2` signed RC.

### M5 — Clean-Mac and Ableton qualified

**Target:** week 4  
**Gate:** G-M1/G-M2 install, Standalone, AU, VST3, Ableton persistence, update/rollback all pass on the exact RC.  
**Deliverable:** host/clean-machine matrix and final known limitations.

### M6 — Internal pilot

**Target:** week 5, minimum 3–5 active days  
**Cohort:** 2–3 trusted internal/friendly users.  
**Gate to proceed:** no P0/P1; all can install/activate; at least two complete a real library scan and Ableton journey; rollback drill passes.  
**Deliverable:** go/no-go decision for external Phase 1.

### M7 — Private Beta Phase 1

**Target:** week 6, minimum 7 active days  
**Cohort:** 5–8 external trusted producers.  
**Gate to expand:** section 7 metrics pass; no unresolved P0/P1; support load sustainable.  
**Deliverable:** Beta 1 outcomes report and decision: iterate, expand, or stop.

### M8 — Private Beta Phase 2

**Earliest:** after M7 evidence, not by calendar promise  
**Cohort:** 15–25 testers, one additional supported macOS/host combination only if separately qualified.  
**Gate:** same release discipline for every update; no silent cohort expansion.

## 7. Beta success metrics

The beta exists to answer whether SLO is safe, usable, useful, stable, and supportable.

### 7.1 Hard safety and reliability gates

| Metric | Internal pilot gate | Phase 1 expansion gate |
|---|---:|---:|
| Confirmed unintended source-file mutations | 0 | 0 |
| P0 incidents | 0 | 0 |
| Unresolved P1 incidents | 0 | 0 |
| Signed download checksum mismatches | 0 | 0 |
| Install + activation completion | 100% | ≥ 90% |
| Ableton project reopen/state success among users attempting it | 100% | ≥ 95% |
| Crash-free completed sessions | ≥ 95% | ≥ 97% |
| Index recoveries requiring manual cache deletion | 0 | 0 preferred; any occurrence blocks expansion pending review |

### 7.2 Usefulness gates

| Metric | Phase 1 target |
|---|---:|
| Invited testers who complete first scan | ≥ 75% |
| First useful sound found within first session | ≥ 70% of activated testers |
| Median time from launch to first useful result, excluding initial large scan | ≤ 10 minutes |
| Testers who use SLO in a real production session within 7 days | ≥ 60% |
| Testers who would be disappointed to lose access | ≥ 40% directional signal; do not overinterpret tiny sample |
| Median usefulness score | ≥ 4/5 |
| Classification corrections per 100 reviewed items | measure by class/evidence mode; no single global target until baseline is stable |
| Unknown/OOD judged preferable to a wrong confident label | ≥ 80% of reviewed abstentions |

### 7.3 Performance/support gates

- no supported-library scan exceeds the documented expectation by more than 2× without explanation;
- no sustained post-scan memory growth across repeated use;
- fewer than 0.5 support tickets per active tester per week after onboarding week;
- median first response under one business day;
- every P1 has reproduction status and owner within one business day.

Metrics must use explicit denominators. Invited, activated, scanned, and active users are not interchangeable.

## 8. Stop conditions and rollback

Freeze distribution immediately if any of the following occurs:

- suspected or confirmed unintended mutation/loss of source audio;
- package/signature/checksum mismatch;
- licensing bypass or leaked production secret;
- repeatable DAW crash affecting more than one tester on a supported configuration;
- corrupted index that cannot recover without risky manual filesystem instructions;
- an outage that prevents new activation and has no safe documented fallback;
- privacy behavior differs from the published statement;
- release artifact cannot be tied to its source/model/manifest.

Rollback procedure:

1. disable the affected download/release entitlement;
2. preserve the package, manifest, logs, and reports—do not overwrite evidence;
3. notify affected testers with exact release ID and safe steps;
4. restore the previous signed release and verify its checksum;
5. confirm source-library integrity with affected users before asking them to retry;
6. open an incident record with severity, scope, first/last known time, candidate SHA, and owner;
7. ship a fix only through the full candidate gates appropriate to the changed risk surface.

## 9. Risk register

| Risk | Likelihood | Impact | Mitigation | Owner |
|---|---|---|---|---|
| Apple enrollment/signing delay | High until confirmed | Critical | start immediately; continue non-distribution work in parallel | Jack |
| Dirty-tree work is lost or wrongly promoted | High | Critical | inventory, preserve, split, commit, push, clean worktree reproduction | Engineering + Jack |
| Research classifier accidentally becomes shipping classifier | Medium | High | explicit production model/hash freeze; release diff review | Classification owner |
| Licensing endpoint fails or leaks dev config | Medium | High | production-mode fail-closed test; E2E activation/revocation | Platform |
| Ableton-specific crash/state loss | Medium | High | exact-version matrix on signed RC; cohort constrained to qualified version | Product QA |
| High memory on very large libraries | Medium | Medium/High | document supported scale; record peak RSS; staged cohorts; cancel/recovery | Engineering |
| Misclassification reduces trust | High | Medium | confidence/Unknown UI; honest limitations; collect correction context | Product + classification |
| Sort Library causes fear or real harm | Low if disabled | Critical | disable in cohort 1; fixture-only mutation tests; Copy default and Undo | Product owner |
| Support overload | Medium | Medium | tiny cohort; templates; daily triage; expansion gates | Jack |
| Documentation contradicts product name/features | High without pass | Medium | exact-build documentation truth review | Operations |
| Private sample data is over-collected | Low/Medium | High | no audio by default; explicit consent; minimised logs | Support/privacy owner |
| Beta expands through enthusiasm rather than evidence | Medium | High | cohort gates and written owner authorisation | Jack |

## 10. Prioritised backlog

### P0 — required before any external tester

1. owner scope/identity/platform decisions;
2. dirty-tree inventory, preservation, clean beta branch, and remote backup;
3. exact Release build and full direct test execution;
4. production HTTPS licensing plus activation/revocation;
5. Developer ID signing, notarisation, installer, manifest, and checksums;
6. clean-machine installation and rollback;
7. exact-version Ableton validation;
8. real download-path rehearsal and owner release authorisation;
9. support/incident/known-limitations pack.

### P1 — required before Phase 1 expansion

1. live UI journey and restart/recovery acceptance;
2. format support verified against every format claimed publicly;
3. supported-library-size and memory guidance;
4. internal pilot completed with zero unresolved P0/P1;
5. classification limitations and correction workflow tested with users;
6. account/download backup and restore drill;
7. update from prior beta and rollback to prior beta.

### P2 — useful during beta, not a launch blocker unless evidence says otherwise

1. additional subtype/attribute breadth;
2. OOD threshold research after explicit authorisation and predeclared evaluation;
3. Intel Mac or more DAWs/hosts;
4. optional consent-based diagnostics/telemetry;
5. large visual redesign;
6. internal class/file/target rename;
7. public accuracy claims;
8. paid checkout and broad commercial operations.

## 11. First 72 hours

### Day 1 — decide and protect

- approve/narrow section 2;
- start or confirm Apple Developer enrollment;
- name internal and Phase 1 cohorts;
- confirm supported macOS/Ableton versions, support mailbox, entitlement duration, and Sort Library policy;
- snapshot and back up the current SLO state without discarding anything.

### Day 2 — reconcile the tree

- generate the full dirty-tree classification;
- identify the minimal shipping diff;
- separate generated/research artifacts from product source;
- reconcile stale audits with current implementation;
- create a clean candidate worktree/branch.

### Day 3 — prove the baseline

- configure and clean-build the release candidate;
- run the complete native suite directly;
- capture model/taxonomy/build identity;
- run the read-only safety test and a small end-to-end scan;
- open only evidence-backed defects;
- publish the first candidate gate receipt.

At the end of 72 hours, the project should have a precise blocked/passing board and an immutable engineering candidate, even if Apple or clean-machine dependencies are still pending.

## 12. Weekly operating rhythm

- Monday: gate review, blocker owners, candidate scope freeze.
- Daily during active release work: short P0/P1 review; no uncontrolled research merges.
- Wednesday: candidate qualification and documentation truth check.
- Friday: release/no-release decision based on receipts, not percentage-complete estimates.
- During cohort week: daily support/incident review and a twice-weekly usefulness review.
- After every candidate: archive receipts and update the blocker register before starting the next candidate.

## 13. Definition of done for Beta 1

SLO Beta 1 is ready only when all statements below are true:

- the shipping source tree is clean, pushed, immutable, and reproducible;
- the exact build has passed all required automated tests by execution;
- model/taxonomy/preprocessing identity is frozen and recorded;
- source-library read-only behavior is verified on the candidate;
- production HTTPS activation, offline behavior, expiry, revocation, and download entitlement pass;
- all artifacts are dependency-complete, signed, notarised, stapled, manifested, and checksummed;
- clean-Mac install/reinstall/uninstall and rollback pass;
- Standalone, AU, VST3, and the single claimed Ableton version pass their exact-artifact matrices;
- the tester pack describes only verified behavior and limitations;
- support and incident response are live;
- the internal pilot meets the hard gates;
- the owner records explicit release authorisation.

Anything less may still be an engineering preview, but it must not be represented as the external private beta defined here.

## 14. Source-of-truth hierarchy

Use this plan for sequencing and ownership. Use the following existing documents for detailed evidence/procedure:

1. `SLO_BETA_BLOCKER_REGISTER_V2.md` — blocker evidence trail;
2. `SLO_FULL_PRODUCT_CLASSIFICATION_BETA_READINESS_AUDIT_V1_FINAL_REPORT.md` — product/classification audit;
3. `SLO_PRIVATE_BETA_READINESS_V2.md` — prior readiness synthesis, noting that some gaps are now implemented in the dirty working tree and need requalification;
4. `SLO_READ_ONLY_SAFETY_QUALIFICATION_V1.md` — file-safety evidence;
5. `SmartSampleManager/docs/QUALIFICATION_RUNBOOK_V1.md` — correct build/test procedure;
6. `SLO_HOST_VALIDATION_REPORT_V1.md` — current host-claim boundary;
7. `SLO_LICENSE_MODEL_AUDIT_V1.md` — model and licensing boundary;
8. `../../validation/qualification/beta-operations-v1/SLO_PRIVATE_BETA_RELEASE_CHECKLIST_V1.md` — release checklist;
9. `../../validation/qualification/beta-operations-v1/SLO_PRIVATE_BETA_SUPPORT_RUNBOOK_V1.md` — support procedure;
10. `../../validation/qualification/beta-operations-v1/SLO_PRIVATE_BETA_MASTER_GATE_V1.md` — combined engineering/platform/operations gate.
11. `SLO_COMPETITOR_PARITY_TEST_AND_RESEARCH_PLAN_V1.md` — competitor-informed workflow, test, corpus, performance, and research programme.

If documents conflict, the newest direct evidence from the exact release candidate wins, but the conflict must be recorded rather than silently rewriting history.
