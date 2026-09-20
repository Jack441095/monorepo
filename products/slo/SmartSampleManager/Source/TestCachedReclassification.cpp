#include <JuceHeader.h>
#include "AcousticClassifier.h"
#include <sqlite3.h>
#include <iostream>
#include <vector>
#include <chrono>
#include <random>

int main()
{
    juce::initialiseJuce_GUI();

    juce::File tempDbFile = juce::File::getSpecialLocation(juce::File::tempDirectory).getChildFile("test_reclass_cache.sqlite3");
    tempDbFile.deleteFile();

    std::cout << "Creating isolated temporary test database at: " << tempDbFile.getFullPathName() << std::endl;

    sqlite3* db = nullptr;
    if (sqlite3_open(tempDbFile.getFullPathName().toUTF8(), &db) != SQLITE_OK)
    {
        std::cerr << "FAIL: Could not open temporary database" << std::endl;
        return 1;
    }

    // 1. Create legacy table structure
    const char* createLegacySql = 
        "CREATE TABLE sample_cache ("
        "  path TEXT PRIMARY KEY,"
        "  mtime INTEGER NOT NULL,"
        "  size INTEGER NOT NULL,"
        "  bpm REAL,"
        "  key TEXT,"
        "  instrument_type TEXT,"
        "  embedding BLOB,"
        "  category TEXT,"
        "  subcategory TEXT,"
        "  tag_confidence REAL,"
        "  tag_source TEXT,"
        "  tag_user_overridden INTEGER,"
        "  taxonomy_version INTEGER"
        ");";

    char* errMsg = nullptr;
    if (sqlite3_exec(db, createLegacySql, nullptr, nullptr, &errMsg) != SQLITE_OK)
    {
        std::cerr << "FAIL: Could not create legacy table: " << (errMsg ? errMsg : "unknown") << std::endl;
        sqlite3_free(errMsg);
        sqlite3_close(db);
        return 1;
    }

    // 2. Populate 1,000 mock rows (with mock 512D embeddings)
    std::cout << "Inserting 1,000 mock cached files..." << std::endl;
    sqlite3_exec(db, "BEGIN TRANSACTION;", nullptr, nullptr, nullptr);

    const char* insertSql = "INSERT INTO sample_cache (path, mtime, size, embedding, subcategory) VALUES (?, 123456, 1024, ?, 'Kick');";
    sqlite3_stmt* insertStmt = nullptr;
    sqlite3_prepare_v2(db, insertSql, -1, &insertStmt, nullptr);

    std::mt19937 rng(42);
    std::uniform_real_distribution<float> dist(-1.0f, 1.0f);

    std::vector<float> mockEmbed(AcousticWeights::embeddingDim);

    for (int i = 0; i < 1000; ++i)
    {
        for (int d = 0; d < AcousticWeights::embeddingDim; ++d)
        {
            mockEmbed[d] = dist(rng);
        }

        juce::String path = "file:///Volumes/MockSamples/sample_" + juce::String(i) + ".wav";
        sqlite3_bind_text(insertStmt, 1, path.toRawUTF8(), -1, SQLITE_TRANSIENT);
        sqlite3_bind_blob(insertStmt, 2, mockEmbed.data(), static_cast<int>(AcousticWeights::embeddingDim * sizeof(float)), SQLITE_TRANSIENT);
        sqlite3_step(insertStmt);
        sqlite3_reset(insertStmt);
    }
    sqlite3_finalize(insertStmt);
    sqlite3_exec(db, "COMMIT;", nullptr, nullptr, nullptr);

    // 3. Perform schema migration (additive ALTER TABLEs)
    std::cout << "Running additive DB migrations..." << std::endl;
    sqlite3_exec(db, "ALTER TABLE sample_cache ADD COLUMN classification_model_version INTEGER;", nullptr, nullptr, nullptr);
    sqlite3_exec(db, "ALTER TABLE sample_cache ADD COLUMN ood_score REAL;", nullptr, nullptr, nullptr);
    sqlite3_exec(db, "ALTER TABLE sample_cache ADD COLUMN abstention_state INTEGER;", nullptr, nullptr, nullptr);

    // 4. Run reclassification benchmark
    std::cout << "Running reclassification benchmark..." << std::endl;
    auto start = std::chrono::high_resolution_clock::now();

    // Read cached embeddings
    sqlite3_stmt* selectStmt = nullptr;
    sqlite3_prepare_v2(db, "SELECT path, embedding, tag_user_overridden FROM sample_cache WHERE embedding IS NOT NULL;", -1, &selectStmt, nullptr);

    sqlite3_stmt* updateStmt = nullptr;
    sqlite3_prepare_v2(db, "UPDATE sample_cache SET subcategory = ?, tag_confidence = ?, classification_model_version = ?, ood_score = ?, abstention_state = ? WHERE path = ?;", -1, &updateStmt, nullptr);

    sqlite3_exec(db, "BEGIN TRANSACTION;", nullptr, nullptr, nullptr);

    int processedCount = 0;
    while (sqlite3_step(selectStmt) == SQLITE_ROW)
    {
        const unsigned char* path = sqlite3_column_text(selectStmt, 0);
        const void* blob = sqlite3_column_blob(selectStmt, 1);
        int bytes = sqlite3_column_bytes(selectStmt, 1);
        int userOverridden = sqlite3_column_int(selectStmt, 2);

        if (bytes == AcousticWeights::embeddingDim * sizeof(float) && blob != nullptr)
        {
            const float* embed = static_cast<const float*>(blob);
            
            // Protect user overrides: do not reclassify if user has overridden the tag!
            if (userOverridden == 1)
            {
                continue;
            }

            auto classification = AcousticClassifier::classify520(embed);

            // Update row
            sqlite3_bind_text(updateStmt, 1, classification.subcategory.c_str(), -1, SQLITE_TRANSIENT);
            sqlite3_bind_double(updateStmt, 2, classification.confidence);
            sqlite3_bind_int(updateStmt, 3, AcousticWeights::modelVersion);
            sqlite3_bind_double(updateStmt, 4, classification.margin);
            sqlite3_bind_int(updateStmt, 5, classification.isOod ? 1 : 0);
            sqlite3_bind_text(updateStmt, 6, reinterpret_cast<const char*>(path), -1, SQLITE_TRANSIENT);

            sqlite3_step(updateStmt);
            sqlite3_reset(updateStmt);
            processedCount++;
        }
    }

    sqlite3_finalize(selectStmt);
    sqlite3_finalize(updateStmt);
    sqlite3_exec(db, "COMMIT;", nullptr, nullptr, nullptr);

    auto end = std::chrono::high_resolution_clock::now();
    std::chrono::duration<double, std::milli> duration = end - start;

    double elapsedSecs = duration.count() / 1000.0;
    double filesPerSec = processedCount / elapsedSecs;
    double timeFor10k = (10000.0 / filesPerSec);

    std::cout << "Reclassified " << processedCount << " files in " << duration.count() << " ms." << std::endl;
    std::cout << "Throughput: " << filesPerSec << " files/sec" << std::endl;
    std::cout << "Estimated time for 10,000 files: " << timeFor10k << " seconds" << std::endl;

    sqlite3_close(db);
    tempDbFile.deleteFile();

    std::cout << "SUCCESS: Cache reclassification benchmark completed successfully!" << std::endl;
    juce::MessageManager::deleteInstance();
    return 0;
}
