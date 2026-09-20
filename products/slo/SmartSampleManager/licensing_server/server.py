"""
Local mock licensing backend for Smart Sample Manager.

This is a DEV/TEST reference implementation of the architecture described in
README.md -- it proves the client<->server activation flow end to end (see
Source/Licensing/LicenseManager.cpp on the client), but it is NOT the
production backend. Before shipping, this needs to be deployed behind real
hosting with TLS, a real database, real auth on the admin endpoints, and a
freshly generated production keypair.

Run:
    ./.venv/bin/uvicorn server:app --reload --port 8420

Authoritative-server principle: the client never gets to declare its own
license state. Every activate/validate call re-derives status from this
server's database and returns a freshly Ed25519-signed token: the client can
only ever replay a signature this server actually produced, and only for the
claims (device, expiry, tier) this server actually decided.
"""
import base64
import json
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from nacl.signing import SigningKey
from pydantic import BaseModel

DB_PATH = Path(__file__).parent / "licensing.db"
KEYS_DIR = Path(__file__).parent / "keys"

# How long a client-held signed token remains valid for OFFLINE use before it
# must successfully re-validate against the server. This is the offline grace
# period from mission section 14 -- long enough that a temporary internet
# outage doesn't lock a working audio engineer out mid-session, short enough
# that a revoked/expired license actually stops working within a bounded time.
OFFLINE_GRACE_PERIOD_SECONDS = 14 * 24 * 60 * 60  # 14 days

app = FastAPI(title="Smart Sample Manager Licensing (DEV)")


def _load_signing_key() -> SigningKey:
    private_path = KEYS_DIR / "signing_key.private"
    if not private_path.exists():
        raise RuntimeError(
            f"No signing key at {private_path}. Run generate_keypair.py first."
        )
    return SigningKey(base64.b64decode(private_path.read_text().strip()))


_signing_key = _load_signing_key()


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init_db() -> None:
    with _db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS licenses (
                license_key TEXT PRIMARY KEY,
                customer_email TEXT NOT NULL,
                product_id TEXT NOT NULL,
                tier TEXT NOT NULL,
                max_activations INTEGER NOT NULL,
                expires_at INTEGER,              -- NULL == perpetual
                revoked INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS activations (
                license_key TEXT NOT NULL,
                device_id TEXT NOT NULL,
                device_name TEXT,
                activated_at INTEGER NOT NULL,
                deactivated_at INTEGER,
                PRIMARY KEY (license_key, device_id),
                FOREIGN KEY (license_key) REFERENCES licenses(license_key)
            );
            """
        )


_init_db()


def _sign_payload(payload: dict) -> dict:
    # Canonical JSON: sorted keys, no incidental whitespace. The client must
    # verify the signature against this EXACT string, not a re-serialization
    # of the parsed object -- JUCE's JSON writer uses different key ordering
    # and spacing than Python's, so re-serializing before verifying would
    # make every legitimately-signed token fail verification. We therefore
    # ship `token_json` as the literal signed string (the client verifies
    # against it directly, then parses it separately for field access) and
    # `token` as a convenience pre-parsed copy for humans poking the API.
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    signature = _signing_key.sign(canonical.encode("utf-8")).signature
    return {
        "token_json": canonical,
        "token": payload,
        "signature": base64.b64encode(signature).decode("ascii"),
    }


class CreateLicenseRequest(BaseModel):
    customer_email: str
    product_id: str = "smart-sample-manager"
    tier: str = "pro"
    max_activations: int = 3
    expires_in_days: Optional[int] = None  # None == perpetual


class ActivateRequest(BaseModel):
    license_key: str
    device_id: str
    device_name: str = ""


class ValidateRequest(BaseModel):
    license_key: str
    device_id: str


class DeactivateRequest(BaseModel):
    license_key: str
    device_id: str


@app.post("/v1/admin/licenses")
def create_license(req: CreateLicenseRequest):
    """
    Stand-in for what a payment-provider webhook (Stripe etc.) would call
    after a successful purchase. Not authenticated here since this is a
    local dev server -- production MUST put real auth on this route, since
    anyone who can call it can mint licenses for free.
    """
    license_key = "-".join(secrets.token_hex(4).upper() for _ in range(4))
    now = int(time.time())
    expires_at = now + req.expires_in_days * 86400 if req.expires_in_days else None

    with _db() as conn:
        conn.execute(
            "INSERT INTO licenses (license_key, customer_email, product_id, tier, "
            "max_activations, expires_at, revoked, created_at) VALUES (?, ?, ?, ?, ?, ?, 0, ?)",
            (license_key, req.customer_email, req.product_id, req.tier,
             req.max_activations, expires_at, now),
        )
    return {"license_key": license_key}


def _get_license(conn: sqlite3.Connection, license_key: str) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM licenses WHERE license_key = ?", (license_key,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="License not found")
    return row


def _license_status(lic: sqlite3.Row, now: int) -> str:
    if lic["revoked"]:
        return "revoked"
    if lic["expires_at"] is not None and lic["expires_at"] < now:
        return "expired"
    return "active"


def _issue_token(lic: sqlite3.Row, device_id: str, now: int) -> dict:
    return _sign_payload(
        {
            "product_id": lic["product_id"],
            "license_key": lic["license_key"],
            "customer_email": lic["customer_email"],
            "device_id": device_id,
            "tier": lic["tier"],
            "issued_at": now,
            "expires_at": lic["expires_at"],
            "check_again_by": now + OFFLINE_GRACE_PERIOD_SECONDS,
        }
    )


@app.post("/v1/activate")
def activate(req: ActivateRequest):
    now = int(time.time())
    with _db() as conn:
        lic = _get_license(conn, req.license_key)
        status = _license_status(lic, now)
        if status != "active":
            raise HTTPException(status_code=403, detail=f"License is {status}")

        existing = conn.execute(
            "SELECT * FROM activations WHERE license_key = ? AND device_id = ?",
            (req.license_key, req.device_id),
        ).fetchone()

        if existing is None:
            active_count = conn.execute(
                "SELECT COUNT(*) FROM activations WHERE license_key = ? AND deactivated_at IS NULL",
                (req.license_key,),
            ).fetchone()[0]
            if active_count >= lic["max_activations"]:
                raise HTTPException(
                    status_code=403,
                    detail=f"Activation limit reached ({lic['max_activations']} devices). "
                    "Deactivate another device first.",
                )
            conn.execute(
                "INSERT INTO activations (license_key, device_id, device_name, activated_at, deactivated_at) "
                "VALUES (?, ?, ?, ?, NULL)",
                (req.license_key, req.device_id, req.device_name, now),
            )
        else:
            # Re-activating a device that was previously deactivated on this
            # same license -- just clear the deactivated_at marker.
            conn.execute(
                "UPDATE activations SET deactivated_at = NULL, activated_at = ?, device_name = ? "
                "WHERE license_key = ? AND device_id = ?",
                (now, req.device_name, req.license_key, req.device_id),
            )

        return _issue_token(lic, req.device_id, now)


@app.post("/v1/validate")
def validate(req: ValidateRequest):
    now = int(time.time())
    with _db() as conn:
        lic = _get_license(conn, req.license_key)
        status = _license_status(lic, now)
        if status != "active":
            raise HTTPException(status_code=403, detail=f"License is {status}")

        activation = conn.execute(
            "SELECT * FROM activations WHERE license_key = ? AND device_id = ? AND deactivated_at IS NULL",
            (req.license_key, req.device_id),
        ).fetchone()
        if activation is None:
            raise HTTPException(status_code=403, detail="Device is not activated for this license")

        return _issue_token(lic, req.device_id, now)


@app.post("/v1/deactivate")
def deactivate(req: DeactivateRequest):
    now = int(time.time())
    with _db() as conn:
        _get_license(conn, req.license_key)
        result = conn.execute(
            "UPDATE activations SET deactivated_at = ? "
            "WHERE license_key = ? AND device_id = ? AND deactivated_at IS NULL",
            (now, req.license_key, req.device_id),
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Active activation not found")
    return {"status": "deactivated"}
