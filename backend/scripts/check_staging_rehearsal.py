#!/usr/bin/env python3
"""Run the read-only gate for a durable Submit staging rehearsal.

The command probes only public, unauthenticated endpoints. It never sends
mail, calls Paddle, uploads an artifact, changes provider state, or prints
response bodies. A passing result means the service advertises the durable
storage and deliverable-email posture required before a staging customer
journey is treated as proven.

Usage:
    python scripts/check_staging_rehearsal.py --base-url https://api.example

Add ``--require-checkout`` when the rehearsal also includes the Sandbox
checkout path. The default gate deliberately checks infrastructure readiness
and the download authentication boundary without assuming a payment run.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


def validate_health(status_code: int, payload: Any) -> list[str]:
    """Return human-readable failures for the staging liveness response."""
    failures: list[str] = []
    if status_code != 200:
        failures.append(f"GET /health returned HTTP {status_code}, expected 200")
    if not isinstance(payload, dict):
        failures.append("GET /health did not return a JSON object")
        return failures
    if payload.get("status") != "ok":
        failures.append("GET /health did not report status=ok")
    if payload.get("environment") != "staging":
        failures.append("GET /health did not report environment=staging")
    return failures


def validate_ready(
    status_code: int,
    payload: Any,
    *,
    require_checkout: bool = False,
) -> list[str]:
    """Return failures for the durable staging readiness contract."""
    failures: list[str] = []
    if status_code != 200:
        failures.append(f"GET /ready returned HTTP {status_code}, expected 200")
    if not isinstance(payload, dict):
        failures.append("GET /ready did not return a JSON object")
        return failures

    for field in (
        "database",
        "storage",
        "storage_durable",
        "email_provider_configured",
        "email_deliverable",
        "staging_customer_rehearsal",
        "staging_customer_rehearsal_ready",
    ):
        if payload.get(field) is not True:
            failures.append(f"GET /ready field {field}=true is required")

    if payload.get("status") != "ok":
        failures.append("GET /ready did not report status=ok")
    if payload.get("storage_backend") != "s3":
        failures.append("GET /ready field storage_backend=s3 is required")
    if payload.get("email_provider") != "resend":
        failures.append("GET /ready field email_provider=resend is required")
    if require_checkout and payload.get("checkout_enabled") is not True:
        failures.append("GET /ready field checkout_enabled=true is required")
    return failures


def validate_download_auth(status_code: int) -> list[str]:
    """Ensure the unauthenticated download route remains protected."""
    if status_code == 401:
        return []
    return [f"GET /downloads/latest returned HTTP {status_code}, expected 401"]


def _request_json(url: str, timeout: float) -> tuple[int | None, Any, str | None]:
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "nite-dsp-staging-rehearsal-gate/1",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            status_code = response.status
            raw_body = response.read()
    except HTTPError as error:
        status_code = error.code
        try:
            raw_body = error.read()
        except OSError:
            raw_body = b""
    except (URLError, TimeoutError, OSError) as error:
        return None, None, type(error).__name__

    try:
        return status_code, json.loads(raw_body), None
    except (UnicodeDecodeError, json.JSONDecodeError):
        return status_code, None, "invalid JSON response"


def _request_status(url: str, timeout: float) -> tuple[int | None, str | None]:
    request = Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "nite-dsp-staging-rehearsal-gate/1"},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.status, None
    except HTTPError as error:
        return error.code, None
    except (URLError, TimeoutError, OSError) as error:
        return None, type(error).__name__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        required=True,
        help="public HTTPS base URL for the staging backend, e.g. https://api-staging.example",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=15.0,
        help="per-request timeout in seconds (default: 15)",
    )
    parser.add_argument(
        "--require-checkout",
        action="store_true",
        help="also require checkout_enabled=true in the readiness response",
    )
    parser.add_argument(
        "--allow-http-local",
        action="store_true",
        help="allow an http:// URL for a local fixture or tunnel; never use for Railway",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.timeout <= 0:
        print("staging rehearsal gate failed: --timeout must be greater than zero", file=sys.stderr)
        return 2

    parsed = urlparse(args.base_url)
    if not parsed.hostname or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        print("staging rehearsal gate failed: --base-url must be an origin without a path or query", file=sys.stderr)
        return 2
    if parsed.scheme != "https" and not (args.allow_http_local and parsed.scheme == "http"):
        print("staging rehearsal gate failed: --base-url must use HTTPS", file=sys.stderr)
        return 2
    base_url = args.base_url.rstrip("/")

    failures: list[str] = []
    health_status, health_payload, health_error = _request_json(f"{base_url}/health", args.timeout)
    if health_error:
        failures.append(f"GET /health failed before receiving JSON ({health_error})")
    else:
        failures.extend(validate_health(health_status or 0, health_payload))

    ready_status, ready_payload, ready_error = _request_json(f"{base_url}/ready", args.timeout)
    if ready_error:
        failures.append(f"GET /ready failed before receiving JSON ({ready_error})")
    else:
        failures.extend(
            validate_ready(
                ready_status or 0,
                ready_payload,
                require_checkout=args.require_checkout,
            )
        )

    download_status, download_error = _request_status(f"{base_url}/downloads/latest", args.timeout)
    if download_error:
        failures.append(f"GET /downloads/latest failed ({download_error})")
    else:
        failures.extend(validate_download_auth(download_status or 0))

    if failures:
        print("staging rehearsal gate: FAIL")
        for failure in failures:
            print(f"- {failure}")
        return 1

    checkout_note = ", checkout" if args.require_checkout else ""
    print(f"staging rehearsal gate: PASS (health, durable readiness{checkout_note}, download auth)")
    print(f"base_url={base_url}")
    print("provider state unchanged; no artifact upload or email/Paddle request made")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
