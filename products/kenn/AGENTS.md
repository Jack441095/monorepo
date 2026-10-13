# KENN working agreements

## Repository sharing

- `Nite-DSP/monorepo:products/kenn` is the source of truth. `Nite-DSP/kenn-app` shares this product with teammates who must not receive the full business repository.
- Every published KENN change must reach the matching branch in `kenn-app`. Use the existing `tooling/scripts/sync_kenn_app.py` from the monorepo and verify that the destination Git tree equals the committed `products/kenn` tree before reporting publication complete.
- The existing sharing workflow handles ordinary pushes. If it fails, complete the same sync manually and report the automation failure; a failed workflow does not count as a completed sync.
- Review independent changes on `kenn-app` feature branches, import approved changes into the monorepo, then synchronize from the monorepo. Preserve teammates' commits; use ordinary fast-forward pushes and the export checks rather than force-pushing over independent work.
- Export only committed product files. Keep credentials, local audio, model weights, generated indexes, and the rest of the business repository out of the sharing repository.

## Git and runtime boundaries

- Use neutral branch and tag names such as `draft/`, `feature/`, or `fix/`; omit AI tool names. Commit messages are single-line descriptions of the change and its reason, without AI attribution trailers. Stage exact file paths.
- `KENN_PLAN.md` is the sole roadmap and work queue.
- Before implementing or extending audio analysis, follow the standing open-source reuse check in `KENN_PLAN.md`.
- Daily engineering uses `KENN_LIVE_BACKEND=fake`. Real Live writes require Jack's scheduled, supervised disposable session.
- Remote KENN work uses physical GPU 1 with `CUDA_VISIBLE_DEVICES=1`. Do not restart servers.
