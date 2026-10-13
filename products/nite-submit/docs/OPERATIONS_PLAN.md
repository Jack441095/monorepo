# Submit operations plan

Updated: 2026-10-11. This is the working checklist for Submit and the shared
services needed to deliver it. Tick a task only after its completion evidence
is recorded. A prepared script, credential being present, or service returning
HTTP 200 does not complete a customer journey.

**Current position:** private beta 1.0.0 passed local engineering verification.
The arm64 app is ad-hoc signed and not notarised. It targets macOS 13, but was
tested on macOS 27.0.1. Tester distribution, independent field testing and
public paid release remain outstanding.

Use the [shipping status](SHIPPING_STATUS_2026-10-11.md) for dated test evidence,
the [release report](../NITE_SUBMIT_RELEASE_REPORT.md) for artifact hashes,
the [beta handoff](../NITE_SUBMIT_BETA_HANDOFF.md) for tester instructions and
the [release procedure](../RELEASE.md) for commands. Shared operational history
is in the [operations audit](../../../docs/OPERATIONS_AUDIT_2026-10-08.md).
This checklist carries forward its unresolved Submit/shared-service work;
older audit failures superseded by the final Submit gate are not new blockers.

Owner means you or your named business/account owner. Engineering means the
person executing the local or approved service work. Tester means a selected
private-beta participant. No dates or new spending commitments are assumed.

## Completed and verified

- [x] **C01 — Continue the existing changes safely.** Preserve the split-title
  fix, its regressions and unrelated backend, staging and KENN work.
- [x] **C02 — Fix OCR and candidate detection.** Correct the MIT scan's title
  and institution ranking, title continuation and colonless candidate labels;
  preserve alternatives and human approval for ambiguity.
- [x] **C03 — Prove critical regressions.** New detection and signing-failure
  regressions reproduced red and rejected the relevant removal mutations.
- [x] **C04 — Migrate and qualify the rebuilt corpus.** Pin 47 ordinary inputs
  to exact hashes and independent reviews; document replacement provenance and
  reject stale reports, unqualified inputs and wrong reviewed values.
- [x] **C05 — Retain write and privacy protections.** Check approval, required
  fields, source preservation, collisions, path containment and intake isolation.
- [x] **C06 — Verify the actual bundle.** Helpers, libraries, resources and
  third-party notices pass, including use of bundled qpdf and 7za.
- [x] **C07 — Verify archives and PDF optimisation.** Unicode archives, password
  rejection/round trips, 25 MiB split volumes and valid optimised PDFs pass;
  originals remain unchanged.
- [x] **C08 — Pass the complete source/ZIP/DMG gate.** Final release gate exits
  0; 534 Swift checks, 27 corpus-tool tests and five update-feed tests pass.
- [x] **C09 — Verify reviewed accuracy.** Public authors 7/7, titles 9/9 and
  institutions 9/9; controlled IDs 11/11, explicit absent ID 1/1 and modules
  10/10. Twenty-six public documents add layout coverage.
- [x] **C10 — Verify batch decisions.** All 47 qualified inputs pass; batch
  gives 45 previews, two holds and zero writes. Synthetic ordinary ID+Project
  cases give 172 writes/61 holds; all 233 name-bearing cases hold.
- [x] **C11 — Exercise the final GUI and first launch locally.** Invalid keys,
  picker, review/correction, approval invalidation, approved copy, collision,
  queue retention, archive and image-only recovery pass in disposable settings.
- [x] **C12 — Verify isolated licensing and backend behavior.** Scoped 87 and
  full 139 backend tests pass; signer material stays outside distributed files.
- [x] **C13 — Verify delivery of the exact final ZIP locally.** Simulated
  test-mode GBP 2 purchase, captured email, valid licence, authenticated download
  and signature/replay rejection pass. This is local integration evidence.
- [x] **C14 — Prepare guarded update metadata.** Version, archive name, URL and
  public-key match checks pass. Actual feed signing still needs the owner's key.
- [x] **C15 — Prepare signing and notarisation.** Four stub-tool workflow tests
  pass; missing credentials fail before artifact mutation; failed signing cannot
  leave a passing release manifest. No Apple submission has run.
- [x] **C16 — Produce and preserve beta artifacts.** App, ZIP, DMG and manifest
  agree; four artifact hashes and 17 rollback hashes verify. Disposable test
  homes and licence material were cleaned up.
- [x] **C17 — Refresh the local corpus backup.** All 58 archive members,
  including 48 PDFs, match their source bytes. The archive is on the same drive.
- [x] **C18 — Finish the engineering handoff.** Install guidance, tester
  missions, privacy, rollback, release report, shipping status and this operations
  checklist are recorded.

These ticks certify the retained 2026-10-11 build and evidence. They do not
certify changed binaries, a future signed build or current hosted availability.
Nine historical acquisitions remain unrecovered; controlled ID/module cases
do not establish accuracy on real private student documents.

## Order of operations

| Step | Work | Responsible | Exit condition |
| --- | --- | --- | --- |
| 1 | Owner inputs and independent backup, O01–O09 | Owner, with engineering | Credentials/configuration, company facts and permissions resolved |
| 2 | Private-beta round, O10–O14 | Owner, testers, engineering | Tester evidence reviewed; blocking defects fixed |
| 3 | Signed candidate, O15–O18 | Engineering and clean-Mac testers | Exact signed artifacts, update metadata and installation checks pass |
| 4 | Hosted Sandbox journey, O19–O23 | Owner and engineering | Current artifact reaches an inbox and authenticated customer download |
| 5 | Operational preparation, O24–O36 | Named operators and owner | Recovery, backup, capacity, security, support and business checks pass |
| 6 | Public decision and execution, O37–O40 | Owner and engineering | Explicit approval and verified public delivery with signed rollback |
| 7 | Ongoing operations, O41–O42 | Named operators | Checks have owners, cadence and recorded results |

Steps 1, 2 and independent work in step 5 can run in parallel. Signing needs
O03; the feed needs O04 and the final signed ZIP; hosted delivery needs O08,
O09 and the exact candidate. Public paid distribution waits for steps 1–5 and
the owner's decision in O37. Optional work at the end is not a launch gate.

## 1. Owner inputs and backup

- [ ] **O01 — Keep an independent corpus and release backup.** Owner selects a
  separate device or approved storage; engineering copies the selected corpus,
  reviews, qualification and verified rollback. Complete after checksum
  verification and a retrieval test from the independent copy.
- [ ] **O02 — Resolve licence-signing key provenance.** Owner/account operator
  reconciles the deployed signer with the lifecycle record through approved
  secret access, without printing keys. If rotation is required, agree a client
  trust-key migration that preserves existing customer licences first.
- [ ] **O03 — Supply Apple release credentials.** Owner installs a valid
  Developer ID Application identity and the `NITE_SUBMIT` notary profile.
  Complete when credential preflight succeeds; actual signing is O15.
- [ ] **O04 — Supply the offline update signer.** Owner provides the private
  key matching the existing app public pin through a private path. Complete
  when its public-key match verifies; do not change the pin to obtain a pass.
- [ ] **O05 — Verify the company particulars.** Owner provides independently
  verifiable UK registered name, company number and registered office. A trading
  name or statement that the company is incorporated does not complete this.
- [ ] **O06 — Approve and publish accurate legal copy.** Owner/legal reviewer
  approves terms, software licence, refunds and privacy, including company
  particulars, provider regions/transfers, retention/deletion and actual
  analytics/email behavior. Engineering applies approved copy and checks the
  deployed pages before legal approval is enabled.
- [ ] **O07 — Align Stripe business and Submit catalogue.** Owner resolves the
  recorded individual/company mismatch, verifies the intended one-time GBP 2
  Submit product/price and metadata, and records separate Sandbox/live mappings.
  Keep checkout closed until the release decision; archived legacy links do
  not qualify as the active offer.
- [ ] **O08 — Approve durable staging configuration.** Owner supplies isolated
  Stripe Sandbox, durable R2 storage, deliverable Resend configuration and
  database/environment settings for the existing staging service. Complete
  when engineering can run the durable staging gate without temporary storage,
  console email or test/live credential mixing.
- [ ] **O09 — Authorize the real-email rehearsal.** Owner names the approved
  recipient and explicitly authorizes sending the staging purchase/sign-in
  emails. Complete when that instruction is recorded; sending is part of O21.

## 2. Private-beta field testing

- [ ] **O10 — Arrange the private tester round.** Owner selects the cohort,
  issues approved offline test licences and chooses a private delivery channel.
  Engineering supplies the verified beta and handoff through that approved
  channel; invitations/messages need the owner's explicit sending instruction.
- [ ] **O11 — Record installation on tester Macs.** Testers record OS, arm64
  hardware, quarantined installation and first launch. Include macOS 13 before
  claiming it has been tested. Record any ad-hoc-signature installation failure
  without weakening Gatekeeper instructions.
- [ ] **O12 — Complete tester missions.** Testers exercise text/scanned PDFs,
  picker/Finder opening, alternatives/manual corrections, required-field holds,
  approved copies, unchanged sources, collisions, queue/archive flows and error
  recovery. Complete with the privacy-safe feedback described in the handoff.
- [ ] **O13 — Review broader real field coverage.** Owner obtains permission
  for representative IDs, modules, group submissions and anonymous naming.
  Engineering keeps private intake ignored, derives independent truth and
  reports its coverage separately from public and controlled fixtures.
- [ ] **O14 — Close beta blockers.** Engineering triages feedback, adds
  reproduced regressions for confirmed defects and reruns affected checks.
  Any code/artifact/qualification change requires fresh applicable release
  evidence and hashes; owner reviews unresolved limitations before promotion.

## 3. Signed public candidate

- [ ] **O15 — Sign and notarise the candidate.** Engineering follows
  [RELEASE.md](../RELEASE.md), runs the fresh full gate and prepared signing
  workflow, staples the app/DMG and passes public distribution readiness.
  Complete with real Apple results and a new final artifact manifest.
- [ ] **O16 — Verify the signed build on clean Macs.** Testers install from the
  quarantined final ZIP and DMG, check Gatekeeper, licensing and representative
  GUI flows, and record minimum-version/arm64 results. Intel is not claimed.
- [ ] **O17 — Sign and review the final update metadata.** Engineering uses the
  matching offline key with the final signed ZIP, checks version, HTTPS URL,
  length and checksum, and verifies the signature. The unsigned zero-length
  placeholder must be replaced before any update feed is offered.
- [ ] **O18 — Retest exact signed-artifact delivery locally.** Engineering
  repeats the isolated purchase/licence/download check using the final signed
  ZIP and records its new checksum. Private-beta hashes cannot certify it.

## 4. Hosted purchase and delivery rehearsal

- [ ] **O19 — Register the exact candidate in staging.** Engineering uploads
  the approved signed artifact to durable staging storage and verifies release
  descriptor, architecture, licence-key compatibility and object checksum.
  Retain access control and a verified rollback object.
- [ ] **O20 — Pass durable staging readiness.** Engineering runs
  [check_staging_rehearsal.py](../../../backend/scripts/check_staging_rehearsal.py)
  with approved staging configuration. Record the current pass and verify an
  external browser can reach the intended website/API journey.
- [ ] **O21 — Complete the hosted Sandbox customer journey.** Owner/tester
  makes a test-mode GBP 2 purchase; engineering traces hosted signed webhook,
  one purchase/entitlement, real inbox receipt, sign-in, authenticated download
  and app activation. Downloaded bytes must match O15's exact artifact.
- [ ] **O22 — Prove hosted failure and replay behavior.** Engineering verifies
  duplicate webhook idempotency, rejected signatures, sign-in link replay and
  denied unauthorised downloads in staging without extra entitlements/emails.
- [ ] **O23 — Validate refunds and disputes in Sandbox.** Owner/operator
  exercises real provider test events, full-refund licence revocation, dispute
  review and out-of-order reconciliation; refunded/disputed orders stay out of
  confirmation retries. Use the current commerce runbook for actual semantics.

## 5. Shared operational preparation

- [ ] **O24 — Assign confirmation-email recovery.** Owner names an operator
  and cadence for the backlog and `sweep_unsent_confirmations`. Engineering
  demonstrates failed-send recovery under the
  [commerce runbook](../../../backend/docs/COMMERCE_RUNBOOK.md), including
  refunded/disputed exclusions. A recurring job is not currently verified.
- [ ] **O25 — Verify email operations.** Owner/operator confirms the installed
  key's workspace, inbox/junk placement, message SPF/DKIM/DMARC alignment,
  provider verification and bounce handling. Existing DNS records and provider
  delivery status alone do not complete this task.
- [ ] **O26 — Retire superseded credentials safely.** Account owners identify
  old Resend and R2 token users, confirm replacement usage and revoke only
  credentials proven unused. Record completion without secret values; leave
  unrelated account/bucket tokens untouched.
- [ ] **O27 — Choose a production database recovery strategy.** Owner agrees
  either managed database migration or a tested independent backup path, with
  restore access, recovery-time and data-loss targets. New services/costs need
  approval. Existing volume snapshots do not establish independent recovery.
- [ ] **O28 — Prove production-data recovery in isolation.** Engineering
  restores an approved backup into an isolated environment and verifies schema,
  purchases/entitlements and recovery targets without contacting customers.
  The completed local synthetic restore is only baseline evidence.
- [ ] **O29 — Measure capacity and startup behavior.** Engineering investigates
  the recorded OOM, tests sustained staging load/memory and cold starts, and
  records headroom. Owner approves any capacity/cost change before execution.
- [ ] **O30 — Rehearse service rollback.** Engineering verifies staging
  deployment rollback, compatible migrations, configuration/secret retention
  and release-object recovery. Record the exact last verified service version.
- [ ] **O31 — Establish shared rate limits.** Engineering proposes and, after
  approval for any dependency/service change, verifies a shared edge/storage
  quota across concurrently running machines. Process-local counters do not
  establish a shared quota.
- [ ] **O32 — Connect operational alerts.** Owner names recipients; engineering
  verifies routing for API readiness, failed webhooks, confirmation backlog,
  storage, billing limits and domain/certificate renewal. An approved test alert
  must reach the named operator before the task is ticked.
- [ ] **O33 — Verify account continuity.** Owner checks named ownership, MFA,
  recovery, billing access and renewal notices for Stripe, Vercel, Fly, domain
  hosting, Resend, R2 and Neon. Store recovery material outside the repository.
- [ ] **O34 — Verify waitlist and account lifecycle.** Engineering/operator
  checks sign-up deduplication, export/deletion, unsubscribe and actual retention
  against approved privacy copy. Verify any claimed email sequence or remove
  the claim through approved copy changes.
- [ ] **O35 — Complete business administration.** Owner/adviser verifies payout
  reconciliation, accounting exports, tax obligations, customer receipt/support
  details, software terms and third-party licence compliance. Record decisions
  without bank details or personal account data in Git.
- [ ] **O36 — Assign customer support and incident handling.** Owner names the
  refund/dispute/support operator, response targets and evidence trail; operator
  rehearses failed payment/delivery, licence repair and escalation using the
  commerce runbook. Customer contact needs explicit sending authorization.

## 6. Public decision and launch

- [ ] **O37 — Approve the concrete public release.** Owner reviews the exact
  signed artifacts/hashes, legal/company details, tester limitations, hosted
  journey, operational evidence and rollback. Record explicit publication
  approval before public upload, feed publication or opening paid checkout.
- [ ] **O38 — Record the reviewed source checkpoint.** Engineering prepares a
  bounded Submit/relevant-delivery diff and exact source/build record. Commit
  and push only when the owner explicitly requests them; preserve unrelated
  dirty work and do not describe the current HEAD alone as the release source.
- [ ] **O39 — Execute and verify approved public distribution.** Engineering
  publishes approved signed files/feed and release metadata, checks public
  object hashes and authorised download, and aligns website/backend
  legal/release/checkout gates with the approved live Stripe offer. Use an
  owner-approved verification method; no live card charge is implied.
- [ ] **O40 — Retain a usable public rollback.** Engineering verifies a signed
  rollback snapshot and records how to pause affected checkout/downloads and
  restore it. The ad-hoc private-beta snapshot is not a signed public rollback.

## 7. After launch

- [ ] **O41 — Start the agreed operational cadence.** Owner assigns coverage;
  operator reviews readiness, failed webhooks, unsent confirmations, support,
  refunds/disputes and storage/billing alerts during the initial launch period.
  Agree the ongoing cadence, backup/restore frequency and incident escalation.
  This plan does not create scheduled jobs or notifications.
- [ ] **O42 — Keep releases and evidence current.** Engineering updates this
  checklist and dated evidence after each change, reruns the applicable gates
  for new artifacts, retains verified signed rollback copies and periodically
  checks key/credential lifecycle and independent restore evidence.

## Deferred or conditional work

- [ ] **D01 — Review release CI when requested.** Engineering proposes gate
  coverage and private secret injection; owner approves before CI changes.
  Passing manual checks are not evidence of a CI run.
- [ ] **D02 — Recheck the recorded development dependency advisories.**
  Engineering runs a fresh scoped audit before choosing a compatible fix;
  owner approves dependency changes. The dated audit's ESLint/glob findings
  are historical evidence, not a current advisory determination.
- [ ] **D03 — Add Intel support only if selected.** Owner decides whether it
  is needed; engineering then builds and verifies actual Intel/universal
  artifacts on supported Macs before changing architecture claims.
- [ ] **D04 — Decide whether the prepared Cloudflare staging proxy is needed.**
  Owner chooses hosting/access scope before any token permissions or deployment
  changes. Existing Fly staging can satisfy Submit's journey without this option.
- [ ] **D05 — Consider UI automation separately.** If repeatability warrants
  it, owner approves the required System Events access before running the
  prepared script. Native GUI evidence already exists; permission is unchanged.
- [ ] **D06 — Revisit historical PDFs only on a new lead.** If an original
  becomes available, engineering checks its recorded hash, derives/rechecks
  qualification and reports any added coverage. Do not repeat the completed
  broad backup search or claim recovered historical parity without evidence.

Separate product work remains in its existing records: SLO artifact acceptance
and catalogue setup, and the disabled free Para-phase engine's service/privacy
checks are in the [operations audit](../../../docs/OPERATIONS_AUDIT_2026-10-08.md).
They do not authorize extra Submit scope. KENN's sole work queue remains
[KENN_PLAN.md](../../kenn/KENN_PLAN.md); this document creates no KENN tasks.

## Keeping the checklist honest

For each new tick, append the date and a link/path to evidence or an owner
decision. Preserve failure evidence and separate public, controlled and private
coverage. A failed or skipped gate stays open. If a later change invalidates a
completed task, reopen it and record why; do not reuse the beta manifest for a
changed or signed build. Keep credentials, private PDFs and personal feedback
out of tracked notes.
