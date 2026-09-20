#pragma once

#include <JuceHeader.h>

// Native macOS menu bar (via MenuBarModel::setMacMainMenu) for the
// Standalone app. Dispatches to callbacks supplied by the editor rather
// than owning any app logic itself, so menu items and their equivalent
// sidebar buttons share one implementation instead of two.
class MainMenuModel : public juce::MenuBarModel {
public:
    enum MenuItemId {
        scanFolder = 1,
        preferences,
        quit,
        findDuplicates,
        findSimilar,
        importEvidence,
        exportDiagnostics,
        sortLibrary,
        undoSort,
        removeMissingFiles,
        about,
    };

    std::function<void()> onScanFolder;
    std::function<void()> onPreferences;
    std::function<void()> onFindDuplicates;
    std::function<void()> onFindSimilar;
    std::function<void()> onImportEvidence;
    std::function<void()> onExportDiagnostics;
    std::function<void()> onSortLibrary;
    std::function<void()> onUndoSort;
    std::function<void()> onRemoveMissingFiles;
    std::function<void()> onAbout;

    juce::StringArray getMenuBarNames() override;
    juce::PopupMenu getMenuForIndex(int topLevelMenuIndex, const juce::String& menuName) override;
    void menuItemSelected(int menuItemID, int topLevelMenuIndex) override;
};
