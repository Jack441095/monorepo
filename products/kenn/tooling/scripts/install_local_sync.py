#!/usr/bin/env python3
"""Install the owner's opt-in local cloud catch-up without changing Git permissions."""

import argparse
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    label = "com.nitedsp.kenn-git-catchup"
    support = Path.home() / "Library/Application Support/KENN/git-catchup"
    agents = Path.home() / "Library/LaunchAgents"
    support.mkdir(parents=True, exist_ok=True)
    agents.mkdir(parents=True, exist_ok=True)
    script = support / "sync_local_checkout.py"
    # Keep the scheduled script outside the checkout so switching branches cannot remove it.
    shutil.copyfile(Path(__file__).with_name("sync_local_checkout.py"), script)
    plist = agents / f"{label}.plist"
    configuration = {
        "Label": label,
        "ProgramArguments": [sys.executable, str(script), "--repo", str(repo), "--lock", str(support / "sync.lock")],
        "EnvironmentVariables": {"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
        "RunAtLoad": True,
        "StartInterval": 300,
        "ProcessType": "Background",
        "StandardOutPath": str(support / "sync.log"),
        "StandardErrorPath": str(support / "sync-error.log"),
    }
    domain = f"gui/{os.getuid()}"
    # Reload only this opt-in agent; other KENN and product services belong to the owner.
    if subprocess.run(["launchctl", "print", f"{domain}/{label}"], capture_output=True).returncode == 0:
        subprocess.run(["launchctl", "bootout", f"{domain}/{label}"], check=True)
    with plist.open("wb") as handle:
        plistlib.dump(configuration, handle)
    subprocess.run(["plutil", "-lint", str(plist)], check=True)
    subprocess.run(["launchctl", "bootstrap", domain, str(plist)], check=True)
    print("Local cloud catch-up installed: login and every 300 seconds while awake")


if __name__ == "__main__":
    main()
