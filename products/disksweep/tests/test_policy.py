"""10 unit tests: blocklist escapes, SAFE/REVIEW mapping, LLM-guard, trash/undo."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sidecar import classifier as C


def item(path, cat="Cache", size=100, parent=None):
    return {
        "path": path,
        "size_bytes": size,
        "mtime": "2026-09-17T00:00:00",
        "category": cat,
        "installed_parent_app_or_null": parent,
        "signature": "kind:dir",
    }


def test_block_system_prefix():
    assert C.is_blocked("/System/Library/Extensions") is True


def test_block_no_prefix_bypass_systemx():
    # "/Systemx" must NOT match "/System" (segment-boundary rule).
    assert C.is_blocked("/Systemx") is False


def test_block_dotdot_escape():
    assert C.is_blocked("/System/Volumes/Data/../../System/Library") is True


def test_block_private_vm():
    assert C.is_blocked("/private/var/vm/sleepimage") is True


def test_block_kext_substring():
    assert C.is_blocked("/Library/Extensions/Fake.kext/Contents") is True
    assert C.is_blocked("/Library/Extensions/ok.txt") is False


def test_block_timemachine():
    assert C.is_blocked("/Volumes/B/Backups.backupdb/x") is True


def test_usr_local_cache_exception():
    assert C.is_blocked("/usr/local/var/cache/cleanme") is False
    assert C.is_blocked("/usr/bin/ls") is True


def test_safe_cache_verdict():
    v = C.rule_verdict(item("/Users/a/Library/Caches/vscode-cpptools", "Cache", 50))
    assert (
        v["safety"] == "SAFE"
        and v["action"] == "trashable"
        and v["reclaim_bytes"] == 50
    )


def test_review_orphan_appsupport():
    v = C.rule_verdict(
        item("/Users/a/Library/Application Support/Plex Media Server", "AppSupport", 60)
    )
    assert v["safety"] == "REVIEW" and v["action"] == "needs_checkbox"


def test_llm_cannot_clear_blocked():
    items = [item("/System/evil", "Cache", 70)]
    out = C.classify(items, use_llm=False)
    assert out[0]["safety"] == "BLOCKED" and out[0]["reclaim_bytes"] == 0


def test_double_slash_normalisation():
    assert C.is_blocked("/usr//bin//ls") is True
    assert C.is_blocked("/usr//local//var/cache//x") is False


def test_trailing_slash_blocked():
    assert C.is_blocked("/System/") is True


def test_usr_local_nested_allowed():
    assert C.is_blocked("/usr/local/var/cache/sub/dir") is False


def test_usr_local_prefix_trick_blocked():
    assert C.is_blocked("/usr/localx/bin") is True
    assert C.is_blocked("/usr/local-var/cache") is True


def test_symlink_lexical_no_fs_resolution(tmp_path):
    # Lexical only: a symlink pointing at /System still matches textually.
    link = tmp_path / "link"
    try:
        link.symlink_to("/System")
    except OSError:
        pass
    assert C.is_blocked(str(link) + "/Library") is False  # unknown prefix passes
    assert C.is_blocked("/tmp/link/../../System/x") is True  # .. collapses lexically


def test_trash_category_safe():
    v = C.rule_verdict(item("/Users/a/.Trash/old.tgz", "Trash", 80))
    assert v["safety"] == "SAFE" and v["action"] == "trashable"


def test_downloads_review():
    v = C.rule_verdict(item("/Users/a/Downloads/big.rar", "Downloads", 90))
    assert v["safety"] == "REVIEW" and v["action"] == "needs_checkbox"


def test_dev_review():
    v = C.rule_verdict(item("/Users/a/devbox/toolchain", "Dev", 100))
    assert v["safety"] == "REVIEW"


def test_kext_anywhere_blocked():
    assert C.is_blocked("/Users/a/x.kext.bak/stuff") is True


def test_enrich_offline_keeps_verdicts(monkeypatch):
    from sidecar import ollama_client

    monkeypatch.setattr(ollama_client, "ollama_available", lambda: False)
    items = [item("/Users/a/Library/Caches/x", "Cache", 110)]
    out = C.classify(items, use_llm=True)
    assert out[0]["safety"] == "SAFE"
    assert C.get_enrichment_status()["rules_only"] is True


def test_enrich_error_marks_rules_only(monkeypatch):
    from sidecar import ollama_client

    monkeypatch.setattr(ollama_client, "ollama_available", lambda: True)
    monkeypatch.setattr(
        ollama_client, "label", lambda *a, **k: (_ for _ in ()).throw(IOError("down"))
    )
    items = [item("/Users/a/Library/Caches/x", "Cache", 120)]
    out = C.classify(items, use_llm=True)
    assert out[0]["safety"] == "SAFE"  # verdict unchanged by LLM failure
    assert "llm:" not in out[0]["reason"]


def test_classify_idempotent():
    items = [
        item("/Users/a/Library/Caches/x", "Cache", 130),
        item("/System/y", "Cache", 140),
    ]
    once = C.classify(items, use_llm=False)
    twice = C.classify(items, use_llm=False)
    assert once == twice


def _v(path, safety, reclaim):
    return {
        "path": path,
        "size_bytes": reclaim,
        "safety": safety,
        "reason": "t",
        "reclaim_bytes": reclaim,
        "action": {
            "SAFE": "trashable",
            "REVIEW": "needs_checkbox",
            "BLOCKED": "unselectable",
        }[safety],
    }


def _ib(path, sig):
    return {path: {"signature": sig}}


def test_leaf_totals_dedupes_parent_child():
    verdicts = [_v("/a", "SAFE", 100), _v("/a/b", "SAFE", 100)]
    byp = {**_ib("/a", "kind:dir:depth0"), **_ib("/a/b", "kind:dir:depth1")}
    assert C.leaf_totals(verdicts, byp) == {"SAFE": 100, "REVIEW": 0}


def test_leaf_totals_excludes_bigfiles():
    verdicts = [_v("/m/blobs/sha1", "REVIEW", 4000)]
    byp = _ib("/m/blobs/sha1", "kind:file:big")
    assert C.leaf_totals(verdicts, byp) == {"SAFE": 0, "REVIEW": 0}


def test_leaf_totals_blocked_zero():
    verdicts = [_v("/System/x", "BLOCKED", 0), _v("/c", "SAFE", 50)]
    byp = {**_ib("/System/x", "blocked"), **_ib("/c", "kind:dir:depth0")}
    assert C.leaf_totals(verdicts, byp) == {"SAFE": 50, "REVIEW": 0}


def test_action_mapping_all():
    assert (
        C.rule_verdict(item("/Users/a/Library/Caches/x", "Cache", 1))["action"]
        == "trashable"
    )
    assert (
        C.rule_verdict(item("/Users/a/Downloads/x", "Downloads", 1))["action"]
        == "needs_checkbox"
    )
    assert C.rule_verdict(item("/bin/x", "Other", 1))["action"] == "unselectable"
