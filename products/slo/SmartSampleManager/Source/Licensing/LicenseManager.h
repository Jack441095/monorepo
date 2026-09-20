#pragma once

#include "LicenseTypes.h"

// Client-side half of the licensing architecture. Talks to licensing_server/
// (a local mock backend for dev/test -- see that directory's README for what
// changes before this can point at a real production deployment).
//
// Design principles this follows (see mission doc sections 11/14/35):
//  - The server is authoritative. This class never invents or upgrades a
//    license state locally -- every Status::active comes from either a
//    signature-verified token the server actually issued, or honoring that
//    same token's server-set offline grace period while unreachable.
//  - Asymmetric signing: only a public key lives here (LicensePublicKey.h).
//    The private signing key never leaves the server.
//  - Not wired into app startup/feature-gating yet -- this is infrastructure
//    only. See licensing_server/README.md for what's still required before
//    this should ever block a real user from running the app.
//
// All network methods below are synchronous (blocking) for simplicity and
// testability -- callers integrating this into UI code must run them off
// the message thread (e.g. via juce::ThreadPool, as SampleManagerEngine
// already does for its own background work) rather than adding a second,
// redundant async layer in here.
class LicenseManager {
public:
    LicenseManager();
    ~LicenseManager();

    // Loads and signature-verifies any license persisted from a previous
    // activate()/revalidate() call. Pure local check, no network I/O.
    Licensing::LicenseState loadPersisted() const;

    // POST /v1/activate. On success, persists the returned signed token to
    // disk and returns Status::active.
    Licensing::LicenseState activate(const juce::String& licenseKey);

    // POST /v1/validate for the currently-persisted license + device. On
    // success, refreshes the persisted token (new checkAgainBy deadline).
    // If there's no persisted license to revalidate, returns notActivated.
    Licensing::LicenseState revalidate();

    // POST /v1/deactivate, then clears the local license file regardless of
    // whether the server call succeeded -- a legitimate user can always
    // free this device locally, even if offline; the seat itself only frees
    // up on the server once it's reachable, which is an acceptable
    // asymmetry (worst case: they burn an activation slot until they're
    // back online to fully deactivate, not "your app stops working").
    bool deactivate();

    // Stable per-install random device identifier (a generated UUID kept
    // in the app's data directory, NOT a hardware fingerprint) -- see
    // mission section 19: privacy-by-design, no invasive device tracking.
    juce::String getDeviceId() const;

    // Overridable via SMART_SAMPLE_MANAGER_LICENSE_SERVER_URL env var so
    // tests/staging can point elsewhere without a rebuild. Defaults to the
    // local dev mock server. Plain HTTP is accepted only for localhost,
    // 127.0.0.1, or ::1; all non-local endpoints must use https:// so
    // credentials/license keys never travel over plain HTTP.
    static juce::String serverBaseURL();

private:
    bool verifyAndDecode(const juce::String& tokenJson,
                          const juce::String& signatureBase64,
                          Licensing::LicenseToken& outToken,
                          juce::String& outError) const;

    Licensing::LicenseState evaluateToken(const Licensing::LicenseToken& token) const;

    void persistToken(const juce::String& tokenJson, const juce::String& signatureBase64) const;
    bool loadRawToken(juce::String& outTokenJson, juce::String& outSignatureBase64) const;
    void clearPersistedToken() const;

    juce::File getLicenseFile() const;
    juce::File getDeviceIdFile() const;

    // Posts `body` as JSON to serverBaseURL() + path. Returns false with
    // outError set on any transport, HTTP-status, or JSON-parse failure.
    bool postJson(const juce::String& path, const juce::var& body,
                  juce::var& outResponse, juce::String& outError) const;

    JUCE_DECLARE_NON_COPYABLE(LicenseManager)
};
