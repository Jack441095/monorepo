#pragma once

#include <JuceHeader.h>
#include "SampleManagerEngine.h"

// In-app interactive Sort & Rename preview panel.
// Displays exact planned file destinations, original vs proposed names,
// category hierarchy, and safety policy status (Eligible vs Excluded)
// before committing any filesystem changes.
class SortPreviewPanel : public juce::Component,
                         public juce::TableListBoxModel
{
public:
    SortPreviewPanel(SampleManagerEngine& engine);
    ~SortPreviewPanel() override = default;

    void setPreview(const SampleManagerEngine::SortPreviewResult& result, int namingStyle);

    void setConfirmCallback(std::function<void(bool copyInsteadOfMove)> callback);
    void setCancelCallback(std::function<void()> callback);
    void setUndoPreviousCallback(std::function<void()> callback);

    // juce::TableListBoxModel implementation
    int getNumRows() override;
    void paintRowBackground(juce::Graphics& g, int rowNumber, int width, int height, bool rowIsSelected) override;
    void paintCell(juce::Graphics& g, int rowNumber, int columnId, int width, int height, bool rowIsSelected) override;

    void paint(juce::Graphics& g) override;
    void resized() override;
    bool keyPressed(const juce::KeyPress& key) override;

    enum ColumnId
    {
        colStatus = 1,
        colOriginalName,
        colArrow,
        colProposedName,
        colFolder,
        colKeyBpm,
        colPolicyReason
    };

    enum FilterMode
    {
        filterAll = 0,
        filterEligibleOnly,
        filterExcludedOnly
    };

private:
    void applyFilter();

    SampleManagerEngine& engine;
    SampleManagerEngine::SortPreviewResult currentResult;
    std::vector<SampleManagerEngine::SortPreviewItem> filteredItems;

    int namingStyle = 1;
    FilterMode currentFilter = filterAll;
    juce::String searchQuery;

    juce::Label titleLabel;
    juce::Label summaryLabel;

    juce::TextEditor searchField;
    juce::TextButton filterAllButton;
    juce::TextButton filterEligibleButton;
    juce::TextButton filterExcludedButton;

    juce::TableListBox table;

    juce::TextButton copyButton;
    juce::TextButton moveButton;
    juce::TextButton cancelButton;
    juce::TextButton undoPreviousButton;
    juce::TextButton closeButton;

    std::function<void(bool)> onConfirm;
    std::function<void()> onCancel;
    std::function<void()> onUndoPrevious;

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR(SortPreviewPanel)
};

