# SLO Infrastructure Requirements V1

**Purpose:** what SLO will eventually need from the NITE DSP platform — documented now, **not implemented now**. Per explicit instruction: do not touch Submit, platform payment rails, Railway staging, Paddle, or licensing. This is a forward-looking requirements list, gated behind private beta success, not a build task.

## Later (post-beta, paid-launch adjacent) — do not build yet

- **Account entitlement** — SLO has no user-account/entitlement system today (unlike Submit, which has magic-link auth + Paddle entitlement already proven on staging). Would need its own design, likely reusing Submit's proven pattern rather than inventing a new one — but that's a platform-level decision, not SLO's alone.
- **Signed downloads** — depends on B-001 (Apple Developer ID) landing first. No distribution signing infrastructure exists for SLO specifically; Submit's existing release-artifact registry pattern (`releases/nite-submit/...`) is a reasonable template to reuse rather than reinvent, once B-001 unblocks.
- **Update channel** — no auto-update mechanism exists for SLO. Not needed for a beta with a handful of manually-distributed builds; needed before any wider release.
- **Crash/error reporting** — SLO has no telemetry or crash reporting today. For a *local-first, read-only* private beta with a small, owner-approved cohort, manual tester feedback (see `SLO_PRIVATE_BETA_TEST_PLAN_V1.md`) is sufficient; don't build telemetry infrastructure just for this beta.

## Needed for beta itself (lighter-weight than the above)

- **Documentation** — a tester-facing README/quickstart. Not yet written; straightforward once the beta build itself is frozen (same pattern as Submit's tester pack).
- **Support flow** — who testers email/message with issues. Simplest answer: reuse Jack's existing support channel (same `nitedsp@outlook.com` address already in use for Submit) rather than standing up something SLO-specific — a platform decision, not an engineering one.
- **Privacy/legal review** — SLO's local-first, no-audio-upload design (see below) substantially reduces the privacy surface vs. a cloud product, but "no review at all" isn't a real answer for anything reaching outside a fully trusted, small, owner-approved cohort. Recommend a lightweight review (not the full Submit-scale legal process) before even the private beta, given it touches real user file systems.
- **Storage of release artifacts outside git** — SLO's build artifacts (the `.app` bundles, `_build/`, `_cache/`) are already gitignored and never committed (confirmed throughout this session's work — `.gitignore` already covers `_build/`/`_cache/`). No new infrastructure needed for this specifically; just need a real distribution mechanism (e.g. a shared drive link, matching how Submit's beta ZIP is planned to be hand-delivered) once there's a build to distribute.

## Already true, no work needed

- **Local-first privacy model** — SLO already processes everything on-device (ONNX inference is local, no network calls in the scan/classify path — confirmed by code review across this whole session, no HTTP/network client code touches the scan pipeline at all).
- **No audio upload requirement for beta** — follows directly from the above; nothing to build, just to state clearly in tester-facing docs so it's not assumed otherwise.

## Explicit non-goals for this document

Paid launch, Railway/Paddle integration, account systems, and update infrastructure are all **out of scope for private beta** and were not designed, prototyped, or touched while producing this document — consistent with "SLO is parked but important" and "do not disturb Submit."
