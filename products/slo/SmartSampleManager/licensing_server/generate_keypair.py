"""
Generates the licensing backend's Ed25519 signing keypair.

Run this ONCE per environment (dev, staging, production are separate
keypairs -- never share one across environments). The private key never
leaves the server; the public key gets embedded in the desktop client
(see Source/Licensing/LicensePublicKey.h on the client side).

    ./.venv/bin/python generate_keypair.py
"""
import base64
from pathlib import Path

from nacl.signing import SigningKey

OUT_DIR = Path(__file__).parent / "keys"


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    private_path = OUT_DIR / "signing_key.private"
    if private_path.exists():
        raise SystemExit(
            f"{private_path} already exists -- refusing to overwrite an "
            "existing signing key. Delete it manually first if you really "
            "want to rotate keys (this invalidates every license issued "
            "under the old key)."
        )

    signing_key = SigningKey.generate()
    verify_key = signing_key.verify_key

    private_b64 = base64.b64encode(bytes(signing_key)).decode("ascii")
    public_b64 = base64.b64encode(bytes(verify_key)).decode("ascii")

    private_path.write_text(private_b64)
    private_path.chmod(0o600)
    (OUT_DIR / "signing_key.public").write_text(public_b64)

    print(f"Private key written to {private_path} (chmod 600, gitignored).")
    print(f"Public key written to {OUT_DIR / 'signing_key.public'}.")
    print()
    print("Public key (base64) -- embed this in the client:")
    print(f"  {public_b64}")


if __name__ == "__main__":
    main()
