# Licensing Key Management

The legacy local licensing server is development/test infrastructure only. Generate its Ed25519 key locally with `licensing_server/generate_keypair.py`; never commit its private half or runtime SQLite files.

Production signing uses `LICENSING_PRIVATE_KEY_BASE64` injected by Railway. A missing or invalid production key must fail closed. The legacy exposed private key is retired and must never be used for signing again; its public key remains only in the historical development verifier contract.

Use `scripts/check_repository_security.sh` before commits and in CI to reject tracked private keys and licensing runtime databases.
