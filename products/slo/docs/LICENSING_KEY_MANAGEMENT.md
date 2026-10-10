# Licensing Key Management

The legacy local licensing server is development/test infrastructure only. Generate its Ed25519 key locally with `licensing_server/generate_keypair.py`; never commit its private half or runtime SQLite files.

Production signing uses `LICENSING_PRIVATE_KEY_BASE64` stored as a Fly.io app secret. A missing or invalid production key must fail closed. Do not use a private key exposed in source, shell output, or conversation. The provenance of one removed local rehearsal key is unresolved; see the [operations audit](../../../docs/OPERATIONS_AUDIT_2026-10-08.md). Do not rotate the production signer until existing clients can trust both the old and new public keys.

Use `scripts/check_repository_security.sh` before commits and in CI to reject tracked private keys and licensing runtime databases.
