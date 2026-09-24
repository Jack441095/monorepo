#!/usr/bin/env python3
"""Run KENN's test suite on the GPU box's CPUs, from an exact commit, and bring the results back.

Keeps long test runs off the owner's Mac and gives a clean, reproducible record:

1. ``git archive`` of the commit (products/kenn, shared, Audio_Too and the audio-technology it links to): the box
   has no GitHub access. The tree is committed into a throwaway local repo, since some tests read ``git HEAD``;
2. KENN's git-ignored runtime data (active knowledge index, notes, embedding model) from the
   main checkout, uploaded only when it changed, so data-dependent tests run instead of skipping;
3. a Python 3.12 virtual environment under ``/mnt/data/kenn-bakeoff/ci`` built from
   ``apps/backend/requirements.txt`` (rebuilt only when that file changes);
4. each suite target in its own pytest process (as the qualification gate does), GPUs hidden;
5. ``results.json`` copied back and summarised.

Only the ``kenn-bakeoff`` folder on the box is touched; nothing is started as a service.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tarfile
import time
from pathlib import Path

MONOREPO = Path(__file__).resolve().parents[4]
KENN = MONOREPO / "products" / "kenn"
HOST = "ubuntu@www.haoee.com"
SSH = ["ssh", "-o", "BatchMode=yes", "-o", "ControlMaster=no", "-p", "2022", HOST]
SCP = ["scp", "-o", "BatchMode=yes", "-o", "ControlMaster=no", "-P", "2022", "-q"]
REMOTE = "/mnt/data/kenn-bakeoff/ci"
TARGETS = ("apps/backend/src/kenn/tests", "chat/tests", "mix-review/tests", "automix/tests")
DATA_PATHS = ("Training_Data_Notes", "artifacts/models/minilm")  # plus the active index version


def _run(command: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(command, check=True, **kwargs)


def _remote(script: str, timeout: int = 3600) -> str:
    return _run(SSH + [script], capture_output=True, text=True, timeout=timeout).stdout


def main_checkout() -> Path:
    """The main checkout (git-ignored data lives there, not in worktrees)."""
    common = _run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=MONOREPO,
                  capture_output=True, text=True).stdout.strip()
    return Path(common).parent


def pack_code(ref: str, out: Path) -> str:
    commit = _run(["git", "rev-parse", ref], cwd=MONOREPO, capture_output=True, text=True).stdout.strip()
    with out.open("wb") as handle:
        _run(["git", "archive", "--format=tar.gz", commit, "products/kenn", "shared", "Audio_Too",
              "audio-technology"],
             cwd=MONOREPO, stdout=handle)
    return commit


def pack_data(data_root: Path, out: Path) -> str:
    """The git-ignored runtime data as a tarball; returns its content digest."""
    package = data_root / "apps" / "backend" / "src" / "kenn"
    version = (package / "data" / "index" / "CURRENT").read_text().strip()
    members = [package / "data" / "index" / "CURRENT", package / "data" / "index" / "versions" / version]
    members += [package / relative for relative in DATA_PATHS]
    digest = hashlib.sha256()
    with tarfile.open(out, "w:gz") as archive:
        for member in members:
            for path in sorted([member] if member.is_file() else member.rglob("*")):
                if path.is_file():
                    digest.update(str(path.relative_to(package)).encode() + path.read_bytes())
                    archive.add(path, arcname=str(path.relative_to(package)))
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ref", default="HEAD", help="commit to test (default: HEAD of this checkout)")
    parser.add_argument("--data-root", type=Path, default=None,
                        help="KENN folder holding the git-ignored index, notes and model (default: main checkout)")
    parser.add_argument("--out", type=Path, default=Path("box-test-results.json"))
    args = parser.parse_args()
    args.data_root = args.data_root or main_checkout() / "products" / "kenn"

    scratch = Path("/tmp") / f"kenn-box-test-{int(time.time())}"
    scratch.mkdir(parents=True)
    commit = pack_code(args.ref, scratch / "code.tgz")
    data_digest = pack_data(args.data_root, scratch / "data.tgz")
    requirements = (KENN / "apps" / "backend" / "requirements.txt").read_bytes()
    req_digest = hashlib.sha256(requirements).hexdigest()
    run_dir = f"{REMOTE}/runs/{commit[:12]}"

    _remote(f"mkdir -p {REMOTE}/data {run_dir}")
    _run(SCP + [str(scratch / "code.tgz"), f"{HOST}:{run_dir}/code.tgz"])
    have = _remote(f"cat {REMOTE}/data/.digest 2>/dev/null || true").strip()
    if have != data_digest:
        _run(SCP + [str(scratch / "data.tgz"), f"{HOST}:{REMOTE}/data.tgz"])
        _remote(f"rm -rf {REMOTE}/data && mkdir -p {REMOTE}/data && tar xzf {REMOTE}/data.tgz -C {REMOTE}/data "
                f"&& echo {data_digest} > {REMOTE}/data/.digest && rm {REMOTE}/data.tgz")

    targets = " ".join(TARGETS)
    script = f"""set -e
cd {run_dir} && rm -rf tree && mkdir tree && tar xzf code.tgz -C tree
(cd tree && git init -q && git add -A && git -c user.name=box -c user.email=box@localhost commit -qm "{commit}")
PKG=tree/products/kenn/apps/backend/src/kenn
cp -r {REMOTE}/data/data {REMOTE}/data/Training_Data_Notes $PKG/ && mkdir -p $PKG/artifacts/models && cp -r {REMOTE}/data/artifacts/models/minilm $PKG/artifacts/models/
if [ "$(cat {REMOTE}/venv/.req 2>/dev/null)" != "{req_digest}" ]; then
  rm -rf {REMOTE}/venv && /mnt/data/anaconda3/bin/python3.12 -m venv {REMOTE}/venv
  {REMOTE}/venv/bin/pip install -q --disable-pip-version-check -r tree/products/kenn/apps/backend/requirements.txt
  echo {req_digest} > {REMOTE}/venv/.req
fi
cd tree/products/kenn
export PATH="{REMOTE}/venv/bin:$PATH" CUDA_VISIBLE_DEVICES="" PYTHONPATH="apps/backend/src:tooling:packages/chat:packages/mix-review:packages/automix"
python_bin={REMOTE}/venv/bin/python
echo '{{"commit": "{commit}", "results": [' > {run_dir}/results.json
first=1
for target in {targets}; do
  start=$(date +%s)
  set +e; $python_bin -m pytest "$target" -q -p no:cacheprovider > {run_dir}/$(echo $target | tr / _).log 2>&1; code=$?; set -e
  summary=$(tail -1 {run_dir}/$(echo $target | tr / _).log | sed 's/"/\\\\"/g')
  [ $first = 1 ] || echo ',' >> {run_dir}/results.json; first=0
  echo "{{\\"target\\": \\"$target\\", \\"exit\\": $code, \\"seconds\\": $(( $(date +%s) - start )), \\"summary\\": \\"$summary\\"}}" >> {run_dir}/results.json
done
echo ']}}' >> {run_dir}/results.json
"""
    _remote(script, timeout=3600)
    _run(SCP + [f"{HOST}:{run_dir}/results.json", str(args.out)])
    results = json.loads(args.out.read_text())
    failed = [r for r in results["results"] if r["exit"] != 0]
    for r in results["results"]:
        print(f"{'ok ' if r['exit'] == 0 else 'FAIL'} {r['target']:32} {r['seconds']:4}s  {r['summary']}")
    print(f"commit {commit[:12]} on the box: {'all passed' if not failed else f'{len(failed)} target(s) failed'}"
          f" (logs in {run_dir})")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
