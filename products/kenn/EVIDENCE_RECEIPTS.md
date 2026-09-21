# KENN Internal Beta — Evidence Receipts

Append-only log. Each entry records what was verified, how, and the exact source state it was verified against — per the sprint's "record the source SHA, produce a dated evidence receipt" operating model.

---

## 2026-09-01 — Mix Review adapter: independent clean-checkout build proof

**Work package:** E (independent build), closing BB-7 for `mix-review/`.

**Claim tested:** the Mix Review adapter (`products/kenn/mix-review/adapter.py` +
`qualified_detectors.py`) builds and runs correctly using only the
`Audio_Too` commit actually pinned in git — not whatever is currently
checked out in the (dirty, ahead-of-pin) working tree.

**Method:**
1. Read the pinned submodule commit from the git index directly (not the
   working tree): `git ls-tree HEAD Audio_Too` → `1b2ead0bc15ea33a52550e72d527c623bb0e6cfc`.
2. Cloned `Audio_Too` locally into an isolated scratch directory and checked
   out exactly that commit — the real working-tree `Audio_Too` (dirty, with
   uncommitted Thursday work) was never touched.
3. Ran `products/kenn/mix-review/tests` with `KENN_AUDIO_TOO_ROOT` and
   `KENN_MIX_REVIEW_RUNTIME_DIR` pointed at that isolated clone.
4. Ran the CLI entrypoint directly against a freshly synthesized WAV file
   through the same isolated clone.

**Result:**
- `products/kenn-repo main @ e3de078`, `Audio_Too @ 1b2ead0bc15ea33a52550e72d527c623bb0e6cfc`
- `pytest products/kenn/mix-review/tests`: 12/12 passed
- CLI (`python3 products/kenn/mix-review/adapter.py <file> --scope mix_in_progress`): `status: completed`, all 3 qualified families returned with explicit status, no error

**Not covered by this receipt:** the `automix/` and `chat/` boundaries were
not re-verified against an isolated clone in this pass (`chat/` already has
a documented Dockerfile-based build; `automix/` is out of beta scope per
`BETA_SCOPE.md` and remains untested against a clean checkout — tracked as
the remaining half of BB-7).
