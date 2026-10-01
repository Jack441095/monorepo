#!/usr/bin/env bash
# Sync products/kenn from the monorepo to Nite-DSP/kenn-app.
#
# Run it from the monorepo. With no arguments it does every check and stops
# short of pushing; add --push to fast-forward kenn-app main once they pass.
# The monorepo stays the source of truth, so this never force-pushes.
set -euo pipefail

PUSH=0
case "${1:-}" in
  "") ;;
  --push) PUSH=1 ;;
  *) echo "usage: $0 [--push]" >&2; exit 2 ;;
esac

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "${REPO_ROOT}"
if [ ! -d products/kenn ] || ! git remote get-url kenn-app >/dev/null 2>&1; then
  echo "run this from the monorepo, with the kenn-app remote set up" >&2
  exit 1
fi

echo "[1/6] Checking main is clean and matches origin"
git fetch -q origin main
git fetch -q kenn-app main
if [ "$(git rev-parse main)" != "$(git rev-parse origin/main)" ]; then
  echo "local main and origin/main differ; push or pull first" >&2
  exit 1
fi

echo "[2/6] Splitting products/kenn out of main"
sha="$(git subtree split -q --prefix=products/kenn main)"

if [ "$(git rev-parse "${sha}^{tree}")" = "$(git rev-parse kenn-app/main^{tree})" ]; then
  echo "kenn-app main already matches products/kenn on main"
  exit 0
fi

echo "[3/6] Checking kenn-app main is an ancestor of the split"
if ! git merge-base --is-ancestor kenn-app/main "${sha}"; then
  echo "kenn-app main has commits the monorepo doesn't; look at them before syncing" >&2
  git log --oneline "${sha}..kenn-app/main" >&2
  exit 1
fi
git log --oneline "kenn-app/main..${sha}"

echo "[4/6] Scanning the new commits"
# Commit messages here never carry an AI attribution line (see CLAUDE.md).
if git log --format=%B "kenn-app/main..${sha}" \
    | grep -Eiq '^co-authored-by:.*(claude|anthropic)|generated with .*claude'; then
  echo "an attribution line is in the commit messages; reword before syncing" >&2
  exit 1
fi
# Added lines only, so an old token that was already removed doesn't trip this.
if git log -p --format= "kenn-app/main..${sha}" | grep -E '^\+' \
    | grep -Eq 'AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{30,}|sk-[A-Za-z0-9]{20,}|xox[bp]-[A-Za-z0-9-]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY-----'; then
  echo "something that looks like a key or token is in the new commits" >&2
  exit 1
fi

echo "[5/6] Running the CI script on a fresh checkout of the split"
# A clean tree has none of our git-ignored data, which is what kenn-app's CI and
# a colleague's clone see. Tests that need it skip; anything else that needs it fails here.
fresh="${REPO_ROOT}/workspace/tmp/kenn-app-sync-check"
rm -rf "${fresh}"
git worktree add -q --detach "${fresh}" "${sha}"
trap 'git -C "${REPO_ROOT}" worktree remove --force "${fresh}" >/dev/null 2>&1 || true' EXIT
bash "${fresh}/tooling/scripts/ci_verification.sh"

if [ "${PUSH}" -ne 1 ]; then
  echo "[6/6] All checks passed. Run again with --push to update kenn-app main (${sha:0:9})"
  exit 0
fi

echo "[6/6] Pushing to kenn-app main"
git push kenn-app "${sha}:refs/heads/main"
git fetch -q kenn-app main
if [ "$(git rev-parse kenn-app/main^{tree})" != "$(git rev-parse main:products/kenn)" ]; then
  echo "pushed, but kenn-app main's tree differs from products/kenn on main" >&2
  exit 1
fi
echo "kenn-app main is now ${sha:0:9} and matches products/kenn on main"
