"""JSON reference routes report absent evidence without inventing EQ moves."""

import json
import threading
from collections import defaultdict, deque
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest


REFERENCE_PATHS = [
    "/api/reference/analyze",
    "/kenn/api/reference/analyze",
    "/api/reference/match-curve",
    "/kenn/api/reference/match-curve",
]


@pytest.fixture
def reference_http(monkeypatch):
    import kenn.server as server
    import kenn.server_rate_limit as rate_limit

    monkeypatch.setattr(rate_limit, "RATE_BUCKETS", defaultdict(deque))
    httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    worker = threading.Thread(target=lambda: httpd.serve_forever(poll_interval=0.01), daemon=True)
    worker.start()

    def post(path, payload):
        request = Request(
            f"http://127.0.0.1:{httpd.server_port}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            response = urlopen(request, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.loads(response.read().decode("utf-8"))

    try:
        yield post
    finally:
        httpd.shutdown()
        worker.join(timeout=5)
        httpd.server_close()


@pytest.mark.parametrize("path", REFERENCE_PATHS)
@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"session_spectrum": [], "reference_spectrum": []},
        {"session_spectrum": None, "reference_spectrum": None},
        {"session_spectrum": [-20.0] * 40},
        {"session_spectrum": [-20.0] * 39, "reference_spectrum": [-20.0] * 40},
        {"session_spectrum": [-20.0] * 40, "reference_spectrum": [None] * 40},
        {"session_spectrum": [True] * 40, "reference_spectrum": [-20.0] * 40},
        {"session_spectrum": ["-20.0"] * 40, "reference_spectrum": [-20.0] * 40},
    ],
)
def test_reference_json_route_rejects_missing_invalid_or_incomplete_measurements(reference_http, path, payload):
    # Both aliases used to report HTTP 200 and four EQ moves for an empty body.
    status, result = reference_http(path, payload)
    assert status == 400
    assert result["ok"] is False
    assert result["error"]
    report = result.get("analysis", result)
    assert report["available"] is False
    assert report["delta_curve"] == []
    assert report["eq_recipe"] == []
    assert report["rms_spectral_delta_db"] is None
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("path", REFERENCE_PATHS)
def test_reference_json_route_keeps_measured_difference_and_does_not_reuse_it(reference_http, path):
    session = [-20.0] * 40
    reference = [-20.0] * 40
    reference[30] = -17.0
    status, result = reference_http(path, {
        "session_spectrum": session,
        "reference_spectrum": reference,
        "reference_name": "Measured fixture",
    })
    assert status == 200 and result["ok"] is True
    report = result.get("analysis", result)
    assert report["available"] is True
    assert len(report["delta_curve"]) == 40
    assert report["delta_curve"][30]["delta_db"] == 3.0
    assert len(report["eq_recipe"]) == 4
    assert report["rms_spectral_delta_db"] > 0.0

    missing_status, missing = reference_http(path, {})
    assert missing_status == 400 and missing["ok"] is False
    missing_report = missing.get("analysis", missing)
    assert missing_report["available"] is False
    assert missing_report["delta_curve"] == []
    assert missing_report["eq_recipe"] == []
    assert missing_report["rms_spectral_delta_db"] is None
    assert report["delta_curve"][30]["delta_db"] == 3.0


@pytest.mark.parametrize("path", REFERENCE_PATHS)
def test_reference_json_route_rejects_nonfinite_numbers_before_comparison(reference_http, path):
    status, result = reference_http(path, {
        "session_spectrum": [float("nan")] * 40,
        "reference_spectrum": [-20.0] * 40,
    })
    assert status == 400 and result["error"]
    assert not result.get("eq_recipe") and not result.get("delta_curve")
    assert not result.get("analysis", {}).get("eq_recipe")
