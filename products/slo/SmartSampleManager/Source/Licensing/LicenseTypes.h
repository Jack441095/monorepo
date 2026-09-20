#pragma once

#include <juce_audio_utils/juce_audio_utils.h>

namespace Licensing {

enum class Status {
    // No license has ever been activated on this device.
    notActivated,
    // A signature-verified, non-expired license is present and either the
    // server confirmed it recently or we're still inside the offline grace
    // window from the last successful check.
    active,
    // We have a previously-valid license on disk, but its offline grace
    // period (checkAgainBy) has elapsed and we haven't been able to reach
    // the server to refresh it. Not yet a hard failure -- the caller decides
    // how strict to be (mission section 14: don't brick the app just
    // because the internet is briefly down).
    needsRevalidation,
    // The server said the license is expired, revoked, or the local token's
    // signature/format failed verification (tamper or corruption).
    invalid,
};

// The verified, decoded contents of a server-issued license token. Only
// constructed by LicenseManager after a successful Ed25519 signature check
// against the embedded public key -- nothing in this struct should ever be
// trusted if it came from anywhere else.
struct LicenseToken {
    juce::String productId;
    juce::String licenseKey;
    juce::String customerEmail;
    juce::String deviceId;
    juce::String tier;
    juce::int64 issuedAt = 0;
    juce::int64 expiresAt = 0;      // 0 == perpetual (no expiry)
    juce::int64 checkAgainBy = 0;   // offline grace period deadline, server-set

    bool isPerpetual() const { return expiresAt == 0; }
};

struct LicenseState {
    Status status = Status::notActivated;
    LicenseToken token;
    juce::String lastError;
};

} // namespace Licensing
