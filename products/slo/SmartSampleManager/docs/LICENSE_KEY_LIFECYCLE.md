# NITE DSP License Key Lifecycle (Design Only)

Phase 3, Sections 20-21. Covers signing-key generation, storage, and rotation design. **Design
only — no production key has been generated.**

## Correction to Phase 2's assumption

`docs/NITE_DSP_COMMERCIAL_ARCHITECTURE.md` (Phase 2) proposed adding a `product_id` field to the
license token, assuming it didn't exist. **Verified against the real source this pass
(`Source/Licensing/LicenseTypes.h`) — it already exists**: `LicenseToken::productId` is already
a field, already product-aware. No client-side schema change is needed for product-awareness at
all. This document corrects that assumption rather than repeating it.

## Current token structure (verified, `Source/Licensing/LicenseTypes.h`)

```cpp
struct LicenseToken {
    juce::String productId;       // already present -- product-aware today
    juce::String licenseKey;
    juce::String customerEmail;
    juce::String deviceId;
    juce::String tier;
    juce::int64 issuedAt = 0;
    juce::int64 expiresAt = 0;      // 0 == perpetual
    juce::int64 checkAgainBy = 0;   // offline grace deadline, server-set
};
```

For production, `productId` would simply be set to `"smart-sample-manager"` (matching the
`products.id` slug in `docs/NITE_DSP_DATABASE_SCHEMA.md`) at token-issuance time — no client
rebuild required for this specifically.

## Production key generation

```text
1. A real, secure production environment must exist first (production hosting +
   secrets storage -- docs/HUMAN_COMMERCIAL_REQUIREMENTS.md)
2. Run generate_keypair.py (the existing script, unmodified -- Section 17 forbids
   rewriting the crypto) directly in that production environment
3. Private key goes immediately into the environment's secrets manager -- never
   written to a file the deploying human's own machine can retain a copy of
4. Public key is compiled into the client (Source/Licensing/LicensePublicKey.h),
   replacing the dev key
```

**If a secure production environment doesn't exist yet, this step does not happen.** Per Section
20's explicit stop condition, generating a "production" key on a developer laptop or in this
sandboxed environment and calling it production would be worse than not having one — it creates
false confidence in a key that was never actually secured. Marked:

# HUMAN ACTION REQUIRED

## Where the private key must NEVER exist

Repository, client binary, installer, frontend/website code, documentation, public CI logs,
downloadable artifacts. This list matches Section 20 exactly and is a hard constraint, not a
guideline — the existing dev-key handling already gets this right (the dev private key lives only
in `licensing_server/keys/`, gitignored, regenerated per-CI-run as an ephemeral throwaway — see
`docs/TEST_COVERAGE_AUDIT.md`'s CI isolation section) and production must inherit the same
discipline, just with a real secrets manager instead of "gitignored file."

## Key rotation design (Section 21)

Not implementing a full PKI — Phase 3's own Section 83 explicitly warns against overengineering.
The minimal design that supports a future rotation without breaking every existing license:

```text
Client embeds an ARRAY of trusted public keys, not a single one:

    static constexpr const char* kTrustedPublicKeys[] = {
        "<current-key-base64>",
        // future: "<next-key-base64>",  -- added in a client update, ahead of rotation
    };
```

Rotation sequence, when it's eventually needed (compromised key, routine hygiene):

```text
1. Generate the NEW keypair in the secure production environment
2. Ship a client update that trusts BOTH the old and new public keys
   (a grace period client release)
3. Once enough of the install base has updated (telemetry-free approximation:
   wait a few release cycles, matching typical DAW-plugin update adoption
   curves), switch the LICENSING SERVER to sign new tokens with the new key
4. Existing OLD tokens still verify fine (clients trust both keys) until they
   naturally expire/refresh and get reissued under the new key
5. After a further grace period, ship a client update that drops the old
   key from the trusted list
```

This avoids ever having a "flag day" where every existing customer's license breaks
simultaneously — consistent with the offline-grace-period philosophy already built into the
client (`docs/LICENSING_PRODUCTION_GAP.md`).

**Client-side code change required to support this**: `LicenseManager::verifyAndDecode` currently
checks against a single embedded public key (`LicensePublicKey.h`). Supporting multi-key trust
requires iterating the array and accepting the first key that verifies — a small, well-scoped
change, **not implemented this pass** since there's no production key yet to rotate away from;
this is documented as the design for when rotation is first actually needed, not built speculatively
ahead of that need.

## Status

**Design only.** No production key exists. No client code change for multi-key rotation support
has been made (correctly deferred — no key to rotate yet).
