"""Infrastructure / deployment health (Thursday Ops upgrade, phase 8).

Real, live HTTP reachability checks against NITE DSP's actual production
endpoints -- the one thing genuinely missing from every other Ops-upgrade
module tonight, all of which read local files or local databases. Uses
`curl` via subprocess rather than Python's `urllib`/`ssl`: this
environment's Python lacks a working local CA bundle (confirmed --
`urllib.request.urlopen` fails `CERTIFICATE_VERIFY_FAILED` even against
google.com), while `curl` uses the system certificate store and is
confirmed working against the real production URLs. Read-only GET only
(`-o /dev/null`, discards the body), a strict per-request timeout, no
retries -- a single failed check is reported honestly, not retried into a
false positive.

Endpoints and their contracts are documented in
docs/NITE_DSP_SOURCE_OF_TRUTH_AND_RAILWAY_RUNBOOK_V1.md (cited, not
duplicated -- same discipline as funding_ops.py). This module answers
exactly one question per endpoint: did it respond, and with what status
code, right now. It does NOT replace
docs/NITE_DSP_INFRASTRUCTURE_READINESS_SCORECARD_V1.md's broader
narrative status (payments, licensing, releases, security, support,
backups) -- that scorecard is a dated snapshot requiring human judgment
across many systems this module doesn't touch at all; conflating "the
website responded 200 just now" with "infrastructure is ready" would be
exactly the kind of overclaim this whole Ops upgrade has avoided all
night.
"""

from __future__ import annotations

import subprocess

TARGETS = {
    "website": "https://www.nitedsp.co.uk",
    "api_health": "https://api.nitedsp.co.uk/health",
    "api_ready": "https://api.nitedsp.co.uk/ready",
}

_TIMEOUT_SECONDS = 5


def check_url(url: str, *, timeout: int = _TIMEOUT_SECONDS) -> dict:
    """One real, live GET via curl. Never raises -- every failure mode
    (timeout, DNS failure, connection refused, non-numeric response)
    reports {"reachable": False, "error": <reason>} rather than crashing
    the caller or silently reporting success.
    """
    try:
        result = subprocess.run(
            ["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}",
             "--max-time", str(timeout), url],
            capture_output=True, text=True, timeout=timeout + 3,
        )
    except subprocess.TimeoutExpired:
        return {"reachable": False, "status_code": None, "error": "timed out (subprocess)"}
    except FileNotFoundError:
        return {"reachable": False, "status_code": None, "error": "curl not found on this system"}
    except Exception as exc:
        return {"reachable": False, "status_code": None, "error": str(exc)}

    if result.returncode != 0:
        stderr = result.stderr.strip()
        return {"reachable": False, "status_code": None, "error": stderr or f"curl exit code {result.returncode}"}

    code = result.stdout.strip()
    if not code.isdigit():
        return {"reachable": False, "status_code": None, "error": f"unexpected curl output: {code!r}"}

    return {"reachable": True, "status_code": int(code), "error": None}


def deployment_health_check() -> str:
    lines = ["DEPLOYMENT HEALTH CHECK", ""]
    reachable_count = 0

    for name, url in TARGETS.items():
        result = check_url(url)
        if result["reachable"]:
            reachable_count += 1
            code = result["status_code"]
            status = "reachable" if 200 <= code < 300 else "reachable, non-2xx"
            lines.append(f"  {name} ({url}): HTTP {code} — {status}")
        else:
            lines.append(f"  {name} ({url}): UNREACHABLE — {result['error']}")

    lines.append("")
    lines.append(f"{reachable_count}/{len(TARGETS)} endpoints reachable just now.")
    lines.append("")
    lines.append(
        "Live reachability only (curl, 5s timeout, checked at request time) "
        "-- not a full readiness audit. See "
        "docs/NITE_DSP_INFRASTRUCTURE_READINESS_SCORECARD_V1.md for the "
        "broader narrative status (payments, licensing, releases, "
        "security, support, backups), none of which this check verifies. "
        "A 200 here means the endpoint answered, not that the product is "
        "ready to sell."
    )

    return "\n".join(lines)
