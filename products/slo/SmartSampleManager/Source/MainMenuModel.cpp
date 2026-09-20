#include "MainMenuModel.h"

juce::StringArray MainMenuModel::getMenuBarNames() {
    return { "File", "Library", "Help" };
}

juce::PopupMenu MainMenuModel::getMenuForIndex(int topLevelMenuIndex, const juce::String&) {
    juce::PopupMenu menu;

    if (topLevelMenuIndex == 0) {
        menu.addItem(scanFolder, "Scan Folder...");
        menu.addItem(preferences, "Preferences...");
        menu.addSeparator();
        menu.addItem(quit, "Quit");
    } else if (topLevelMenuIndex == 1) {
        menu.addItem(findDuplicates, "Find Duplicates");
        menu.addItem(findSimilar, "Find Similar to Selection");
        menu.addItem(importEvidence, "Import AI Evidence...");
        menu.addItem(exportDiagnostics, "Export Diagnostics Bundle...");
        menu.addItem(sortLibrary, "Sort Library");
        menu.addItem(undoSort, "Undo Last Sort...");
        menu.addItem(removeMissingFiles, "Remove Missing Files");
    } else if (topLevelMenuIndex == 2) {
        menu.addItem(about, "About SLO");
    }

    return menu;
}

void MainMenuModel::menuItemSelected(int menuItemID, int) {
    switch (menuItemID) {
        case scanFolder:      if (onScanFolder) onScanFolder(); break;
        case preferences:     if (onPreferences) onPreferences(); break;
        case quit:            juce::JUCEApplicationBase::quit(); break;
        case findDuplicates:  if (onFindDuplicates) onFindDuplicates(); break;
        case findSimilar:     if (onFindSimilar) onFindSimilar(); break;
        case importEvidence:  if (onImportEvidence) onImportEvidence(); break;
        case exportDiagnostics: if (onExportDiagnostics) onExportDiagnostics(); break;
        case sortLibrary:     if (onSortLibrary) onSortLibrary(); break;
        case undoSort:        if (onUndoSort) onUndoSort(); break;
        case removeMissingFiles: if (onRemoveMissingFiles) onRemoveMissingFiles(); break;
        case about:           if (onAbout) onAbout(); break;
        default: break;
    }
}
