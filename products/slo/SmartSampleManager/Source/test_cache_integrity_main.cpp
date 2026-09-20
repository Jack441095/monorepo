#include <iostream>
#include <fstream>
#include <string>
#include <filesystem>
#include <sqlite3.h>

#include "SampleManagerEngine.h"
#include "TestCacheDbIsolation.h"

// Cache integrity + user-state-preservation regression tests (hardening
// brief section 7/8/9). Proves:
//   1. A healthy cache is NEVER quarantined on reopen.
//   2. A genuinely corrupt cache is quarantined (a .corrupt-<ts> file is
//      created) and rebuilt into a fresh, valid cache.
//   3. Irreplaceable user state (favorites, preview history, smart
//      collections, and user tag overrides) survives a quarantine-and-rebuild.

static int failures = 0;

#define CHECK(cond, msg) \
    do { if (!(cond)) { std::cerr << "FAIL: " << msg << std::endl; failures++; } } while (0)

static int countQuarantineFiles()
{
    auto dir = SampleManagerEngine::getCacheDbFile().getParentDirectory();
    int n = 0;
    for (const auto& f : dir.findChildFiles(juce::File::TypesOfFileToFind::findFiles, false, "*.corrupt-*"))
    {
        juce::ignoreUnused(f);
        ++n;
    }
    return n;
}

int main()
{
    ScopedIsolatedCacheDb _isolatedCacheDb;  // never touch the real production cache DB
    juce::MessageManager::getInstance();

    // --- Part 1: healthy reopen never quarantines ----------------------
    {
        int quarantinesBefore = countQuarantineFiles();

        {
            SampleManagerEngine engineA;
            CHECK(engineA.checkCacheIntegrity(), "a freshly-opened cache DB should be healthy");
            engineA.setFavorite("/tmp/fake/favorite.wav", true);
            engineA.recordPreview("/tmp/fake/favorite.wav");
            engineA.createSmartCollection("My Drums", "{\"favorite\":true}");
        }

        {
            SampleManagerEngine engineB;
            CHECK(engineB.checkCacheIntegrity(), "healthy reopened cache should still be healthy");
            auto favs = engineB.getFavorites();
            CHECK(favs.size() == 1 && favs[0] == "/tmp/fake/favorite.wav",
                  "favorite should survive a healthy reopen");
        }

        int quarantinesAfter = countQuarantineFiles();
        CHECK(quarantinesAfter == quarantinesBefore,
              "healthy reopen must NOT create a quarantine file");
    }

    // --- Part 2: corrupt DB -> quarantine + user state preserved -------
    {
        juce::File cacheFile = SampleManagerEngine::getCacheDbFile();

        // Establish user state, then close (destructor checkpoints WAL).
        {
            SampleManagerEngine engineA;
            engineA.setFavorite("/tmp/keep/favorite.wav", true);
            engineA.recordPreview("/tmp/keep/previewed.wav");
            engineA.createSmartCollection("Keep Me", "{\"favorite\":true}");
        }

        // Inject a user tag override into the durable table, and give
        // sample_cache a real row so it has a root page to corrupt below.
        {
            sqlite3* db = nullptr;
            if (sqlite3_open(cacheFile.getFullPathName().toRawUTF8(), &db) == SQLITE_OK)
            {
                sqlite3_exec(db,
                    "INSERT OR REPLACE INTO user_tag_overrides "
                    "(path, category, subcategory, secondary_tags, tag_confidence, tag_source) "
                    "VALUES ('/tmp/keep/override.wav', 'Drums', 'Kick', 'One-Shot', 1.0, 'user');",
                    nullptr, nullptr, nullptr);
                sqlite3_exec(db,
                    "INSERT OR REPLACE INTO sample_cache (path, mtime, size) "
                    "VALUES ('/tmp/keep/sample.wav', 1, 1);",
                    nullptr, nullptr, nullptr);
                sqlite3_close(db);
            }
            else
            {
                CHECK(false, "could not open cache DB to inject rows");
            }
        }

        // Deterministically corrupt ONLY sample_cache's root page so PRAGMA
        // quick_check fails while the user-state tables remain readable -- the
        // realistic "derived cache corrupt, user data intact" case the salvage
        // path is built for.
        {
            sqlite3* db = nullptr;
            int rootPage = -1;
            if (sqlite3_open(cacheFile.getFullPathName().toRawUTF8(), &db) == SQLITE_OK)
            {
                sqlite3_stmt* stmt = nullptr;
                if (sqlite3_prepare_v2(db,
                        "SELECT rootpage FROM sqlite_master WHERE type='table' AND name='sample_cache';",
                        -1, &stmt, nullptr) == SQLITE_OK)
                {
                    if (sqlite3_step(stmt) == SQLITE_ROW)
                        rootPage = sqlite3_column_int(stmt, 0);
                    sqlite3_finalize(stmt);
                }
                sqlite3_close(db);
            }
            CHECK(rootPage > 1, "could not determine sample_cache root page for corruption");

            const int pageSize = 4096;
            juce::int64 offset = static_cast<juce::int64>(rootPage - 1) * pageSize;
            std::fstream f(cacheFile.getFullPathName().toStdString(),
                           std::ios::binary | std::ios::in | std::ios::out);
            if (f.is_open())
            {
                std::string garbage(static_cast<size_t>(pageSize), '\xFF');
                f.seekp(static_cast<std::streamoff>(offset));
                f.write(garbage.data(), pageSize);
                f.close();
            }
            else
            {
                CHECK(false, "could not open cache DB to corrupt sample_cache root page");
            }
        }

        // Reopen -> quarantine + salvage + restore.
        {
            SampleManagerEngine engineB;
            CHECK(engineB.checkCacheIntegrity(), "cache should be fresh/valid after quarantine-and-rebuild");

            auto favs = engineB.getFavorites();
            bool favFound = false;
            for (const auto& f : favs)
                if (f == "/tmp/keep/favorite.wav") favFound = true;
            CHECK(favFound, "favorite must survive quarantine");

            auto history = engineB.getRecentPreviews(100);
            bool histFound = false;
            for (const auto& h : history)
                if (h.filePath == "/tmp/keep/previewed.wav") histFound = true;
            CHECK(histFound, "preview history must survive quarantine");

            auto cols = engineB.getSmartCollectionNames();
            bool colFound = false;
            for (const auto& c : cols)
                if (c == "Keep Me") colFound = true;
            CHECK(colFound, "smart collection must survive quarantine");
        }

        // Verify the user tag override survived into the rebuilt DB.
        {
            sqlite3* db = nullptr;
            bool overrideFound = false;
            if (sqlite3_open(cacheFile.getFullPathName().toRawUTF8(), &db) == SQLITE_OK)
            {
                sqlite3_stmt* stmt = nullptr;
                if (sqlite3_prepare_v2(db,
                        "SELECT category FROM user_tag_overrides WHERE path='/tmp/keep/override.wav';",
                        -1, &stmt, nullptr) == SQLITE_OK)
                {
                    if (sqlite3_step(stmt) == SQLITE_ROW)
                    {
                        const unsigned char* c = sqlite3_column_text(stmt, 0);
                        overrideFound = (c && std::string(reinterpret_cast<const char*>(c)) == "Drums");
                    }
                    sqlite3_finalize(stmt);
                }
                sqlite3_close(db);
            }
            CHECK(overrideFound, "user tag override must survive quarantine");
        }

        CHECK(countQuarantineFiles() > 0, "expected a .corrupt-* quarantine file to exist after a genuine corruption");
    }

    // --- Part 3: legacy-location cache migration (P1-A) ----------------
    // Builds that predate the move to userApplicationDataDirectory stored the
    // cache at ~/Library/SmartSampleManager. Verify a populated legacy cache is
    // COPY-adopted (not moved) into the current location so its user state
    // (favorites/history) isn't silently stranded at the old path.
    {
        juce::File base = juce::File::getSpecialLocation(juce::File::tempDirectory);
        juce::File legacyDir  = base.getChildFile("SSMLegacy_"  + juce::Uuid().toString());
        juce::File currentDir = base.getChildFile("SSMCurrent_" + juce::Uuid().toString());
        legacyDir.createDirectory();
        currentDir.createDirectory();

        // 1) Plant user state in the LEGACY location.
        SampleManagerEngine::setCacheDbDirectoryOverrideForTesting(legacyDir);
        {
            SampleManagerEngine legacyEngine;
            legacyEngine.setFavorite("/tmp/migrate/keep.wav", true);
            legacyEngine.recordPreview("/tmp/migrate/preview.wav");
        }

        // 2) Point CURRENT at an empty dir + LEGACY at legacyDir, then reopen:
        //    the engine must copy the legacy cache over before opening it.
        SampleManagerEngine::setCacheDbDirectoryOverrideForTesting(currentDir);
        SampleManagerEngine::setLegacyCacheDbDirectoryOverrideForTesting(legacyDir);
        {
            SampleManagerEngine engine;
            bool favFound = false;
            for (const auto& f : engine.getFavorites())
                if (f == "/tmp/migrate/keep.wav") favFound = true;
            CHECK(favFound, "legacy-location favorite must be migrated to the current cache");

            bool previewFound = false;
            for (const auto& h : engine.getRecentPreviews(100))
                if (h.filePath == "/tmp/migrate/preview.wav") previewFound = true;
            CHECK(previewFound, "legacy-location preview history must be migrated");

            // The migration must be a COPY: the legacy file stays behind.
            CHECK(legacyDir.getChildFile("sample_cache.sqlite3").existsAsFile(),
                  "legacy cache must remain after a copy (not move) migration");
        }

        // 3) Idempotence: reopening (marker present) must not fail and must
        //    still expose the migrated data.
        {
            SampleManagerEngine engine2;
            CHECK(engine2.checkCacheIntegrity(), "migrated cache should be healthy on reopen");
        }

        // Restore process-wide isolation before the outer ScopedIsolatedCacheDb
        // destructor runs (which resets the override and deletes its own dir).
        SampleManagerEngine::setLegacyCacheDbDirectoryOverrideForTesting(juce::File());
        SampleManagerEngine::setCacheDbDirectoryOverrideForTesting(_isolatedCacheDb.dir);

        legacyDir.deleteRecursively();
        currentDir.deleteRecursively();
    }

    // --- Part 4: header-only corruption (64-byte 0xFF prefix, P1-F) -------
    // This is the exact historical corruption signature (see the P1-F forensics
    // in the hardening report): the first 64 bytes of the SQLite header were
    // wiped to 0xFF, leaving the rest of the DB intact. Reproduced here via the
    // same idiom as test_resilience_main.cpp (std::string garbage(64, '\xFF')).
    // The classifier must treat it as fatal (NOTADB), quarantine without
    // crashing, and rebuild a fresh cache. BUT -- and this is the documented gap
    // -- ordinary SQLite salvage cannot read a header-less DB, so user state in
    // a header-corrupt cache is NOT recovered by the current salvage path (the
    // data IS recoverable via a 64-byte header patch, proven separately in the
    // report but not implemented in production).
    {
        juce::File currentDir = juce::File::getSpecialLocation(juce::File::tempDirectory)
            .getChildFile("SSMHeader_" + juce::Uuid().toString());
        currentDir.createDirectory();
        SampleManagerEngine::setCacheDbDirectoryOverrideForTesting(currentDir);

        {
            SampleManagerEngine engineA;
            engineA.setFavorite("/tmp/hdr/keep.wav", true);
        }

        {
            juce::File cacheFile = SampleManagerEngine::getCacheDbFile();
            std::ofstream out(cacheFile.getFullPathName().toStdString(),
                              std::ios::binary | std::ios::in | std::ios::out);
            if (out.is_open())
            {
                std::string garbage(64, '\xFF');
                out.write(garbage.data(), static_cast<std::streamsize>(garbage.size()));
                out.close();
            }
            else
            {
                CHECK(false, "could not open cache DB to corrupt its header");
            }
        }

        {
            SampleManagerEngine engineB;
            CHECK(engineB.checkCacheIntegrity(), "cache should be fresh/valid after header-corrupt quarantine");

            // Documented limitation: a header-corrupt DB can't be read via
            // ordinary SQL, so the salvage path cannot recover its user state.
            auto favs = engineB.getFavorites();
            bool favFound = false;
            for (const auto& f : favs)
                if (f == "/tmp/hdr/keep.wav") favFound = true;
            CHECK(!favFound,
                  "header-corrupt user state is NOT salvaged via ordinary SQL (documented limitation)");
        }

        bool quarantineFound = false;
        for (const auto& f : currentDir.findChildFiles(juce::File::TypesOfFileToFind::findFiles, false, "*.corrupt-*"))
            if (f.getFileName().contains("sample_cache")) quarantineFound = true;
        CHECK(quarantineFound, "header-corrupt cache must be quarantined (renamed to .corrupt-*)");

        SampleManagerEngine::setCacheDbDirectoryOverrideForTesting(_isolatedCacheDb.dir);
        currentDir.deleteRecursively();
    }

    if (failures == 0)
    {
        std::cout << "ALL CACHE INTEGRITY TESTS PASSED SUCCESSFULLY!" << std::endl;
        return 0;
    }
    std::cerr << failures << " cache integrity test(s) FAILED" << std::endl;
    return 1;
}

