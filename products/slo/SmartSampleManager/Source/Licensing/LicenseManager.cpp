#include "LicenseManager.h"
#include "LicensePublicKey.h"

#include <sodium.h>
#include <string>

namespace {

bool isAllowedLicenseServerURL(const juce::String& rawURL) {
    const auto candidate = rawURL.trim().toLowerCase().toStdString();

    // Production/staging endpoints must use TLS.  The only intentional HTTP
    // exception is the loopback-only development server documented in
    // licensing_server/README.md.
    if (candidate.rfind("https://", 0) == 0)
        return true;
    if (candidate.rfind("http://", 0) != 0)
        return false;

    auto authority = candidate.substr(7);
    const auto pathStart = authority.find_first_of("/?#");
    if (pathStart != std::string::npos)
        authority.resize(pathStart);

    // Do not permit user-info syntax to turn a loopback-looking URL into an
    // ambiguous credential-bearing endpoint.
    if (authority.find('@') != std::string::npos)
        return false;

    std::string host = authority;
    if (!host.empty() && host.front() == '[') {
        const auto closingBracket = host.find(']');
        if (closingBracket == std::string::npos)
            return false;
        host.resize(closingBracket + 1);
    } else {
        const auto portStart = host.find(':');
        if (portStart != std::string::npos)
            host.resize(portStart);
    }

    return host == "localhost" || host == "127.0.0.1" || host == "[::1]";
}

juce::int64 nowUnixSeconds() {
    return static_cast<juce::int64>(juce::Time::getCurrentTime().toMilliseconds() / 1000);
}

juce::File appDataDir() {
    auto dir = juce::File::getSpecialLocation(juce::File::userApplicationDataDirectory)
                   .getChildFile("SmartSampleManager");
    dir.createDirectory();
    return dir;
}

} // namespace

LicenseManager::LicenseManager() {
    // sodium_init() is safe to call more than once (subsequent calls are a
    // cheap no-op returning 1) and from multiple translation units, so no
    // extra guarding needed here.
    if (sodium_init() < 0) {
        jassertfalse; // libsodium failed to initialize -- treat as a build/environment bug
    }
}

LicenseManager::~LicenseManager() = default;

juce::String LicenseManager::serverBaseURL() {
    if (auto envOverride = juce::SystemStats::getEnvironmentVariable(
            "SMART_SAMPLE_MANAGER_LICENSE_SERVER_URL", {});
        envOverride.isNotEmpty()) {
        auto candidate = envOverride.trim();
        return isAllowedLicenseServerURL(candidate) ? candidate : juce::String();
    }
    // Local dev mock server (see licensing_server/). Production builds must
    // override this to a real https:// domain -- see licensing_server/README.md.
    return "http://localhost:8420";
}

juce::File LicenseManager::getLicenseFile() const {
    return appDataDir().getChildFile("license.json");
}

juce::File LicenseManager::getDeviceIdFile() const {
    return appDataDir().getChildFile("device_id.txt");
}

juce::String LicenseManager::getDeviceId() const {
    auto file = getDeviceIdFile();
    if (file.existsAsFile()) {
        auto existing = file.loadFileAsString().trim();
        if (existing.isNotEmpty())
            return existing;
    }
    auto newId = juce::Uuid().toString();
    file.replaceWithText(newId);
    return newId;
}

bool LicenseManager::postJson(const juce::String& path, const juce::var& body,
                               juce::var& outResponse, juce::String& outError) const {
    const auto baseURL = serverBaseURL();
    if (baseURL.isEmpty()) {
        outError = "Licensing server URL rejected (HTTPS is required for non-local endpoints)";
        return false;
    }

    juce::URL url(baseURL + path);
    url = url.withPOSTData(juce::JSON::toString(body, true));

    int statusCode = 0;
    auto options = juce::URL::InputStreamOptions(juce::URL::ParameterHandling::inPostData)
                       .withExtraHeaders("Content-Type: application/json")
                       .withConnectionTimeoutMs(8000)
                       .withStatusCode(&statusCode);

    std::unique_ptr<juce::InputStream> stream(url.createInputStream(options));
    if (stream == nullptr) {
        outError = "Could not reach licensing server (network/connection failure)";
        return false;
    }

    auto responseText = stream->readEntireStreamAsString();
    auto parsed = juce::JSON::parse(responseText);

    if (statusCode < 200 || statusCode >= 300) {
        if (auto* obj = parsed.getDynamicObject(); obj != nullptr && obj->hasProperty("detail"))
            outError = obj->getProperty("detail").toString();
        else
            outError = "Server returned HTTP " + juce::String(statusCode);
        return false;
    }

    outResponse = parsed;
    return true;
}

bool LicenseManager::verifyAndDecode(const juce::String& tokenJson,
                                      const juce::String& signatureBase64,
                                      Licensing::LicenseToken& outToken,
                                      juce::String& outError) const {
    // Note: juce::MemoryBlock::fromBase64Encoding uses a JUCE-proprietary
    // encoding (size-prefixed, not RFC 4648), incompatible with the
    // standard base64 the Python server emits -- juce::Base64::convertFromBase64
    // is the standard-compliant one and what actually interops here.
    juce::MemoryBlock signatureBytes, publicKeyBytes;
    {
        bool convOk;
        {
            // MemoryOutputStream grows its backing block geometrically and
            // only trims it back to the actual bytes written when the
            // stream flushes/destructs -- checking signatureBytes.getSize()
            // while sigStream is still alive would see that over-allocated
            // capacity, not the real decoded length. Scoping the stream
            // tightly so it's gone before we inspect the block.
            juce::MemoryOutputStream sigStream(signatureBytes, false);
            convOk = juce::Base64::convertFromBase64(sigStream, signatureBase64);
        }
        if (!convOk ||
            signatureBytes.getSize() != crypto_sign_BYTES) {
            outError = "Malformed signature";
            return false;
        }
    }
    {
        bool convOk;
        {
            juce::MemoryOutputStream keyStream(publicKeyBytes, false);
            convOk = juce::Base64::convertFromBase64(keyStream, Licensing::kServerPublicKeyBase64);
        }
        if (!convOk ||
            publicKeyBytes.getSize() != crypto_sign_PUBLICKEYBYTES) {
            outError = "Malformed embedded public key (build configuration bug)";
            return false;
        }
    }

    auto tokenUtf8 = tokenJson.toUTF8();
    auto messageLen = tokenJson.getNumBytesAsUTF8();

    if (crypto_sign_verify_detached(
            static_cast<const unsigned char*>(signatureBytes.getData()),
            reinterpret_cast<const unsigned char*>(tokenUtf8.getAddress()),
            messageLen,
            static_cast<const unsigned char*>(publicKeyBytes.getData())) != 0) {
        outError = "Signature verification failed (tampered or corrupt license data)";
        return false;
    }

    // Signature is valid -- the bytes genuinely came from whoever holds the
    // server's private key. Only now is it safe to trust the parsed fields.
    auto parsed = juce::JSON::parse(tokenJson);
    auto* obj = parsed.getDynamicObject();
    if (obj == nullptr) {
        outError = "Signed token was not valid JSON (should be impossible if signature verified)";
        return false;
    }

    outToken.productId = obj->getProperty("product_id").toString();
    outToken.licenseKey = obj->getProperty("license_key").toString();
    outToken.customerEmail = obj->getProperty("customer_email").toString();
    outToken.deviceId = obj->getProperty("device_id").toString();
    outToken.tier = obj->getProperty("tier").toString();
    outToken.issuedAt = static_cast<juce::int64>(static_cast<double>(obj->getProperty("issued_at")));
    outToken.expiresAt = obj->getProperty("expires_at").isVoid()
                              ? 0
                              : static_cast<juce::int64>(static_cast<double>(obj->getProperty("expires_at")));
    outToken.checkAgainBy = static_cast<juce::int64>(static_cast<double>(obj->getProperty("check_again_by")));
    return true;
}

Licensing::LicenseState LicenseManager::evaluateToken(const Licensing::LicenseToken& token) const {
    Licensing::LicenseState state;
    state.token = token;

    auto now = nowUnixSeconds();
    if (!token.isPerpetual() && token.expiresAt < now) {
        state.status = Licensing::Status::invalid;
        state.lastError = "License expired";
        return state;
    }

    // A token fresh off activate()/revalidate() always has checkAgainBy in
    // the future, so this naturally evaluates to `active`; a token loaded
    // from disk with no network contact falls through to
    // needsRevalidation once its grace window has passed. Same rule, both
    // call sites -- no separate "offline" code path needed.
    state.status = (now <= token.checkAgainBy) ? Licensing::Status::active
                                                : Licensing::Status::needsRevalidation;
    return state;
}

void LicenseManager::persistToken(const juce::String& tokenJson, const juce::String& signatureBase64) const {
    auto* obj = new juce::DynamicObject();
    obj->setProperty("token_json", tokenJson);
    obj->setProperty("signature", signatureBase64);
    getLicenseFile().replaceWithText(juce::JSON::toString(juce::var(obj)));
}

bool LicenseManager::loadRawToken(juce::String& outTokenJson, juce::String& outSignatureBase64) const {
    auto file = getLicenseFile();
    if (!file.existsAsFile())
        return false;

    auto parsed = juce::JSON::parse(file.loadFileAsString());
    auto* obj = parsed.getDynamicObject();
    if (obj == nullptr || !obj->hasProperty("token_json") || !obj->hasProperty("signature"))
        return false;

    outTokenJson = obj->getProperty("token_json").toString();
    outSignatureBase64 = obj->getProperty("signature").toString();
    return true;
}

void LicenseManager::clearPersistedToken() const {
    getLicenseFile().deleteFile();
}

Licensing::LicenseState LicenseManager::loadPersisted() const {
    Licensing::LicenseState state;

    juce::String tokenJson, signatureBase64;
    if (!loadRawToken(tokenJson, signatureBase64)) {
        state.status = Licensing::Status::notActivated;
        return state;
    }

    Licensing::LicenseToken token;
    juce::String error;
    if (!verifyAndDecode(tokenJson, signatureBase64, token, error)) {
        state.status = Licensing::Status::invalid;
        state.lastError = error;
        return state;
    }

    return evaluateToken(token);
}

Licensing::LicenseState LicenseManager::activate(const juce::String& licenseKey) {
    auto* body = new juce::DynamicObject();
    body->setProperty("license_key", licenseKey);
    body->setProperty("device_id", getDeviceId());
    body->setProperty("device_name", juce::SystemStats::getComputerName());

    juce::var response;
    juce::String error;
    Licensing::LicenseState state;

    if (!postJson("/v1/activate", juce::var(body), response, error)) {
        state.status = Licensing::Status::invalid;
        state.lastError = error;
        return state;
    }

    auto* obj = response.getDynamicObject();
    auto tokenJson = obj->getProperty("token_json").toString();
    auto signatureBase64 = obj->getProperty("signature").toString();

    Licensing::LicenseToken token;
    if (!verifyAndDecode(tokenJson, signatureBase64, token, error)) {
        state.status = Licensing::Status::invalid;
        state.lastError = "Server response failed signature verification: " + error;
        return state;
    }

    persistToken(tokenJson, signatureBase64);
    return evaluateToken(token);
}

Licensing::LicenseState LicenseManager::revalidate() {
    juce::String existingTokenJson, existingSignature;
    if (!loadRawToken(existingTokenJson, existingSignature)) {
        Licensing::LicenseState state;
        state.status = Licensing::Status::notActivated;
        return state;
    }

    // We need the license_key/device_id to ask the server about -- pull
    // them from the existing (already-verified-once, still-on-disk) token
    // rather than trusting the raw JSON blindly again here.
    Licensing::LicenseToken existingToken;
    juce::String error;
    if (!verifyAndDecode(existingTokenJson, existingSignature, existingToken, error)) {
        Licensing::LicenseState state;
        state.status = Licensing::Status::invalid;
        state.lastError = error;
        return state;
    }

    auto* body = new juce::DynamicObject();
    body->setProperty("license_key", existingToken.licenseKey);
    body->setProperty("device_id", existingToken.deviceId);

    juce::var response;
    if (!postJson("/v1/validate", juce::var(body), response, error)) {
        // Server unreachable or rejected us -- fall back to the locally
        // persisted token's own grace-period judgement rather than
        // immediately failing (mission section 14: don't brick the app over
        // a transient network issue).
        return evaluateToken(existingToken);
    }

    auto* obj = response.getDynamicObject();
    auto tokenJson = obj->getProperty("token_json").toString();
    auto signatureBase64 = obj->getProperty("signature").toString();

    Licensing::LicenseToken freshToken;
    Licensing::LicenseState state;
    if (!verifyAndDecode(tokenJson, signatureBase64, freshToken, error)) {
        state.status = Licensing::Status::invalid;
        state.lastError = "Server response failed signature verification: " + error;
        return state;
    }

    persistToken(tokenJson, signatureBase64);
    return evaluateToken(freshToken);
}

bool LicenseManager::deactivate() {
    juce::String tokenJson, signatureBase64;
    bool serverConfirmed = false;

    if (loadRawToken(tokenJson, signatureBase64)) {
        Licensing::LicenseToken token;
        juce::String verifyError;
        if (verifyAndDecode(tokenJson, signatureBase64, token, verifyError)) {
            auto* body = new juce::DynamicObject();
            body->setProperty("license_key", token.licenseKey);
            body->setProperty("device_id", token.deviceId);

            juce::var response;
            juce::String postError;
            serverConfirmed = postJson("/v1/deactivate", juce::var(body), response, postError);
        }
    }

    // Always clear locally, even if the server call failed -- see header
    // comment on why this asymmetry (local-only vs. server-confirmed
    // deactivation) is the right tradeoff.
    clearPersistedToken();
    return serverConfirmed;
}
