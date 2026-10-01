"""F3: the personal-path gate, on the strings that actually leaked and the ones that must not be caught.

The gate is the only thing standing between a repeat of the 2026-09-30 leak and a commit, so it is tested in both
directions: the historical strings are still caught, and the placeholders KENN's own path tests depend on are not.
SLO's equivalent gate has no test at all, which is how its two docs came to claim CI coverage it never had.
"""

from __future__ import annotations

import subprocess

import pytest

from scripts import check_personal_paths as gate

# The exact lines that were in git on 2026-09-30 before the scrub. Each is quoted whole rather than reconstructed, so
# the patterns cannot be quietly weakened to stop matching them.
LEAKED = [
    'HOST = "ubuntu@www.haoee.com"',
    'REMOTE_HOST="ubuntu@www.haoee.com"',
    'SERVER_HOST="www.haoee.com"',
    'host="www.haoee.com"',
    '"${AUTH[@]}" ssh "${SSH_ARGS[@]}" ubuntu@www.haoee.com \'bash -s\'',
    '"ubuntu@www.haoee.com:/mnt/data/kenn-notes-gpu1/transcripts/"',
    "/Volumes/Jack_Gandy_1TB_SSD/Nite-DSP/Nite-DSP-Operations/testing-assets/manifest.json",
    "/Users/Ganders4/.cache/codex-runtimes/node/bin",
    "C:\\Users\\Ganders4\\AppData\\Roaming",
]

# Paths and hosts that look similar and must stay clean, each with the reason it is legitimate.
TOLERATED = [
    ("/Volumes/X/kick.wav", "test_browser_sample_search.py reconstructs this URI; the shape is the assertion"),
    ("/Users/example/Music/Ableton/User Library", "test_abletonosc_installer.py selects between these targets"),
    ("/Volumes/KENN/User Library/Remote Scripts", "same installer test, a labelled fake volume"),
    ("/Users/Shared/", "macOS's own directory, which carries no username"),
    ("/Volumes/.../Shenrendao/", "a redaction already written by hand in KENN_BETA_GAP_MATRIX.md"),
    ("~/Nite-DSP/monorepo/products/kenn", "the form the 2026-09-30 scrub rewrote 140 occurrences to"),
    ('HOST = "${KENN_SERVER_TARGET:?set it}"', "the parameterised form every box script now uses"),
    ("host = os.getenv('KENN_SERVER_PORT')", "a Python local named host is not a machine"),
    ("host = parsed.netloc.lower()", "same"),
    ('ssh -o StrictHostKeyChecking=no ubuntu@127.0.0.1 ls', "loopback"),
    ("mail someone@example.com", "an email address is not a host to log in to"),
]


@pytest.mark.parametrize("line", LEAKED)
def test_the_gate_still_catches_every_string_that_leaked_on_2026_09_30(line: str) -> None:
    assert gate.path_findings(line) or gate.remote_host_findings(line), line


@pytest.mark.parametrize("line, why", TOLERATED)
def test_the_gate_leaves_the_paths_and_hosts_that_have_to_survive_alone(line: str, why: str) -> None:
    assert not gate.path_findings(line) and not gate.remote_host_findings(line), f"{why}: {line}"


def test_every_tolerated_segment_is_a_placeholder_some_test_actually_uses() -> None:
    """A placeholder in the allowlist that nothing uses is a hole with no test behind it."""
    tracked = subprocess.run(["git", "grep", "-IohE", "--",
                              "/Volumes/[A-Za-z0-9._-]+/|/Users/[A-Za-z0-9._-]+/|/home/[A-Za-z0-9._-]+/", "--", "."],
                             capture_output=True, cwd=gate.KENN_ROOT, text=True).stdout.split()
    # git grep matched "/Volumes/X/" — the interesting segment is the one after the root.
    in_use = {path.strip("/").split("/")[1] for path in tracked if path.strip("/").count("/") >= 1}
    assert gate.PLACEHOLDERS <= in_use, f"PLACEHOLDERS entries nothing uses: {sorted(gate.PLACEHOLDERS - in_use)}"


def test_a_planted_leak_fails_the_gate_and_removing_it_makes_the_gate_pass_again(tmp_path) -> None:
    """Verified to pass and verified to fail, which is what SLO's docs claimed and no test proved."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "notes.md").write_text("all clean here\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    assert gate.scan(tmp_path) == []

    (tmp_path / "notes.md").write_text("stems live in /Volumes/Jack_Gandy_1TB_SSD/Nite-DSP/stems\n", encoding="utf-8")
    findings = gate.scan(tmp_path)
    assert findings and findings[0][0] == "notes.md", findings

    (tmp_path / "notes.md").write_text("all clean here\n", encoding="utf-8")
    assert gate.scan(tmp_path) == []


def test_an_untracked_file_is_not_scanned(tmp_path) -> None:
    """The gate is about what git can hand to someone, so a scratch file in the working copy is not its business."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "tracked.md").write_text("clean\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    (tmp_path / "scratch.md").write_text("/Volumes/Jack_Gandy_1TB_SSD/leak\n", encoding="utf-8")
    assert gate.scan(tmp_path) == []


def test_the_shipped_tree_has_no_personal_path_or_remote_host() -> None:
    findings = gate.scan(gate.KENN_ROOT)
    assert findings == [], "run check_personal_paths.py for the file list; the 2026-09-30 scrub should be holding"
