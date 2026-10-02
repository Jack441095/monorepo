# Audio_Too's studio/kenn now points at the engine package directory — 2 October 2026

A3 slice, done on Jack's steer to use the KENN in `products/kenn` rather than rebuild on Audio_Too. It supports
[KENN_PLAN.md](../../KENN_PLAN.md) and closes the symlink finding in
[the LaunchAgent receipt](KENN_LAUNCHAGENT_AND_DOC_POINTERS_2026-10-02.md).

## What was wrong and what changed

`Audio_Too/studio/kenn` was a symlink to `../../products/kenn`. Audio_Too expects `studio/kenn` to be the directory
that contains the importable `kenn` package (164 references use `studio/kenn/kenn/...`, and about 25 scripts do
`sys.path.insert(ROOT / "studio" / "kenn")` then `import kenn`). In the product that directory is
`apps/backend/src`. The symlink now targets `../../products/kenn/apps/backend/src`, so every one of those
callers resolves without being edited. `studio/kenn/kenn/main.py` and `server.py` exist.

One caller used something other than the package: `scripts/install_ableton_remote_script.py` read
`studio/kenn/remote_script/AudioToo_Bridge`. That directory lives at the product root, so the script now reads it
from `products/kenn/remote_script/AudioToo_Bridge`.

## Verification

From `Audio_Too`, with the KENN backend venv (it lacks some Audio_Too dependencies such as `nite_core`, so this
is a before/after comparison, not a green suite):

- `pytest --collect-only -q tests`: 2,673 collected with 214 errors before, 2,864 collected with 188 errors after.
- The 27 test files that reference `studio/kenn/kenn`: 22 passed, 20 failed and 20 errors before; 126 passed, 32
  failed and 6 errors after. More of them now run, so some newly run tests fail. Reasons seen in the failures:
  missing modules, and legacy tests (chat routing, RAFT, gap clustering, mix-review feedback) written against an
  older KENN. None was investigated further, and none is evidence the retarget is wrong.
- `tests/test_install_ableton_remote_script.py`: 2 failed, 8 passed before. With only the symlink change it was 4
  failed, 6 passed, because those tests had been passing only on an untracked `__pycache__` directory under the old
  target. With the script repointed it is 2 failed, 8 passed again. The two that fail need `AudioToo_Bridge`
  source, which is not tracked anywhere in the monorepo.

## Limits

- `studio/kenn/.venv` and `studio/kenn/data/*.db` (one reference each) resolved nowhere before and still do not.
- `Audio_Too/Dockerfile:44` only puts `/app/studio/kenn` on `PYTHONPATH`. A Docker `COPY` of a symlink whose target
  is outside the Audio_Too context will not carry the engine in. No image was built and no Audio_Too CI ran.
- The stale `audio-too-ci.yml` deselect lines (139-141) and the Makefile `business/` lint entry were not changed
  because CI and build config need Jack's go-ahead.
- Historical docs still name the old layout and were left as written.

## Exact changed files

Paths are relative to the monorepo root.

- `Audio_Too/studio/kenn`: symlink target.
- `Audio_Too/scripts/install_ableton_remote_script.py`: the source path.
- `products/kenn/docs/evidence/KENN_AUDIO_TOO_SYMLINK_RETARGET_2026-10-02.md` and `products/kenn/KENN_PLAN.md`.
