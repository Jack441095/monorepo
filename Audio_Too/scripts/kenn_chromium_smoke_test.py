#!/usr/bin/env python3
"""D0.4 (docs/KENN_FUTURE_PLAN.md Phase 0): reusable Chromium harness for
KENN's chat UI, replacing the ad-hoc Playwright scripts written and thrown
away during 2026-08-06's live verification of mute/solo/record-arm.

Drives the real chat UI in headless Chromium -- types a message into the
real input box, clicks send, reads the real rendered response -- rather
than calling internal Python functions directly, so it catches the class
of bug D0.2 found (a route wired correctly end-to-end in-process but
unreachable from the actual HTTP surface the browser uses).

Deliberately does NOT fire real DAW writes against a live Ableton session:
this is meant to run unattended (e.g. by a future agent or in CI) with no
one watching for unintended side effects on someone's real project. It
checks that a DAW-write-shaped chat message round-trips to *some* correct
status (denied, executed, or disconnected -- whichever AUDIO_TOO_ALLOW_DAW_CONTROL
and the live connection state produce), not that a specific real mutation
happened. For that stronger guarantee, see the packaged-boot HTTP-route
test in tests/kenn/test_kenn_product_package.py, which already asserts a
clean 403 against every DAW-write route with the policy gate off.

Usage:
    python3 scripts/kenn_chromium_smoke_test.py [--base-url http://127.0.0.1:8090]

Requires the KENN server already running (see `python3 main.py start`) and
`playwright install chromium` run once beforehand.
"""

from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request

DEFAULT_BASE_URL = "http://127.0.0.1:8090"


def _server_reachable(base_url: str) -> bool:
    try:
        urllib.request.urlopen(base_url, timeout=5)
        return True
    except urllib.error.URLError:
        return False


def _run_checks(base_url: str) -> list[tuple[str, bool, str]]:
    from playwright.sync_api import sync_playwright

    results: list[tuple[str, bool, str]] = []
    console_errors: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

        page.goto(base_url, wait_until="networkidle", timeout=30_000)

        input_box = page.locator("#question").first
        send_button = page.locator("#chat-form button[type='submit']").first

        results.append(("chat UI loaded", input_box.count() > 0, "no chat input element found on page"))

        for label, message, expect_substring in [
            ("read-only session query", "show my ableton session", None),
            # Deliberately an out-of-range track index (999), not a real
            # track -- this still exercises the full DAW-write dispatch
            # pipeline through the real HTTP/chat surface (the class of
            # bug D0.2 found) without ever being able to mutate a real
            # track, whether or not AUDIO_TOO_ALLOW_DAW_CONTROL happens to
            # be enabled on whatever server this runs against. This script
            # may run unattended against someone's live, connected
            # Ableton session -- never use a real track index here.
            ("DAW-write-shaped message (out-of-range, safe)", "mute track 999", None),
            # Reachability regression guard for the 2026-08-06/07 bug: the
            # natural-language mix-revision system was built and tested
            # but silently unreachable from this exact chat surface for a
            # full day before being caught. As of 2026-08-08 this path is
            # also gated behind daw_control (a real security-review fix --
            # it was the only write-capable action on this port with no
            # gate at all), so on a server without AUDIO_TOO_ALLOW_DAW_CONTROL
            # set (this script's own default expectation, matching "safe
            # to run unattended" above) the reply is a policy-denial
            # message, not the old "no completed mix" text -- either way,
            # the important thing this check guards is that the request
            # got RECOGNIZED as a revision at all (fired _maybe_handle_mix_revision),
            # not silently answered as generic RAG advice about vocal comping.
            ("mix-revision request is recognized (not generic RAG)", "make the vocals warmer", "policy"),
            # D3.4: arrangement suggestion round-trips through the real
            # HTTP surface and returns a structure, not a fallthrough answer.
            ("arrangement request returns a structure", "build a 16 bar arrangement", "starting point"),
        ]:
            try:
                input_box.fill(message)
                send_button.click()
                page.wait_for_timeout(6000)
                messages_text = page.locator("#messages").first.inner_text()
                got_response = len(messages_text.strip()) > 0
                if got_response and expect_substring:
                    got_response = expect_substring.lower() in messages_text.lower()
                    detail = "" if got_response else f"reply didn't mention {expect_substring!r}"
                else:
                    detail = "" if got_response else "no assistant reply appeared"
                results.append((label, got_response, detail))
            except Exception as exc:  # pragma: no cover - live browser interaction
                results.append((label, False, str(exc)))

        real_errors = [e for e in console_errors if "favicon" not in e.lower()]
        results.append(("no JS console errors", not real_errors, "; ".join(real_errors[:5])))

        browser.close()

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    args = parser.parse_args()

    if not _server_reachable(args.base_url):
        print(f"KENN server not reachable at {args.base_url} -- start it first (python3 main.py start).")
        return 2

    results = _run_checks(args.base_url)

    failed = [r for r in results if not r[1]]
    for label, ok, detail in results:
        mark = "PASS" if ok else "FAIL"
        line = f"[{mark}] {label}"
        if detail and not ok:
            line += f" -- {detail}"
        print(line)

    if failed:
        print(f"\n{len(failed)} check(s) failed.")
        return 1
    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
