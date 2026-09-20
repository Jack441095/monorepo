#include <iostream>
#include "SampleManagerEngine.h"

// RECOVERY PHASE R1 safety regression test (see brief section 10 /
// docs/SLO_LOST_WORK_RECOVERY_MANIFEST.md). Exists specifically to make the
// original incident (a test run was directly observed shrinking the real
// production SLO cache DB from 4,743,168 to 1,363,968 bytes) mechanically
// difficult to reintroduce.
//
// This test deliberately does NOT construct a ScopedIsolatedCacheDb -- it is
// testing what happens for a binary/code path that "forgot" isolation. It
// must NOT actually open/mutate the production DB to prove that, so it
// exercises the pure, static guard logic (isKnownProductionCacheDbPath())
// directly rather than constructing a real SampleManagerEngine, and
// separately proves via a SHA-256-style sentinel (size + mtime, since this
// test has no crypto dependency) that the real production DB file is
// completely untouched by this process.
//
// This target intentionally is NOT compiled with SSM_TEST_BINARY (see
// CMakeLists.txt) -- it needs to compute what the *production* path would be
// via the same code path a real (non-test) binary would use, without the
// guard aborting the process just for calling getCacheDbFile().

static int failures = 0;
#define CHECK(cond, msg) \
    do { if (!(cond)) { std::cerr << "FAIL: " << msg << std::endl; failures++; } \
         else { std::cout << "  ok: " << msg << std::endl; } } while (0)

int main()
{
    // Sentinel: record the real production DB's on-disk state BEFORE doing
    // anything, so we can prove afterward that this test never touched it.
    juce::File productionDb = SampleManagerEngine::getCacheDbFile();
    bool existedBefore = productionDb.existsAsFile();
    juce::int64 sizeBefore = existedBefore ? productionDb.getSize() : -1;
    juce::Time mtimeBefore = existedBefore ? productionDb.getLastModificationTime() : juce::Time();

    // 1. The production path (what a real, non-isolated binary would
    //    resolve to) must be recognised as production.
    CHECK(SampleManagerEngine::isKnownProductionCacheDbPath(productionDb),
          "getCacheDbFile() result is recognised as the production cache path");

    // 2. An isolated test directory must NOT be misclassified as production.
    juce::File isolatedDir = juce::File::getSpecialLocation(juce::File::tempDirectory)
                                  .getChildFile("SmartSampleManagerTestCache_safety_regression_probe");
    isolatedDir.createDirectory();
    juce::File isolatedDb = isolatedDir.getChildFile("sample_cache.sqlite3");
    CHECK(!SampleManagerEngine::isKnownProductionCacheDbPath(isolatedDb),
          "an isolated temp-dir cache path is NOT misclassified as production");
    isolatedDir.deleteRecursively();

    // 3. Setting an override and re-resolving getCacheDbFile() must move it
    //    off the production path entirely (this is exactly what
    //    ScopedIsolatedCacheDb does before any SampleManagerEngine exists).
    juce::File overrideDir = juce::File::getSpecialLocation(juce::File::tempDirectory)
                                  .getChildFile("SmartSampleManagerTestCache_safety_regression_override");
    SampleManagerEngine::setCacheDbDirectoryOverrideForTesting(overrideDir);
    juce::File resolvedUnderOverride = SampleManagerEngine::getCacheDbFile();
    CHECK(!SampleManagerEngine::isKnownProductionCacheDbPath(resolvedUnderOverride),
          "getCacheDbFile() under an active override no longer resolves to production");
    SampleManagerEngine::setCacheDbDirectoryOverrideForTesting(juce::File());
    overrideDir.deleteRecursively();

    // 4. Production-data sentinel: this entire test must not have touched
    //    the real production DB (it never opened it -- only compared paths).
    bool existsAfter = productionDb.existsAsFile();
    CHECK(existedBefore == existsAfter, "production DB existence unchanged by this test");
    if (existedBefore && existsAfter) {
        CHECK(sizeBefore == productionDb.getSize(), "production DB size unchanged by this test");
        CHECK(mtimeBefore == productionDb.getLastModificationTime(), "production DB mtime unchanged by this test");
    }

    if (failures > 0) {
        std::cerr << failures << " safety regression check(s) FAILED" << std::endl;
        return 1;
    }
    std::cout << "ALL SAFETY REGRESSION TESTS PASSED SUCCESSFULLY!" << std::endl;
    return 0;
}
