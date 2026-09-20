# Tier 0 Remediation Report

**Scope:** Security hardening (R1), live client site fix (R2), licensing gate (R3), site consolidation (R4), disk reclamation (R5), SLO feature-cache correctness (R6)
**Status:** ✅ Complete — backend suite 106/106 green; feature-cache tests 6/6 green

---

## R1 — Backend Security Hardening

### SEC-1: Deactivate possession proof
**Files:** `backend/app/licensing.py`, `backend/app/schemas.py`

`/v1/deactivate` now **requires** the signed activation token issued by `/v1/activate`. The Ed25519 signature is verified server-side and its claims are matched against the license + device being deactivated.

- **Before:** knowing the license key alone (which is emailed in plaintext) was enough to deactivate a customer's device — an account-takeover vector.
- **After:** forged/replayed/mismatched tokens are rejected (401). Admin revoke remains the support escape hatch.
- Zero DB schema change required.

### SEC-2: Webhook replay window
**File:** `backend/app/commerce.py`

- `ts` timestamp outside a **5-day window** → `400` (previously: valid signatures replayable forever).
- Non-UTF-8 request bodies now produce a clean `400` instead of an unhandled `500`.

### SEC-3 + D-5: Rate limiter rewrite
**File:** `backend/app/rate_limit.py`

- **Correct client keying:** uses the first `X-Forwarded-For` entry (behind Railway/Render the socket peer is the proxy; the old code shared ONE bucket across ALL clients — a global lockout lever for any attacker).
- **O(1) eviction:** `deque` with popleft instead of `list.pop(0)` (was O(n²) under load).
- **Bounded memory:** hard cap of 10,000 buckets with a deterministic LRU-style sweep — spoofed-key floods can no longer grow memory unboundedly.

### D-3: Lazy signing key
**File:** `backend/app/licensing.py`

Signing key loaded via `lru_cache` on first use instead of at import time — a missing key no longer crashes the entire backend on startup, only the routes that actually sign (with a clear 500).

### Correction to earlier report
`/v1/activate` already had a rate limit (20/60s) — an earlier truncated read hid it. `/v1/deactivate` had none; it now does.

---

## R2 — Live Client Site (D-1)

**Files:** `monorepo/client-work/client-websites/crystal-carpentry-salisbury/_redirects` and `Client-Work/website-design/crystal-carpentry-salisbury/_redirects`

Both copies now proxy `/api/*` → `https://crystal-carpentry-backend.onrender.com/api/$1` (the URL already hardcoded in `script.js:81`) instead of `localhost:8000`.

- Fixes deploy previews and local Netlify dev; production was already correct via the absolute URL.
- **Correction during R4:** the Tier 0 edit to the `Client-Work` mirror had actually landed on a stray path at the drive root (`/Volumes/Jack_Gandy_1TB_SSD/Client-Work/...`) — the real mirror still pointed at `localhost`. Fixed during R4 and verified byte-identical to the canonical copy.
- The fix is committed locally in the canonical site repo: `627db4f fix(netlify): proxy /api/* ...` (origin is 1 commit behind — **push is pending your call**).

---

## R3 — Asset Licensing Gate

Agreements with vendors are a human action and cannot be automated. What was built:

**File:** `monorepo/scripts/check_asset_licenses.py`

- Scans every manifest under `testing-assets/` and exits **nonzero** on any placeholder license.
- **Current state: 341 blocked entries** (worse than the ~80 estimate — the manifest contains far more `TODO-vendor-pack` stems than the sampled file). Exit code 1.
- **Action:** wire into CI / run before any training or benchmark work. The block is now machine-enforced, not tribal knowledge.

---

## R4 — Client Site Consolidation (completed during R5)

- **Next version pin: no change needed.** `platform/website/package.json` already pins `next 16.3.5` and `react/react-dom 19.2.8` exactly (not ranges).
- **Canonical copy declared:** `monorepo/client-work/client-websites/crystal-carpentry-salisbury/` is the working checkout of `github.com/Nite-DSP/client-websites` (branch `crystal-carpentry-salisbury`) and holds the backend + `DEPLOYMENT_ACCOUNTS.md`. `Client-Work/website-design/crystal-carpentry-salisbury/` is a mirror at the same commit (`d186980`) — a `CANONICAL.md` pointer was added there.
- The two copies were diffed in full: identical apart from the `_redirects` fix above. A stray fixed copy at the drive root (`/Volumes/Jack_Gandy_1TB_SSD/Client-Work/...`) is a leftover from the mis-pathed edit and can be deleted.

## R5 — Disk Reclamation (archive-then-delete)

**Corrections to the original plan:**
- **`velvet_thunder` does not exist** on this drive (full-depth search matched only Ableton pack sample filenames). The ~90 GB estimate was wrong.
- The drive was never in crisis: **372 Gi free at start**.

**Actual inventory & actions:**

| Target | Size | Action |
|---|---|---|
| `monorepo/workspace/worktrees/` (9 stale copies: slo, nite-submit, root, platform, kenn, submit, thursday, slo-phase4) | 24 GB | Tarballed, verified, removed |
| `monorepo/platform/workspace/worktrees/` | 18 MB | Same tarball |
| `Shenrendao/KENN/build` | 3.0 GB | Deleted (gitignored VST3 build intermediates; `scripts/rebuild_vst3.sh` regenerates) |
| `Audio_Too/.venv` | 1.6 GB | Deleted (regenerable) |
| `platform/website/node_modules` + `.next` | 748 MB | Deleted (regenerable) |
| `__pycache__` / `.pytest_cache` sweep | ~small | Deleted across monorepo/Shenrendao/Client-Work |
| `Shenrendao/KENN/dist` | 13 MB | **Kept** — it's the usable built plugin |
| `products/nite-files/build`, `nite-submit-windows/build` | 59 MB | **Kept** — possibly hard-to-regenerate packaged artifacts (Windows build) |

**Archive:** `Nite-DSP-Operations/archive/workspace-worktrees-20260917.tar` (25 GB, uncompressed, zero tar errors).

**Integrity story (important):** the safety gate initially reported verify **FAILED** (225,617 vs 226,160 entries). Root cause was a race I introduced — the cache sweep deleted `__pycache__`/`.pytest_cache` entries while tar was reading them, and the gate's naive count check had a stale denominator. A normalized set-diff proved the archive is a **complete superset**: 0 of the 225,253 on-disk paths missing from the archive; the only 364 archive-only entries are cache files (deleted mid-tar, bonus snapshot). Only then were the originals removed.

**Net disk effect:** ~29.2 GB deleted, 25 GB archive created → **377 Gi free** (from 372 Gi). Deleting the tarball later frees the full ~29 GB. Backend suite re-run post-cleanup: **106/106 green**.

**Stale git worktree registrations pruned** (no file changes): monorepo, Audio_Too (pointed at the old `NITE_DSP/` folder), KENN (pointed at `/private/tmp/...`).

**Flagged for R6 / later:**
- `monorepo/products/` = **48 GB** (SLO models/data — the R6 correctness + cache work should audit it).
- `Audio_Too/artifacts` = 9 GB, `Audio_Too/studio` = 3.1 GB.
- The crystal-carpentry **client backend** still has the old shared-bucket rate limiter — port the SEC-3 fix.
- The monorepo's 33 dirty files mix my Tier 0 fixes with pre-existing uncommitted feature work (`paraphrase`, `waitlist`) — committing them needs your review, so I left them uncommitted.

## R6 — SLO Feature-Cache Correctness (sha256 keying)

**Bug found and fixed:** the feature caches in `products/slo/SmartSampleManager/tools/classification_benchmark/` were keyed by **path string only**. Any sample file that was edited, re-rendered, or replaced at the same path kept serving **stale features silently** — poisoning every benchmark built on the caches. `physics_cache.py` additionally had no version check.

**Changes:**

| File | Change |
|---|---|
| `feature_cache.py` (new) | `DigestIndex`: sha256 content digests memoised behind a `(size, mtime_ns)` JSON sidecar — unchanged files are never rehashed; changed files are rehashed even if mtime is fudged; missing files → `None`. Atomic sidecar writes. |
| `mw_features.py` | Cache entries now stored with a `digests` array. Resume and `load_aligned()` verify content hashes; stale/legacy rows are **dropped and recomputed** (a stale row is worse than a recomputed one). |
| `physics_cache.py` | Same treatment + a `phys-v1` version check that was missing entirely. |
| `test_feature_cache.py` (new) | 6 test groups: digest correctness, memoisation (no rehash on hit), change-detection under fudged mtime, missing-file → None, npz verify-and-drop roundtrip, legacy-cache-treated-stale. **All pass** (`python3 test_feature_cache.py` → `ALL 6 TEST GROUPS PASS`). |

**Operational note:** the first re-run of `mw_features.py`/`physics_cache.py` will report the existing caches as legacy (no digests recorded) and **recompute them once** — that's the correctness fix taking effect, not a regression. Subsequent runs are memoised and fast.

**Scope note:** `loop_features.py` and the ~60 one-off benchmark scripts share the same path-keyed pattern; the shared helper is in place for them, but I only wired the two core caches (mw + physics) — porting the rest is mechanical and can follow if wanted.

---

## Test Changes (validated — 106/106 green)

- **New:** `backend/tests/test_security_hardening.py` — 8 tests covering possession-proof rejection/acceptance/device-mismatch, stale-ts webhook, non-UTF-8 webhook, lazy signing key, forwarded-for keying, bounded buckets + stale sweep.
- **Updated:** `tests/test_e2e.py` (possession proof in step 6; forged-webhook test now covers fresh-ts→401 and stale-ts→400), `tests/test_concurrency.py` (its webhook used a 2023 timestamp, now correctly caught by the replay window).

---

## Known Follow-ups

- The **Client-Work crystal-carpentry backend** (separate tiny service) still has the old shared-bucket rate-limit pattern — port the same fix.
- **Push pending your call (deprioritised):** `client-websites` repo is 1 commit ahead of origin (`627db4f`). Domain name still unconfirmed, so no rush.
- **R6 follow-up (optional):** port the sha256 cache keying to `loop_features.py` and the remaining ~60 benchmark scripts — mechanical, helper is in place.
- **Tier 0 complete.** All planned remediation done; remaining items above are optional ports.
