"""Issue NITE Submit's offline licence format from the matching signing key."""
from __future__ import annotations

import base64
import binascii
import struct
import time

from nacl.signing import SigningKey

# This public key is compiled into LicenseEngine.swift. A different private
# key can produce plausible-looking NTSUB1 strings that every shipped app rejects.
SUBMIT_LICENSE_PUBLIC_KEY_BASE64 = "kxzasvgjtZIqSnwQ2Gfh9FlkHSt9oHb4slC1YFAas4g="


def load_submit_signing_key(private_key_base64: str) -> SigningKey:
    """Load a Submit signer and reject keys the shipped app cannot verify."""
    if not private_key_base64.strip():
        raise ValueError("submit_license_private_key_base64 is required for NITE Submit checkout")
    try:
        private_bytes = base64.b64decode(private_key_base64.strip(), validate=True)
        expected_public_key = base64.b64decode(SUBMIT_LICENSE_PUBLIC_KEY_BASE64, validate=True)
        signing_key = SigningKey(private_bytes)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("submit_license_private_key_base64 is not valid Ed25519 key material") from exc

    if bytes(signing_key.verify_key) != expected_public_key:
        raise ValueError("submit licence signing key does not match the NITE Submit app public key")
    return signing_key


def generate_submit_license_key(private_key_base64: str, issued_at: int | None = None) -> str:
    """Return a client-verifiable NTSUB1 key with a little-endian Unix timestamp."""
    timestamp = int(time.time()) if issued_at is None else issued_at
    if not isinstance(timestamp, int) or not 0 <= timestamp <= 0xFFFFFFFF:
        raise ValueError("Submit licence timestamp is outside the supported Unix-time range")

    payload = struct.pack("<I", timestamp)
    signature = load_submit_signing_key(private_key_base64).sign(payload).signature
    encoded = base64.urlsafe_b64encode(payload + signature).decode("ascii").rstrip("=")
    return f"NTSUB1-{encoded}"
