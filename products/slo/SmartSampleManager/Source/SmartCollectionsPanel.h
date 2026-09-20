#pragma once

#include <JuceHeader.h>
#include <functional>
#include <string>
#include <vector>
#include "SampleManagerEngine.h"

// In-app Smart Collections UX (V1.1) -- musician-friendly rule builder over
// SampleManagerEngine::createSmartCollection()/getSmartCollectionSamples().
//
// IMPORTANT engine-reality constraint (verified against
// SampleManagerEngine.cpp::getSmartCollectionSamples() before building this):
// the real query_rules JSON schema is a FLAT set of optional filters, ANDed
// together -- {"favorite":bool, "bpm_min":n, "bpm_max":n, "key":"...",
// "category":"...", "centroid_min":n, "centroid_max":n}. There is no nested
// rule list, no OR logic, and no support for Tag, Duration, or Date Added,
// despite those being listed as desired rule fields in the design brief.
// This panel therefore only exposes what the engine actually evaluates
// (Category, Key, BPM range, Brightness range via spectral centroid,
// Favorite) -- it does not offer Tag/Duration/Date Added controls, since a
// control that silently does nothing would be worse than not having it. See
// docs/SMART_SAMPLE_MANAGER_UX_AUDIT.md for this finding.
class SmartCollectionsPanel : public juce::Component,
                               private juce::ListBoxModel
{
public:
    SmartCollectionsPanel();
    ~SmartCollectionsPanel() override = default;

    // Non-owning -- the editor owns the real engine and outlives this panel.
    void setEngine(SampleManagerEngine* engineToUse);

    // Re-pulls collection names from the engine and shows the panel. Call
    // this (not setVisible(true) directly) whenever opening the panel so the
    // list is never stale.
    void refreshAndShow();

    void setSampleSelectedCallback(std::function<void(const SampleItem&)> callback);
    void setCloseCallback(std::function<void()> callback);

    void paint(juce::Graphics&) override;
    void resized() override;
    bool keyPressed(const juce::KeyPress& key) override;

    // juce::ListBoxModel (collection-names list only -- the evaluated-samples
    // list uses a second, private inner model so both lists can coexist)
    int getNumRows() override;
    void paintListBoxItem(int rowNumber, juce::Graphics&, int width, int height, bool rowIsSelected) override;
    void listBoxItemClicked(int row, const juce::MouseEvent&) override;

private:
    class SampleRowsModel : public juce::ListBoxModel
    {
    public:
        explicit SampleRowsModel(SmartCollectionsPanel& ownerPanel) : owner(ownerPanel) {}
        int getNumRows() override;
        void paintListBoxItem(int rowNumber, juce::Graphics&, int width, int height, bool rowIsSelected) override;
        void listBoxItemClicked(int row, const juce::MouseEvent&) override;
    private:
        SmartCollectionsPanel& owner;
    };
    SampleRowsModel sampleRowsModel { *this };

    SampleManagerEngine* engine = nullptr;
    std::function<void(const SampleItem&)> onSampleSelected;
    std::function<void()> onClose;

    // Left column: existing collections + "starter presets" that haven't
    // been created yet (shown distinctly, one click to create).
    juce::Label titleLabel;
    juce::TextButton closeButton;
    juce::ListBox collectionsListBox;
    std::vector<std::string> collectionNames;
    struct StarterPreset {
        juce::String name;
        juce::String description;
        juce::String category;      // empty = any
        juce::String key;           // empty = any
        float bpmMin = 0.0f, bpmMax = 0.0f; // 0,0 = no bound
        int brightnessBand = 0;     // 0 = any, 1 = darker, 2 = balanced, 3 = brighter
        bool favoriteOnly = false;
        juce::String physicalClass; // e.g. "Kick", "Snare", "Crash / Cymbal"
        juce::String material;      // e.g. "Wood", "Metal", "Skin / Mylar"
    };
    std::vector<StarterPreset> starterPresets;
    int numRealCollections = 0; // collectionNames.size() at last refresh -- rows beyond this are starter presets

    // Right column: rule builder (for a new/edited collection) OR evaluated
    // results (for a clicked existing collection) -- toggled via showingBuilder.
    bool showingBuilder = true;
    juce::String editingCollectionName; // empty when building a brand-new one

    juce::TextEditor nameEditor;
    juce::Label categoryLabel;
    juce::ComboBox categoryCombo;      // "Any" + the same 6 categories as the sidebar's taxonomy editor
    juce::Label keyLabel;
    juce::TextEditor keyEditor;        // blank = any
    juce::Label bpmLabel;
    juce::TextEditor bpmMinEditor, bpmMaxEditor;
    juce::Label brightnessLabel;
    juce::ComboBox brightnessCombo;    // Any / Darker / Balanced / Brighter -- translates to centroid_min/max, never shown as Hz
    juce::Label physicalClassLabel;
    juce::ComboBox physicalClassCombo; // Any physical class, Kick, Snare, Hi-Hat, Crash / Cymbal, Tom, Bass, Piano / Plucked String
    juce::Label materialLabel;
    juce::ComboBox materialCombo;      // Any material, Wood, Metal, Skin / Mylar, Glass / Ceramic
    juce::ToggleButton favoriteOnlyToggle;
    juce::TextButton saveButton;
    juce::TextButton deleteButton;
    juce::Label emptyStateLabel;

    juce::ListBox sampleResultsListBox;
    std::vector<SampleItem> currentResultItems;

    void showBuilderForNewCollection();
    void showBuilderForExistingCollection(const juce::String& name);
    void showResultsForCollection(const juce::String& name);
    void saveCurrentRuleSet();
    void deleteEditingCollection();
    juce::String buildRulesJson() const;
    void loadPresetIntoBuilder(const StarterPreset& preset);

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR(SmartCollectionsPanel)
};
