#include <iostream>
#include <cstdlib>
#include "Licensing/LicenseManager.h"

// Exercises LicenseManager end to end against a running instance of
// licensing_server/ (start it first: ./.venv/bin/uvicorn server:app --port 8420).
// Requires a license key to be passed as argv[1] -- create one via:
//   curl -X POST localhost:8420/v1/admin/licenses -H "Content-Type: application/json" \
//        -d '{"customer_email":"test@example.com","max_activations":2}'

namespace {
const char* statusName(Licensing::Status s) {
    switch (s) {
        case Licensing::Status::notActivated:     return "notActivated";
        case Licensing::Status::active:            return "active";
        case Licensing::Status::needsRevalidation: return "needsRevalidation";
        case Licensing::Status::invalid:           return "invalid";
    }
    return "?";
}
} // namespace

static int runURLPolicyTests() {
    constexpr const char* variable = "SMART_SAMPLE_MANAGER_LICENSE_SERVER_URL";
    const auto previous = std::getenv(variable);
    const std::string previousValue = previous != nullptr ? previous : "";
    const bool hadPrevious = previous != nullptr;
    int failures = 0;

    auto expect = [&](const char* value, const char* expected, const char* label) {
        if (value != nullptr)
            setenv(variable, value, 1);
        else
            unsetenv(variable);

        const auto actual = LicenseManager::serverBaseURL().toStdString();
        if (actual != expected) {
            std::cerr << "FAIL: " << label << " -> expected '" << expected
                      << "', got '" << actual << "'\n";
            ++failures;
        }
    };

    expect(nullptr, "http://localhost:8420", "default local server");
    expect("http://localhost:8420", "http://localhost:8420", "local HTTP");
    expect("http://127.0.0.1:8420", "http://127.0.0.1:8420", "IPv4 loopback HTTP");
    expect("http://[::1]:8420", "http://[::1]:8420", "IPv6 loopback HTTP");
    expect("https://licenses.example.test", "https://licenses.example.test", "remote HTTPS");
    expect("http://licenses.example.test", "", "remote HTTP rejection");
    expect("http://localhost.example.test", "", "lookalike-host rejection");
    expect("ftp://licenses.example.test", "", "non-HTTP rejection");

    if (hadPrevious)
        setenv(variable, previousValue.c_str(), 1);
    else
        unsetenv(variable);

    if (failures == 0)
        std::cout << "ALL LICENSING URL POLICY TESTS PASSED SUCCESSFULLY!\n";
    return failures == 0 ? 0 : 1;
}

int main(int argc, char* argv[]) {
    if (argc >= 2 && std::string(argv[1]) == "--url-policy")
        return runURLPolicyTests();

    if (argc < 2) {
        std::cerr << "Usage: TestLicensing <license_key>\n"
                     "       TestLicensing --url-policy\n"
                     "Create one with: curl -X POST localhost:8420/v1/admin/licenses "
                     "-H \"Content-Type: application/json\" "
                     "-d '{\"customer_email\":\"test@example.com\",\"max_activations\":2}'"
                  << std::endl;
        return 1;
    }
    juce::String licenseKey(argv[1]);

    juce::MessageManager::getInstance();
    LicenseManager mgr;

    std::cout << "Device ID: " << mgr.getDeviceId() << std::endl;

    std::cout << "\n--- loadPersisted() before any activation ---" << std::endl;
    auto before = mgr.loadPersisted();
    std::cout << "Status: " << statusName(before.status) << std::endl;
    if (before.status != Licensing::Status::notActivated) {
        std::cerr << "FAIL: expected notActivated on a clean device (delete "
                     "~/Library/Application Support/SmartSampleManager/license.json "
                     "and retry if a previous run left state behind)."
                  << std::endl;
        return 1;
    }

    std::cout << "\n--- activate() ---" << std::endl;
    auto activated = mgr.activate(licenseKey);
    std::cout << "Status: " << statusName(activated.status) << std::endl;
    if (activated.status != Licensing::Status::active) {
        std::cerr << "FAIL: activation failed: " << activated.lastError << std::endl;
        return 1;
    }
    std::cout << "  Tier: " << activated.token.tier << std::endl;
    std::cout << "  Customer: " << activated.token.customerEmail << std::endl;
    std::cout << "  Perpetual: " << (activated.token.isPerpetual() ? "yes" : "no") << std::endl;
    std::cout << "SUCCESS: activation verified via Ed25519 signature check." << std::endl;

    std::cout << "\n--- loadPersisted() after activation (pure local check) ---" << std::endl;
    auto persisted = mgr.loadPersisted();
    std::cout << "Status: " << statusName(persisted.status) << std::endl;
    if (persisted.status != Licensing::Status::active) {
        std::cerr << "FAIL: persisted license didn't reload as active." << std::endl;
        return 1;
    }
    std::cout << "SUCCESS: persisted license reloads and re-verifies from disk." << std::endl;

    std::cout << "\n--- revalidate() against server ---" << std::endl;
    auto revalidated = mgr.revalidate();
    std::cout << "Status: " << statusName(revalidated.status) << std::endl;
    if (revalidated.status != Licensing::Status::active) {
        std::cerr << "FAIL: revalidate() did not return active." << std::endl;
        return 1;
    }
    std::cout << "SUCCESS: revalidate() round-tripped a fresh signed token." << std::endl;

    std::cout << "\n--- tamper test: corrupt the persisted signature, confirm it's rejected ---" << std::endl;
    auto licenseFile = juce::File::getSpecialLocation(juce::File::userApplicationDataDirectory)
                            .getChildFile("SmartSampleManager")
                            .getChildFile("license.json");
    auto original = licenseFile.loadFileAsString();
    // Mutate via parse, not string search-and-replace -- JUCE's JSON writer
    // formats with a space after ':' ("signature": "...") which a naive
    // string match against Python-style "signature":"..." would silently
    // miss, making this test pass without actually tampering anything.
    auto parsedLicense = juce::JSON::parse(original);
    auto* licenseObj = parsedLicense.getDynamicObject();
    auto signature = licenseObj->getProperty("signature").toString();
    licenseObj->setProperty("signature", "XXXXXXXX" + signature.substring(8));
    auto tampered = juce::JSON::toString(parsedLicense);
    licenseFile.replaceWithText(tampered);

    auto afterTamper = mgr.loadPersisted();
    std::cout << "Status: " << statusName(afterTamper.status) << std::endl;
    if (afterTamper.status != Licensing::Status::invalid) {
        std::cerr << "FAIL: a tampered signature was NOT rejected -- this would be a critical "
                     "licensing bypass."
                  << std::endl;
        return 1;
    }
    std::cout << "SUCCESS: tampered license correctly rejected (" << afterTamper.lastError << ")." << std::endl;

    // Restore the real token before deactivating, so deactivate() can read
    // a valid license_key/device_id back out of it.
    licenseFile.replaceWithText(original);

    std::cout << "\n--- deactivate() ---" << std::endl;
    bool serverConfirmed = mgr.deactivate();
    std::cout << "Server confirmed: " << (serverConfirmed ? "yes" : "no") << std::endl;
    auto afterDeactivate = mgr.loadPersisted();
    std::cout << "Status after deactivate: " << statusName(afterDeactivate.status) << std::endl;
    if (afterDeactivate.status != Licensing::Status::notActivated) {
        std::cerr << "FAIL: local license file was not cleared by deactivate()." << std::endl;
        return 1;
    }
    std::cout << "SUCCESS: deactivate() cleared local state." << std::endl;

    std::cout << "\nALL LICENSING TESTS PASSED SUCCESSFULLY!" << std::endl;
    juce::MessageManager::deleteInstance();
    return 0;
}
