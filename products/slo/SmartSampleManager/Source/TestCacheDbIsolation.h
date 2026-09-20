#pragma once

#include <JuceHeader.h>
#include "SampleManagerEngine.h"

// Every Test*/Benchmark*/dev-tool binary in this project must never read,
// write, or clear the REAL user's production sample cache DB (see
// docs/SMART_SAMPLE_MANAGER_CACHE_ARCHITECTURE.md). SampleManagerEngine's
// constructor opens the cache DB immediately (in its member initializer),
// so isolation has to be established BEFORE the first SampleManagerEngine
// is constructed in the process -- there's no way to redirect it after the
// fact.
//
// Construct exactly one of these at the very top of main(), before any
// SampleManagerEngine (or engine array/pair) is constructed. It points
// SampleManagerEngine::getCacheDbFile() at a fresh, uniquely-named temp
// directory (juce::Uuid() per process, so two test binaries running at the
// same time -- or a test run alongside the real Standalone app -- never
// collide) for the lifetime of the process, and deletes that directory on
// destruction.
struct ScopedIsolatedCacheDb
{
    juce::File dir;

    ScopedIsolatedCacheDb()
    {
        dir = juce::File::getSpecialLocation(juce::File::tempDirectory)
                  .getChildFile("SmartSampleManagerTestCache_" + juce::Uuid().toString());
        dir.createDirectory();
        SampleManagerEngine::setCacheDbDirectoryOverrideForTesting(dir);
    }

    ~ScopedIsolatedCacheDb()
    {
        SampleManagerEngine::setCacheDbDirectoryOverrideForTesting(juce::File());
        dir.deleteRecursively();
    }

    // Not copyable/movable -- one isolation scope per process, tied to the
    // process-global override.
    ScopedIsolatedCacheDb(const ScopedIsolatedCacheDb&) = delete;
    ScopedIsolatedCacheDb& operator=(const ScopedIsolatedCacheDb&) = delete;
};
