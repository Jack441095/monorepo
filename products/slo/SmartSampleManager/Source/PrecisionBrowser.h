#pragma once

#include <JuceHeader.h>
#include "SampleManagerEngine.h"

class PrecisionBrowser : public juce::Component,
                         public juce::TableListBoxModel
{
public:
    PrecisionBrowser(SampleManagerEngine& engine);
    ~PrecisionBrowser() override = default;

    void updateSamples(const std::vector<SampleItem>& newSamples);
    // Applies the editor's free-text query to the table, using the same
    // filename/key/category/instrument/BPM contract as the map canvas.
    void setSearchQuery(const juce::String& query);
    // Applies the same category-pill selection used by the map. Keeping this
    // on the browser model makes LIST, MAP, and SPLIT views agree.
    void setFilteredCategories(const std::vector<std::string>& activeCategories);
    // Explicit state used by the editor: filterActive=false means ALL (even
    // when the category list is populated); true + an empty list represents
    // the intentional all-off state.
    void setFilteredCategories(const std::vector<std::string>& activeCategories,
                               bool filterActive);
    void setSelectedCallback(std::function<void(const SampleItem&)> callback);
    void setDoubleClickedCallback(std::function<void(const SampleItem&)> callback);
    // Optional first-run action shown by the empty-state card. The editor owns
    // the actual workflow (normally the folder chooser).
    void setEmptyStateActionCallback(std::function<void()> callback);

    // Get currently selected sample
    SampleItem getSelectedItem() const;
    bool hasSelection() const;
    bool isSampleVisible(const juce::String& filePath) const;
    void selectRow(int rowNumber);
    // Move through the currently visible (filtered/sorted) rows.  Keeping
    // this in the browser prevents editor-level shortcuts from accidentally
    // indexing the engine's unfiltered sample vector.
    bool selectRelative(int rowDelta);
    void selectSampleByPath(const juce::String& filePath);

    // juce::TableListBoxModel implementation
    int getNumRows() override;
    void paintRowBackground(juce::Graphics& g, int rowNumber, int width, int height, bool rowIsSelected) override;
    void paintCell(juce::Graphics& g, int rowNumber, int columnId, int width, int height, bool rowIsSelected) override;
    void cellClicked(int rowNumber, int columnId, const juce::MouseEvent& event) override;
    void cellDoubleClicked(int rowNumber, int columnId, const juce::MouseEvent& event) override;
    void deleteKeyPressed(int lastSelectedRow) override;
    void sortOrderChanged(int newSortColumnId, bool isAscending) override;
    
    // Custom drag gesture triggers
    juce::var getDragSourceDescription(const juce::SparseSet<int>& selectedRows) override;

    void paint(juce::Graphics& g) override;
    void resized() override;
    void mouseDown(const juce::MouseEvent& event) override;
    void mouseMove(const juce::MouseEvent& event) override;
    void mouseExit(const juce::MouseEvent& event) override;

    enum ColumnId
    {
        colPlayState = 1,
        colFavorite,
        colFilename,
        colCategory,
        colKey,
        colBpm,
        colDuration,
        colAcousticPhysics
    };

private:
    SampleManagerEngine& engine;
    std::vector<SampleItem> allSamples;
    std::vector<SampleItem> samples;
    std::vector<std::string> filteredCategories;
    bool categoryFilterActive = false;
    juce::String searchQueryLower;
    juce::TableListBox table;
    juce::Label summaryLabel;
    
    std::function<void(const SampleItem&)> onSelect;
    std::function<void(const SampleItem&)> onDoubleClick;
    std::function<void()> onEmptyStateAction;
    juce::Rectangle<int> emptyActionBounds;
    bool emptyActionHovered = false;
    
    int selectedRow = -1;
    // Keep selection identity independent from the current visible projection.
    // A search/category filter may temporarily remove the row, but clearing
    // that filter should restore the same sample instead of silently dropping
    // the user's place in the library.
    std::string selectedFilePath;
    bool externalDragInProgress = false;

    // Sorting state
    int currentSortColumnId = -1;
    bool currentSortAscending = true;
    void applySort();

    void mouseDrag(const juce::MouseEvent& event) override;

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR(PrecisionBrowser)
};
