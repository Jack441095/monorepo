#include <iostream>
#include <string>
#include <vector>

#include <JuceHeader.h>

#include "PrecisionBrowser.h"
#include "SampleManagerEngine.h"
#include "TestCacheDbIsolation.h"

// PrecisionBrowser click-to-sort regression tests.
//
// These deliberately drive the REAL production path --
// PrecisionBrowser::sortOrderChanged() -> PrecisionBrowser::applySort() -- and
// read the resulting row order back through the browser's public API. An
// earlier revision of this file re-implemented each comparator as a local
// lambda and asserted that the lambda sorted correctly, which is tautological:
// it could not fail even if applySort() were deleted outright. It also used
// jassert, which compiles to nothing in a Release build, so the whole file was
// silently inert in exactly the configuration that ships.

static int failures = 0;

#define CHECK(cond, msg) \
    do { if (!(cond)) { std::cerr << "FAIL: " << msg << std::endl; failures++; } } while (0)

// Reads the browser's current visible row order back out through public API.
static std::vector<std::string> visibleOrder(PrecisionBrowser& browser)
{
    std::vector<std::string> order;
    const int rows = browser.getNumRows();
    for (int i = 0; i < rows; ++i)
    {
        browser.selectRow(i);
        order.push_back(browser.getSelectedItem().filePath);
    }
    return order;
}

static SampleItem makeSample(const std::string& path,
                             const std::string& name,
                             const std::string& category,
                             const std::string& key,
                             float bpm,
                             float duration)
{
    SampleItem s;
    s.filePath = path;
    s.name = name;
    s.category = category;
    s.key = key;
    s.bpm = bpm;
    s.durationSeconds = duration;
    return s;
}

int main()
{
    ScopedIsolatedCacheDb _isolatedCacheDb;  // never touch the real production cache DB
    juce::ScopedJuceInitialiser_GUI _juceInit;

    std::cout << "Starting Precision Browser Sorting tests..." << std::endl;

    SampleManagerEngine engine;
    PrecisionBrowser browser(engine);

    std::vector<SampleItem> mockSamples = {
        makeSample("/path/to/a.wav", "Kick A",  "Drums", "C Major", 120.0f, 1.5f),
        makeSample("/path/to/b.wav", "Snare B", "FX",    "A Minor",  90.0f, 0.5f),
        makeSample("/path/to/c.wav", "Synth C", "",      "G Major", 140.0f, 4.2f),
    };

    browser.updateSamples(mockSamples);
    CHECK(browser.getNumRows() == 3, "all three mock samples should be visible with no search query");

    // --- Category pills filter the browser as well as the map -------------
    browser.setFilteredCategories({ "Drums" });
    CHECK(browser.getNumRows() == 1 && browser.getSelectedItem().filePath.empty(),
          "category filtering should reduce the visible browser rows without selecting one");
    browser.selectRow(0);
    CHECK(browser.getSelectedItem().filePath == "/path/to/a.wav",
          "the Drums filter should retain only the taxonomy-matching row");
    browser.setFilteredCategories({ "FX" });
    CHECK(!browser.hasSelection(),
          "a selected row hidden by a category filter should leave no visible row selected");
    CHECK(!browser.isSampleVisible("/path/to/a.wav"),
          "a category-filtered sample should report as not visible to the inspector cue");
    browser.setFilteredCategories({}, true);
    CHECK(browser.getNumRows() == 0,
          "an explicit all-off category state should show no rows");
    browser.setFilteredCategories({ "Drums", "FX" }, false);
    CHECK(browser.getNumRows() == 3,
          "an explicit ALL state should retain uncategorized rows as well as labeled rows");
    browser.setFilteredCategories({});
    CHECK(browser.hasSelection() && browser.getSelectedItem().filePath == "/path/to/a.wav",
          "clearing a category filter should restore the previously selected sample");
    CHECK(browser.isSampleVisible("/path/to/a.wav"),
          "clearing the category filter should restore sample visibility");
    CHECK(browser.getNumRows() == 3,
          "clearing category filters should restore every browser row");

    // --- Sort by SAMPLE name, ascending ---------------------------------
    {
        browser.sortOrderChanged(PrecisionBrowser::colFilename, true);
        const auto order = visibleOrder(browser);
        CHECK(order == (std::vector<std::string>{"/path/to/a.wav", "/path/to/b.wav", "/path/to/c.wav"}),
              "name ascending should order Kick A, Snare B, Synth C");
    }

    // --- Sort by SAMPLE name, descending --------------------------------
    {
        browser.sortOrderChanged(PrecisionBrowser::colFilename, false);
        const auto order = visibleOrder(browser);
        CHECK(order == (std::vector<std::string>{"/path/to/c.wav", "/path/to/b.wav", "/path/to/a.wav"}),
              "name descending should reverse the ascending order");
    }

    // --- Sort by BPM, ascending -----------------------------------------
    {
        browser.sortOrderChanged(PrecisionBrowser::colBpm, true);
        const auto order = visibleOrder(browser);
        CHECK(order == (std::vector<std::string>{"/path/to/b.wav", "/path/to/a.wav", "/path/to/c.wav"}),
              "bpm ascending should order 90, 120, 140");
    }

    // --- Sort by LENGTH, ascending --------------------------------------
    {
        browser.sortOrderChanged(PrecisionBrowser::colDuration, true);
        const auto order = visibleOrder(browser);
        CHECK(order == (std::vector<std::string>{"/path/to/b.wav", "/path/to/a.wav", "/path/to/c.wav"}),
              "duration ascending should order 0.5s, 1.5s, 4.2s");
    }

    // --- Sort by CATEGORY: empty categories sort last --------------------
    {
        browser.sortOrderChanged(PrecisionBrowser::colCategory, true);
        const auto order = visibleOrder(browser);
        CHECK(order == (std::vector<std::string>{"/path/to/a.wav", "/path/to/b.wav", "/path/to/c.wav"}),
              "category ascending should order Drums, FX, then the empty category last");
    }

    // --- Sort by KEY uses musical ordering, not lexicographic ------------
    // Chromatic order puts C Major (0) before G Major (7) before A Minor (21).
    // A purely lexicographic sort would instead yield "A Minor", "C Major",
    // "G Major", so this asserts getKeyPriority() is actually consulted.
    {
        browser.sortOrderChanged(PrecisionBrowser::colKey, true);
        const auto order = visibleOrder(browser);
        CHECK(order == (std::vector<std::string>{"/path/to/a.wav", "/path/to/c.wav", "/path/to/b.wav"}),
              "key ascending should be chromatic (C Major, G Major, A Minor), not alphabetical");
    }

    // --- Unknown keys sort to the bottom ---------------------------------
    {
        std::vector<SampleItem> withUnknownKey = mockSamples;
        withUnknownKey.push_back(makeSample("/path/to/d.wav", "Perc D", "Drums", "not-a-key", 100.0f, 2.0f));

        PrecisionBrowser keyBrowser(engine);
        keyBrowser.updateSamples(withUnknownKey);
        keyBrowser.sortOrderChanged(PrecisionBrowser::colKey, true);

        const auto order = visibleOrder(keyBrowser);
        CHECK(order.size() == 4 && order.back() == "/path/to/d.wav",
              "a key the chromatic table does not recognise should sort to the bottom");
    }

    // --- Ties fall back to filePath for a stable order --------------------
    {
        std::vector<SampleItem> tied = {
            makeSample("/path/to/b.wav", "Second", "Drums", "C Major", 120.0f, 1.0f),
            makeSample("/path/to/a.wav", "First",  "Drums", "C Major", 120.0f, 1.0f),
        };

        PrecisionBrowser tieBrowser(engine);
        tieBrowser.updateSamples(tied);
        tieBrowser.sortOrderChanged(PrecisionBrowser::colBpm, true);

        const auto order = visibleOrder(tieBrowser);
        CHECK(order == (std::vector<std::string>{"/path/to/a.wav", "/path/to/b.wav"}),
              "equal BPMs should fall back to filePath order");
    }

    // --- Re-sorting preserves the selected SAMPLE, not the row index ------
    {
        PrecisionBrowser selBrowser(engine);
        selBrowser.updateSamples(mockSamples);

        selBrowser.sortOrderChanged(PrecisionBrowser::colBpm, true);
        // Rows are now b(90), a(120), c(140); select the 140bpm sample at row 2.
        selBrowser.selectRow(2);
        CHECK(selBrowser.getSelectedItem().filePath == "/path/to/c.wav",
              "precondition: row 2 under bpm-ascending is the 140bpm sample");

        selBrowser.sortOrderChanged(PrecisionBrowser::colBpm, false);
        // Order is now c(140), a(120), b(90) -- the same sample moved to row 0.
        CHECK(selBrowser.hasSelection(), "selection must survive a re-sort");
        CHECK(selBrowser.getSelectedItem().filePath == "/path/to/c.wav",
              "re-sort must follow the selected sample, not keep the old row index");
    }

    if (failures == 0)
        std::cout << "All Precision Browser Sorting tests passed successfully!" << std::endl;
    else
        std::cerr << failures << " Precision Browser Sorting test(s) FAILED" << std::endl;

    return failures == 0 ? 0 : 1;
}
