"""
Generates the NITE DSP staging backend's Ed25519 signing keypair.

Mirrors licensing_server/generate_keypair.py exactly (Section 17: reuse the
crypto, don't reinvent it) -- same key format, same base64 encoding, same
refuse-to-overwrite safety. This staging keypair is cryptographically
unrelated to any future production key (docs/LICENSE_KEY_LIFECYCLE.md)
and to the dev licensing_server's own key.

Run once per local setup:
    ./.venv/bin/python scripts/generate_staging_keypair.py
"""
import base64
from pathlib import Path

from nacl.signing import SigningKey

OUT_DIR = Path(__file__).parent.parent / "staging_keys"


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    private_path = OUT_DIR / "licensing_signing_key.private"
    if private_path.exists():
        raise SystemExit(
            f"{private_path} already exists -- refusing to overwrite an "
            "existing signing key. Delete it manually first if you really "
            "want to rotate the staging key (this invalidates every "
            "staging license issued under the old key)."
        )

    signing_key = SigningKey.generate()
    verify_key = signing_key.verify_key

    private_b64 = base64.b64encode(bytes(signing_key)).decode("ascii")
    public_b64 = base64.b64encode(bytes(verify_key)).decode("ascii")

    private_path.write_text(private_b64)
    private_path.chmod(0o600)
    (OUT_DIR / "licensing_signing_key.public").write_text(public_b64)

    print(f"Private key written to {private_path} (chmod 600, gitignored).")
    print(f"Public key written to {OUT_DIR / 'licensing_signing_key.public'}.")


if __name__ == "__main__":
    main()
