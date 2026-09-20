#include "PluginProcessor.h"
#include "PluginEditor.h"
#include "ClassificationPresentation.h"
#include "DesignTokens.h"
#include "LabelFreeEvidencePacket.h"
#include <algorithm>
#include <cmath>

namespace
{
bool isSupportedDropPath(const juce::String& path)
{
    const juce::File file(path);
    if (file.isDirectory())
        return true;

    const auto extension = file.getFileExtension().toLowerCase();
    return extension == ".wav" || extension == ".mp3"
        || extension == ".aif" || extension == ".aiff"
        || extension == ".flac" || extension == ".ogg";
}

// F-03 rescan-diff copy in one place: short line for the status label, long
// sentences for the completion dialog. Both read the same receipt so the two
// can never disagree with each other.
juce::String formatScanReceipt(const SampleManagerEngine::ScanReceipt& receipt)
{
    juce::String text = "+" + juce::String(receipt.added) + " added · ~"
        + juce::String(receipt.changed) + " re-analysed";
    if (receipt.failed > 0)
        text += " · " + juce::String(receipt.failed) + " failed";
    if (receipt.skippedNonAudio > 0)
        text += " · " + juce::String(receipt.skippedNonAudio) + " skipped (non-audio)";
    return text;
}

juce::String formatScanReceiptLong(const SampleManagerEngine::ScanReceipt& receipt)
{
    juce::String message = juce::String(receipt.added) + " new sample"
        + (receipt.added == 1 ? "" : "s") + " added, "
        + juce::String(receipt.changed) + " existing row"
        + (receipt.changed == 1 ? "" : "s") + " re-analysed.";
    if (receipt.failed > 0)
        message += " " + juce::String(receipt.failed) + " file"
            + (receipt.failed == 1 ? "" : "s")
            + " could not be analysed -- see the Review Queue (U for unknowns).";
    if (receipt.skippedNonAudio > 0)
        message += " " + juce::String(receipt.skippedNonAudio) + " non-audio item"
            + (receipt.skippedNonAudio == 1 ? " was" : "s were")
            + " skipped (unsupported format or symlink).";
    return message;
}
}

SmartSampleManagerAudioProcessorEditor::SmartSampleManagerAudioProcessorEditor(SmartSampleManagerAudioProcessor& p)
    : AudioProcessorEditor(&p), audioProcessor(p),
      browser(p.getEngine()),
      waveformPreview(p.getEngine().getFormatManager()),
      sortPreviewPanel(p.getEngine())
{
    setLookAndFeel(&lookAndFeel);

    // Window settings -- resizable with a sane minimum, restoring the
    // previous session's size if one was saved (see destructor).
    auto& savedProps = AppSettings::getInstance().getProps();
    int savedWidth = savedProps.getIntValue("editorWidth", 800);
    int savedHeight = savedProps.getIntValue("editorHeight", 580);
    setResizeLimits(700, 520, 3000, 2000);
    setResizable(true, true);
    // Keep restored sessions inside the same bounds as interactive resizing.
    // Older builds persisted smaller dimensions, so clamping to 640x500 here
    // could reopen a visibly clipped editor even though the resize handles
    // correctly enforce a 700x520 minimum.
    setSize(juce::jlimit(700, 3000, savedWidth), juce::jlimit(520, 2000, savedHeight));

    updateCategoryButtons();

    // 1. Add and configure header components
    addAndMakeVisible(titleLabel);
    titleLabel.setText("SLO", juce::dontSendNotification);
    titleLabel.setFont(juce::Font(juce::FontOptions().withHeight(Tokens::fontTitle).withStyle("Bold")));
    titleLabel.setColour(juce::Label::textColourId, Tokens::foreground);
    titleLabel.setJustificationType(juce::Justification::left);

    addAndMakeVisible(statusLabel);
    statusLabel.setText("Initializing engine...", juce::dontSendNotification);
    statusLabel.setFont(juce::Font(juce::FontOptions().withHeight(Tokens::fontLabel)));
    statusLabel.setColour(juce::Label::textColourId, Tokens::mutedDim);
    statusLabel.setJustificationType(juce::Justification::right);
    statusLabel.setMinimumHorizontalScale(0.72f);

    addAndMakeVisible(searchField);
    searchField.setTextToShowWhenEmpty("Search...", Tokens::mutedDim);
    searchField.setColour(juce::TextEditor::backgroundColourId, Tokens::surface);
    searchField.setColour(juce::TextEditor::outlineColourId, Tokens::border);
    searchField.setColour(juce::TextEditor::textColourId, Tokens::foreground);
    searchField.setColour(juce::TextEditor::focusedOutlineColourId, Tokens::focusRing);
    searchField.setTooltip("Search current library (⌘F)");
    searchField.setWantsKeyboardFocus(true);
    clearSearchButton.setButtonText("×");
    clearSearchButton.setTooltip("Clear search (Escape)");
    clearSearchButton.setColour(juce::TextButton::buttonColourId, Tokens::surface);
    clearSearchButton.setColour(juce::TextButton::buttonOnColourId, Tokens::surfaceRaised);
    clearSearchButton.setColour(juce::TextButton::textColourOffId, Tokens::mutedDim);
    clearSearchButton.setColour(juce::TextButton::textColourOnId, Tokens::foreground);
    clearSearchButton.setWantsKeyboardFocus(false);
    clearSearchButton.onClick = [this]() {
        searchField.clear();
        searchField.grabKeyboardFocus();
    };
    addAndMakeVisible(clearSearchButton);
    clearSearchButton.setVisible(false);
    // Debounced: waits for a 200ms pause in typing before actually
    // re-filtering, rather than re-filtering on every keystroke -- the
    // "Debounced searches" large-library requirement. The canvas's own
    // filtering is already viewport-bounded (cheap regardless of total
    // library size), but this avoids pointless repaint churn while typing.
    searchField.onTextChange = [this]() {
        auto query = searchField.getText();
        clearSearchButton.setVisible(query.trim().isNotEmpty());
        audioProcessor.setEditorSearchText(query);
        auto expectedGeneration = ++searchDebounceGeneration;
        // SafePointer: a bare [this] capture here would be unsafe if the
        // editor is closed within this 200ms debounce window (a real risk
        // -- DAW UIs can be dismissed at any time) -- see the same fix
        // applied to SampleManagerEngine's callAsync sites in
        // docs/ASYNC_STARTUP.md's "second bug" note. juce::Timer's
        // free-function callAfterDelay() has no automatic lifetime tie to
        // any particular object, so this check is required, not optional.
        juce::Component::SafePointer<SmartSampleManagerAudioProcessorEditor> safeThis(this);
        juce::Timer::callAfterDelay(200, [safeThis, query, expectedGeneration]() {
            if (safeThis == nullptr) return;
            if (expectedGeneration == safeThis->searchDebounceGeneration) {
                safeThis->canvas.setSearchQuery(query);
                safeThis->browser.setSearchQuery(query);
                safeThis->updateSelectionFilterCue();
            }
        });
    };

    // 2. Add central Canvas
    addAndMakeVisible(canvas);

    // 3. Add and configure sidebar components (Phase 8.6B: now hosted inside
    // a Viewport -- see PluginEditor.h comment above sidebarViewport -- so
    // the sidebar scrolls instead of clipping controls at small window
    // heights).
    addAndMakeVisible(sidebarViewport);
    sidebarViewport.setViewedComponent(&sidebarContent, false);
    sidebarViewport.setScrollBarsShown(true, false); // vertical only

    addAndMakeVisible(filterBarViewport);
    filterBarViewport.setViewedComponent(&filterBarContent, false);
    filterBarViewport.setScrollBarsShown(false, true); // horizontal only

    // Keep the explicit viewport colours as well as the shared look-and-feel:
    // these scrollbars are intentionally neutral chrome rather than an accent,
    // and the per-component override also covers host-specific scrollbar
    // look-and-feel fallbacks.
    sidebarViewport.getVerticalScrollBar().setColour(juce::ScrollBar::thumbColourId, Tokens::borderStrong);
    filterBarViewport.getHorizontalScrollBar().setColour(juce::ScrollBar::thumbColourId, Tokens::borderStrong);

    // Keep a single, discoverable escape hatch for compound category filters.
    // It lives inside the same horizontally-scrollable pill strip so it remains
    // reachable on narrow windows without taking space from the primary actions.
    clearFiltersButton.setButtonText("ALL");
    clearFiltersButton.setTooltip("Show all categories (A)");
    clearFiltersButton.setColour(juce::TextButton::buttonColourId, Tokens::surfaceRaised);
    clearFiltersButton.setColour(juce::TextButton::buttonOnColourId, Tokens::selection);
    clearFiltersButton.setColour(juce::TextButton::textColourOffId, Tokens::foreground);
    clearFiltersButton.setColour(juce::TextButton::textColourOnId, Tokens::foreground);
    clearFiltersButton.setWantsKeyboardFocus(true);
    clearFiltersButton.onClick = [this]() {
        for (auto* btn : filterButtons)
            btn->setToggleState(true, juce::dontSendNotification);
        updateCanvasFilters();
    };
    filterBarContent.addAndMakeVisible(clearFiltersButton);
    clearFiltersButton.setVisible(false);

    sidebarContent.addAndMakeVisible(metadataGroup);
    metadataGroup.setText("SELECTED SAMPLE");
    metadataGroup.setTextLabelPosition(juce::Justification::centredLeft);
    metadataGroup.setColour(juce::GroupComponent::outlineColourId, Tokens::border);
    metadataGroup.setColour(juce::GroupComponent::textColourId, Tokens::mutedDim);

    sidebarContent.addAndMakeVisible(nameLabel);
    nameLabel.setText("Name:", juce::dontSendNotification);
    nameLabel.setFont(juce::Font(juce::FontOptions().withHeight(11.0f)));
    nameLabel.setColour(juce::Label::textColourId, Tokens::mutedDim);

    sidebarContent.addAndMakeVisible(nameVal);
    nameVal.setText("Select a sample", juce::dontSendNotification);
    nameVal.setFont(juce::Font(juce::FontOptions().withHeight(13.0f).withStyle("Bold")));
    nameVal.setColour(juce::Label::textColourId, Tokens::foreground);
    nameVal.setTooltip("Select a sample in the map or browser to inspect its metadata");

    sidebarContent.addAndMakeVisible(inspectorSummaryLabel);
    inspectorSummaryLabel.setFont(juce::Font(juce::FontOptions().withHeight(10.0f).withStyle("Bold")));
    inspectorSummaryLabel.setColour(juce::Label::textColourId, Tokens::mutedDim);
    inspectorSummaryLabel.setJustificationType(juce::Justification::centredLeft);
    inspectorSummaryLabel.setMinimumHorizontalScale(0.75f);
    inspectorSummaryLabel.setTooltip("Classifier confidence and winning evidence for the selected sample");

    sidebarContent.addAndMakeVisible(retryAnalysisButton);
    retryAnalysisButton.setButtonText("RETRY AI");
    retryAnalysisButton.setColour(juce::TextButton::buttonColourId, Tokens::warningBg);
    retryAnalysisButton.setColour(juce::TextButton::textColourOffId, Tokens::warningText);
    retryAnalysisButton.setTooltip("Retry transient AI analysis for this sample");
    retryAnalysisButton.onClick = [this]() {
        if (!hasSelection || selectedItem.embeddingStatus != EmbeddingStatus::FailedRetryable)
            return;

        const juce::File source(selectedItem.filePath);
        if (!source.existsAsFile()) {
            taxonomyStatusLabel.setText("file missing -- restore it before retrying", juce::dontSendNotification);
            return;
        }

        // FailedRetryable rows are deliberately not persisted as usable cache
        // entries, so re-admitting the exact path is enough to run the normal
        // decode/DSP/inference pipeline again without mutating source audio.
        retryAnalysisButton.setEnabled(false);
        retryAnalysisButton.setButtonText("QUEUED");
        audioProcessor.getEngine().addPathToQueue(selectedItem.filePath);
    };

    sidebarContent.addAndMakeVisible(bpmLabel);
    bpmLabel.setText("BPM:", juce::dontSendNotification);
    bpmLabel.setFont(juce::Font(juce::FontOptions().withHeight(11.0f)));
    bpmLabel.setColour(juce::Label::textColourId, Tokens::mutedDim);

    // Waveform Preview
    sidebarContent.addAndMakeVisible(waveformPreview);
    waveformPreview.clear();

    sidebarContent.addAndMakeVisible(bpmEditor);
    bpmEditor.setInputRestrictions(4, "0123456789.");
    bpmEditor.setColour(juce::TextEditor::backgroundColourId, Tokens::surfaceRaised);
    bpmEditor.setColour(juce::TextEditor::outlineColourId, Tokens::border);
    bpmEditor.setColour(juce::TextEditor::textColourId, Tokens::foreground);
    bpmEditor.setColour(juce::TextEditor::focusedOutlineColourId, Tokens::foreground);
    bpmEditor.setTooltip("Detected or manually corrected tempo in BPM; use WRITE TO FILE to persist it");

    sidebarContent.addAndMakeVisible(keyLabel);
    keyLabel.setText("Key / Scale:", juce::dontSendNotification);
    keyLabel.setFont(juce::Font(juce::FontOptions().withHeight(11.0f)));
    keyLabel.setColour(juce::Label::textColourId, Tokens::mutedDim);

    sidebarContent.addAndMakeVisible(keyEditor);
    keyEditor.setColour(juce::TextEditor::backgroundColourId, Tokens::surfaceRaised);
    keyEditor.setColour(juce::TextEditor::outlineColourId, Tokens::border);
    keyEditor.setColour(juce::TextEditor::textColourId, Tokens::foreground);
    keyEditor.setColour(juce::TextEditor::focusedOutlineColourId, Tokens::foreground);
    keyEditor.setTooltip("Detected or manually corrected musical key; one-shots are named by note");

    sidebarContent.addAndMakeVisible(typeLabel);
    typeLabel.setText("Instrument Type:", juce::dontSendNotification);
    typeLabel.setFont(juce::Font(juce::FontOptions().withHeight(11.0f)));
    typeLabel.setColour(juce::Label::textColourId, Tokens::mutedDim);

    sidebarContent.addAndMakeVisible(typeCombo);
    typeCombo.setColour(juce::ComboBox::backgroundColourId, Tokens::surfaceRaised);
    typeCombo.setColour(juce::ComboBox::outlineColourId, Tokens::border);
    typeCombo.setColour(juce::ComboBox::textColourId, Tokens::foreground);
    typeCombo.setColour(juce::ComboBox::arrowColourId, Tokens::muted);
    typeCombo.setTooltip("Legacy instrument label used for search and naming");
    typeCombo.addItem("Kick", 1);
    typeCombo.addItem("Snare", 2);
    typeCombo.addItem("Hi-Hat", 3);
    typeCombo.addItem("Clap", 4);
    typeCombo.addItem("Percussion", 5);
    typeCombo.addItem("Bass", 6);
    typeCombo.addItem("Synth", 7);
    typeCombo.addItem("Loop", 8);
    typeCombo.addItem("Vocal", 9);
    typeCombo.addItem("Explosion", 11);
    typeCombo.addItem("Laser", 12);
    typeCombo.addItem("Powerup", 13);
    typeCombo.addItem("Jump", 14);
    typeCombo.addItem("Coin", 15);
    typeCombo.addItem("UI", 16);
    typeCombo.addItem("Footstep", 17);
    typeCombo.addItem("Impact", 18);
    typeCombo.addItem("Other", 10);
    typeCombo.setSelectedId(10, juce::dontSendNotification);

    // Ableton taxonomy editor -- category is a closed combo box (matches
    // the "small set of top-level buckets" design, see AbletonTaxonomy.h),
    // subcategory stays free-text since the mission explicitly calls for
    // an open-ended subcategory vocabulary, not a hardcoded list.
    sidebarContent.addAndMakeVisible(taxonomyLabel);
    taxonomyLabel.setText("Ableton Tags:", juce::dontSendNotification);
    taxonomyLabel.setFont(juce::Font(juce::FontOptions().withHeight(11.0f)));
    taxonomyLabel.setColour(juce::Label::textColourId, Tokens::mutedDim);

    sidebarContent.addAndMakeVisible(categoryCombo);
    categoryCombo.setColour(juce::ComboBox::backgroundColourId, Tokens::surfaceRaised);
    categoryCombo.setColour(juce::ComboBox::outlineColourId, Tokens::border);
    categoryCombo.setColour(juce::ComboBox::textColourId, Tokens::foreground);
    categoryCombo.setColour(juce::ComboBox::arrowColourId, Tokens::muted);
    categoryCombo.setTextWhenNothingSelected("Category...");
    categoryCombo.setTooltip("Top-level Ableton taxonomy category");
    categoryCombo.addItem("Drums", 1);
    categoryCombo.addItem("Bass", 2);
    categoryCombo.addItem("Instruments", 3);
    categoryCombo.addItem("Vocals", 4);
    categoryCombo.addItem("FX", 5);
    categoryCombo.addItem("Ambience", 6);
    categoryCombo.setEditableText(true); // still free-text-capable -- the fixed set above is a shortcut, not a ceiling

    sidebarContent.addAndMakeVisible(subcategoryEditor);
    subcategoryEditor.setTextToShowWhenEmpty("Subcategory...", Tokens::mutedDim);
    subcategoryEditor.setColour(juce::TextEditor::backgroundColourId, Tokens::surfaceRaised);
    subcategoryEditor.setColour(juce::TextEditor::outlineColourId, Tokens::border);
    subcategoryEditor.setColour(juce::TextEditor::textColourId, Tokens::foreground);
    subcategoryEditor.setColour(juce::TextEditor::focusedOutlineColourId, Tokens::foreground);
    subcategoryEditor.setTooltip("Specific sound name or subcategory for this sample");

    sidebarContent.addAndMakeVisible(taxonomyStatusLabel);
    taxonomyStatusLabel.setFont(juce::Font(juce::FontOptions().withHeight(10.0f)));
    taxonomyStatusLabel.setColour(juce::Label::textColourId, Tokens::mutedDim);

    sidebarContent.addAndMakeVisible(suggestedTagsLabel);
    suggestedTagsLabel.setFont(juce::Font(juce::FontOptions().withHeight(11.0f)));
    suggestedTagsLabel.setColour(juce::Label::textColourId, Tokens::success);
    sidebarContent.addAndMakeVisible(audioModelLabel);
    audioModelLabel.setFont(juce::Font(juce::FontOptions().withHeight(11.0f)));
    audioModelLabel.setColour(juce::Label::textColourId, Tokens::mutedDim);
    audioModelLabel.setJustificationType(juce::Justification::centredLeft);
    audioModelLabel.setMinimumHorizontalScale(0.7f);
    audioModelLabel.setTooltip("Frozen audio-model view (no filename/folder fusion) vs the shown fused label");

    sidebarContent.addAndMakeVisible(taxonomyNoteLabel);
    taxonomyNoteLabel.setText("Correction note (optional):", juce::dontSendNotification);
    taxonomyNoteLabel.setFont(juce::Font(juce::FontOptions().withHeight(10.0f)));
    taxonomyNoteLabel.setColour(juce::Label::textColourId, Tokens::mutedDim);

    sidebarContent.addAndMakeVisible(taxonomyNoteEditor);
    taxonomyNoteEditor.setTextToShowWhenEmpty("e.g. rimshot, not in list, uncertain...", Tokens::mutedDim);
    taxonomyNoteEditor.setColour(juce::TextEditor::backgroundColourId, Tokens::surfaceRaised);
    taxonomyNoteEditor.setColour(juce::TextEditor::outlineColourId, Tokens::border);
    taxonomyNoteEditor.setColour(juce::TextEditor::textColourId, Tokens::foreground);
    taxonomyNoteEditor.setColour(juce::TextEditor::focusedOutlineColourId, Tokens::focusRing);
    taxonomyNoteEditor.setTooltip("Optional context stored with this correction for active-learning review");

    sidebarContent.addAndMakeVisible(saveTaxonomyButton);
    saveTaxonomyButton.setButtonText("SAVE TAGS");
    saveTaxonomyButton.setColour(juce::TextButton::buttonColourId, Tokens::surface);
    saveTaxonomyButton.setColour(juce::TextButton::textColourOffId, Tokens::foreground);
    saveTaxonomyButton.setTooltip("Save the category, subcategory, and correction note as a user override");
    saveTaxonomyButton.onClick = [this]() {
        if (!hasSelection) return;
        std::string category = categoryCombo.getText().toStdString();
        std::string subcategory = subcategoryEditor.getText().trim().toStdString();
        std::vector<std::string> secondaryTags = selectedItem.secondaryTags; // preserve existing (One-Shot/Loop/etc); not edited by this control
        const std::string userNote = taxonomyNoteEditor.getText().trim().toStdString();
        audioProcessor.getEngine().updateTaxonomyAsync(selectedItem.filePath, category, subcategory, secondaryTags, userNote);
        selectedItem.category = category;
        selectedItem.subcategory = subcategory;
        selectedItem.tagSource = "user";
        selectedItem.tagUserOverridden = true;
        selectedItem.tagConfidence = 1.0f;
        selectedItem.winningEvidence = "USER_OVERRIDE";
        taxonomyStatusLabel.setText("user-set", juce::dontSendNotification);
        taxonomyNoteEditor.clear();
    };

    sidebarContent.addAndMakeVisible(resetTaxonomyButton);
    resetTaxonomyButton.setButtonText("RESET TO AUTO");
    resetTaxonomyButton.setColour(juce::TextButton::buttonColourId, Tokens::surfaceRaised);
    resetTaxonomyButton.setColour(juce::TextButton::textColourOffId, Tokens::mutedDim);
    resetTaxonomyButton.setTooltip("Discard the manual override and allow automatic classification again");
    resetTaxonomyButton.onClick = [this]() {
        if (!hasSelection) return;
        audioProcessor.getEngine().resetTaxonomyToAuto(selectedItem.filePath);
        selectedItem.category.clear();
        selectedItem.subcategory.clear();
        selectedItem.secondaryTags.clear();
        selectedItem.tagConfidence = 0.0f;
        selectedItem.tagSource = "unclassified";
        selectedItem.tagUserOverridden = false;
        selectedItem.winningEvidence = "UNKNOWN";
        selectedItem.taxonomyVersion = 0;
        categoryCombo.clear(juce::dontSendNotification);
        subcategoryEditor.clear();
        taxonomyStatusLabel.setText("reset -- will re-classify on next scan", juce::dontSendNotification);
        taxonomyNoteEditor.clear();
    };

    // Experimental: pushes tags into Ableton's own (reverse-engineered,
    // unofficial) XMP tag sidecar so Live's Browser can actually filter on
    // them -- everything above only edits this app's internal database.
    sidebarContent.addAndMakeVisible(writeAbletonXmpButton);
    writeAbletonXmpButton.setButtonText("WRITE TO ABLETON (EXPERIMENTAL)");
    // Phase 8.6B fix: this action is non-destructive (it writes tags, with a
    // backup, and refuses on any doubt -- see onClick below) but was styled
    // in the same danger/red tokens as STOP, implying "destructive error"
    // rather than "experimental, treat with care". Amber is this codebase's
    // actual reserved warning/experimental accent (see DesignTokens.h) and
    // is the semantically correct token for this button.
    writeAbletonXmpButton.setColour(juce::TextButton::buttonColourId, Tokens::warningBg);
    writeAbletonXmpButton.setColour(juce::TextButton::textColourOffId, Tokens::warningText);
    writeAbletonXmpButton.setTooltip("Write taxonomy tags to an Ableton sidecar; a backup is made when possible");
    writeAbletonXmpButton.onClick = [this]() {
        if (!hasSelection) return;
        auto result = audioProcessor.getEngine().writeAbletonXmpTags(selectedItem.filePath);
        if (result.success) {
            taxonomyStatusLabel.setText(
                result.backupCreated ? "written to Ableton (backup made)" : "written to Ableton",
                juce::dontSendNotification);
        } else {
            juce::AlertWindow::showMessageBoxAsync(juce::MessageBoxIconType::WarningIcon,
                "Could Not Write Ableton Tags",
                "This is an experimental, unofficial feature (Ableton has no public API for "
                "sample tagging) -- it refused to write rather than risk your data:\n\n"
                + juce::String(result.errorMessage));
        }
    };

    // Playback Audition
    sidebarContent.addAndMakeVisible(playButton);
    playButton.setButtonText("PLAY");
    playButton.setColour(juce::TextButton::buttonColourId, Tokens::successSurface); // Subtle Green
    playButton.setColour(juce::TextButton::textColourOffId, Tokens::success);
    playButton.setColour(juce::TextButton::buttonOnColourId, Tokens::successSurfaceActive);
    playButton.setTooltip("Audition the selected sample (Space or Return)");
    playButton.onClick = [this]() {
        if (hasSelection) audioProcessor.playSample(selectedItem.filePath);
    };

    sidebarContent.addAndMakeVisible(stopButton);
    stopButton.setButtonText("STOP");
    stopButton.setColour(juce::TextButton::buttonColourId, Tokens::dangerSurface); // Subtle Red
    stopButton.setColour(juce::TextButton::textColourOffId, Tokens::danger);
    stopButton.setTooltip("Stop sample playback");
    stopButton.onClick = [this]() {
        audioProcessor.stopSample();
    };

    // "Sounds like this" -- acoustic similarity search against the
    // currently-selected sample, via the engine's HNSW index over real
    // trained embeddings (see SampleManagerEngine::findSimilarSamples).
    sidebarContent.addAndMakeVisible(findSimilarButton);
    findSimilarButton.setButtonText("FIND SIMILAR");
    findSimilarButton.setColour(juce::TextButton::buttonColourId, Tokens::surfaceRaised);
    findSimilarButton.setColour(juce::TextButton::textColourOffId, Tokens::foreground);
    findSimilarButton.setTooltip("Find acoustically similar samples (S)");
    findSimilarButton.onClick = [this]() { showSimilarSamplesReport(); };

    // Reference Search: acoustically search for files similar to an external reference audio file
    sidebarContent.addAndMakeVisible(findSimilarToReferenceButton);
    findSimilarToReferenceButton.setButtonText("FIND SIMILAR TO REF...");
    findSimilarToReferenceButton.setColour(juce::TextButton::buttonColourId, Tokens::surfaceRaised);
    findSimilarToReferenceButton.setColour(juce::TextButton::textColourOffId, Tokens::foreground);
    findSimilarToReferenceButton.setTooltip("Choose an external audio file and find acoustically similar samples");
    findSimilarToReferenceButton.onClick = [this]() { showReferenceSearchDialog(); };

    // Save metadata back directly to Wave file
    sidebarContent.addAndMakeVisible(saveButton);
    saveButton.setButtonText("WRITE TO FILE");
    saveButton.setColour(juce::TextButton::buttonColourId, Tokens::surface);
    saveButton.setColour(juce::TextButton::textColourOffId, Tokens::foreground);
    saveButton.setTooltip("Write the edited BPM, key, and metadata into the source file");
    saveButton.onClick = [this]() {
        saveSidebarMetadata();
    };

    // Folder Scanner Button
    addAndMakeVisible(importButton);
    importButton.setButtonText("SCAN LIBRARY");
    importButton.setColour(juce::TextButton::buttonColourId, Tokens::surfaceRaised);
    importButton.setColour(juce::TextButton::textColourOffId, Tokens::foreground);
    importButton.setTooltip("Add a folder to the SLO library");
    importButton.onClick = [this]() { openFolderScanner(); };

    // Confidence-aware review is a browse action, so keep it in the primary
    // toolbar rather than hiding it inside the selected-sample inspector.
    addAndMakeVisible(reviewQueueButton);
    reviewQueueButton.setButtonText("REVIEW QUEUE");
    reviewQueueButton.setColour(juce::TextButton::buttonColourId, Tokens::surfaceRaised);
    reviewQueueButton.setColour(juce::TextButton::textColourOffId, Tokens::warningText);
    reviewQueueButton.setTooltip("Review low-confidence and classified-unknown samples (R = full queue, U = unknown only)");
    reviewQueueButton.onClick = [this]() { showReviewQueue(); };

    // Label-free evidence review is also available in hosted plug-in formats;
    // the native macOS menu is only present for the standalone wrapper.
    sidebarContent.addAndMakeVisible(evidenceImportButton);
    evidenceImportButton.setButtonText("IMPORT AI EVIDENCE");
    evidenceImportButton.setColour(juce::TextButton::buttonColourId, Tokens::surfaceRaised);
    evidenceImportButton.setColour(juce::TextButton::textColourOffId, Tokens::foreground);
    evidenceImportButton.setTooltip("Open a read-only AI evidence packet for review");
    evidenceImportButton.onClick = [this]() { showEvidencePacketDialog(); };

    // Diagnostics export sits next to evidence import in every layout: support
    // bundles must be one click away in hosted (VST3/AU) formats too, where
    // the native macOS menu does not exist.
    sidebarContent.addAndMakeVisible(exportDiagnosticsButton);
    exportDiagnosticsButton.setButtonText("EXPORT DIAGNOSTICS");
    exportDiagnosticsButton.setColour(juce::TextButton::buttonColourId, Tokens::surfaceRaised);
    exportDiagnosticsButton.setColour(juce::TextButton::textColourOffId, Tokens::foreground);
    exportDiagnosticsButton.setTooltip("Save a support bundle: versions, thresholds, scan receipt, evidence splits, log tail");
    exportDiagnosticsButton.onClick = [this]() { exportDiagnosticsBundle(); };

    // Naming convention selection
    sidebarContent.addAndMakeVisible(namingLabel);
    namingLabel.setText("Naming Style:", juce::dontSendNotification);
    namingLabel.setColour(juce::Label::textColourId, Tokens::mutedDim);
    namingLabel.setFont(juce::Font(juce::FontOptions().withHeight(12.0f)));

    sidebarContent.addAndMakeVisible(namingCombo);
    namingCombo.setColour(juce::ComboBox::backgroundColourId, Tokens::surfaceRaised);
    namingCombo.setColour(juce::ComboBox::outlineColourId, Tokens::border);
    namingCombo.setColour(juce::ComboBox::textColourId, Tokens::foreground);
    namingCombo.setColour(juce::ComboBox::arrowColourId, Tokens::muted);
    namingCombo.addItem("Original Name", 1);
    namingCombo.addItem("lowerCamelCase", 2);
    namingCombo.addItem("snake_case", 3);
    namingCombo.addItem("Prefix Category", 4);
    namingCombo.addItem("Suffix Details", 5);
    namingCombo.addItem("Wwise (SFX_Category_Object_##)", 6);
    namingCombo.addItem("Ableton Places (Category/Subcategory)", 7);
    namingCombo.addItem("ThinkSpace (sx_category_action_##)", 8);
    namingCombo.addItem("Smart Producer", 9);
    namingCombo.setSelectedId(audioProcessor.getEditorNamingStyleId());
    namingCombo.onChange = [this]() {
        audioProcessor.setEditorNamingStyleId(namingCombo.getSelectedId());
    };

    // Reorganize files on disk based on category
    sidebarContent.addAndMakeVisible(sortButton);
    sortButton.setButtonText("SORT LIBRARY");
    sortButton.setColour(juce::TextButton::buttonColourId, Tokens::surfaceRaised2);
    sortButton.setColour(juce::TextButton::textColourOffId, Tokens::foreground);
    sortButton.setTooltip("Preview safe library organization and naming changes");
    sortButton.onClick = [this]() { performSortLibrary(); };

    addAndMakeVisible(sortLibraryTopButton);
    sortLibraryTopButton.setButtonText("SORT / RENAME");
    sortLibraryTopButton.setColour(juce::TextButton::buttonColourId, Tokens::surfaceRaised2);
    sortLibraryTopButton.setColour(juce::TextButton::textColourOffId, Tokens::electricCyan);
    sortLibraryTopButton.setTooltip("Sort and organize the entire sample library into organized subfolders and naming conventions.");
    sortLibraryTopButton.onClick = [this]() { performSortLibrary(); };

    addAndMakeVisible(undoSortTopButton);
    undoSortTopButton.setButtonText("UNDO SORT");
    undoSortTopButton.setColour(juce::TextButton::buttonColourId, Tokens::surfaceRaised2);
    undoSortTopButton.setColour(juce::TextButton::textColourOffId, Tokens::muted);
    undoSortTopButton.setTooltip("Undo the last sort / rename operation and restore files.");
    undoSortTopButton.setEnabled(audioProcessor.getEngine().canUndoSort());
    undoSortTopButton.onClick = [this]() { performUndoSort(); };

    // Find exact-content duplicate samples (identical audio, any filename/
    // path/metadata) -- reports only, no deletion. Deciding what to do about
    // a duplicate (keep which copy, delete which) is the kind of action that
    // should always be an explicit, per-item user choice, not automated.
    sidebarContent.addAndMakeVisible(findDuplicatesButton);
    findDuplicatesButton.setButtonText("FIND DUPLICATES");
    findDuplicatesButton.setColour(juce::TextButton::buttonColourId, Tokens::surfaceRaised2);
    // Phase 8.6B fix: this is a read-only report (see comment above -- no
    // deletion happens here) but was styled with the danger/red text token,
    // implying a destructive action. Neutral foreground matches this
    // button's actual sibling actions (Sort Library, Scan Folder).
    findDuplicatesButton.setColour(juce::TextButton::textColourOffId, Tokens::foreground);
    findDuplicatesButton.setTooltip("Find exact and near-duplicate audio files (read-only report)");
    findDuplicatesButton.onClick = [this]() { showDuplicatesReport(); };

    // 4. Hook canvas and browser selections
    canvas.setSelectedCallback([this](const SampleItem& item) {
        updateSelectionDetails(item);
        browser.selectSampleByPath(item.filePath);
    });

    canvas.setDoubleClickedCallback([this](const SampleItem& item) {
        audioProcessor.playSample(item.filePath);
    });
    canvas.setEmptyStateActionCallback([this]() { openFolderScanner(); });

    addAndMakeVisible(browser);
    browser.setSelectedCallback([this](const SampleItem& item) {
        updateSelectionDetails(item);
        canvas.selectSampleByPath(item.filePath);
    });
    browser.setDoubleClickedCallback([this](const SampleItem& item) {
        audioProcessor.playSample(item.filePath);
    });
    browser.setEmptyStateActionCallback([this]() { openFolderScanner(); });
    // Layout buttons config
    auto setupTabButton = [this](juce::TextButton& btn, const juce::String& text, LayoutMode mode) {
        btn.setButtonText(text);
        btn.setClickingTogglesState(true);
        btn.setRadioGroupId(1001);
        btn.setColour(juce::TextButton::buttonColourId, Tokens::surfaceRaised);
        btn.setColour(juce::TextButton::textColourOffId, Tokens::mutedDim);
        btn.setColour(juce::TextButton::buttonOnColourId, Tokens::selection);
        btn.setColour(juce::TextButton::textColourOnId, Tokens::accentInteractive);
        btn.onClick = [this, mode]() { currentLayoutMode = mode; updateLayoutMode(); };
        addAndMakeVisible(btn);
    };
    setupTabButton(gridTabButton, "LIST", GridOnly);
    setupTabButton(mapTabButton, "MAP", MapOnly);
    setupTabButton(splitTabButton, "SPLIT", SplitView);
    gridTabButton.setTooltip("Show the precision browser list");
    mapTabButton.setTooltip("Show the visual sample map");
    splitTabButton.setTooltip("Show the map and browser together");
    splitTabButton.setToggleState(true, juce::dontSendNotification);

    // Draggable Split Divider Configuration
    addAndMakeVisible(splitDivider);
    splitDivider.onDragStart = [this]() {
        // Find current division point in local coordinates to base delta offset on
        auto workspaceArea = getLocalBounds().reduced(Tokens::space3, 0);
        float headerH = 52.0f;
        float filterBarH = getWidth() < 900 ? 68.0f : 44.0f;
        const float workspaceH = static_cast<float>(workspaceArea.getHeight())
            - headerH - filterBarH; // deduct header + filter bar
        dragStartSplitY = static_cast<int>(headerH + filterBarH + workspaceH * splitFraction);
    };
    splitDivider.onDrag = [this](int deltaY) {
        if (currentLayoutMode != SplitView) return;
        auto workspaceArea = getLocalBounds().reduced(Tokens::space3, 0);
        float headerH = 52.0f;
        float filterBarH = getWidth() < 900 ? 68.0f : 44.0f;
        const float workspaceH = static_cast<float>(workspaceArea.getHeight())
            - headerH - filterBarH;
        if (workspaceH <= 0.0f) return;
        
        int targetY = dragStartSplitY + deltaY;
        // Enforce minimum top (Map) and bottom (Browser) boundaries to prevent overlapping
        int minY = static_cast<int>(headerH + filterBarH + 120);
        int maxY = static_cast<int>(getLocalBounds().getHeight() - 120);
        targetY = juce::jlimit(minY, maxY, targetY);
        
        splitFraction = (static_cast<float>(targetY) - headerH - filterBarH) / workspaceH;
        resized();
    };
    splitDivider.onKeyStep = [this](int direction) {
        if (currentLayoutMode != SplitView)
            return;

        auto workspaceArea = getLocalBounds().reduced(Tokens::space3, 0);
        const float headerH = 52.0f;
        const float filterBarH = getWidth() < 900 ? 68.0f : 44.0f;
        const float workspaceH = static_cast<float>(workspaceArea.getHeight())
            - headerH - filterBarH;
        if (workspaceH <= 0.0f)
            return;

        // Keep both panes at the same 120 px minimum used by mouse dragging.
        // A small 2% step makes keyboard adjustment deliberate but quick.
        const float minimumFraction = 120.0f / workspaceH;
        const float maximumFraction = 1.0f - (120.0f + 4.0f) / workspaceH;
        splitFraction = juce::jlimit(minimumFraction, maximumFraction,
                                     splitFraction + static_cast<float>(direction) * 0.02f);
        resized();
    };

    // Favorites & History buttons configuration
    auto setupQuickTabButton = [this](juce::TextButton& btn, const juce::String& text, std::function<void()> onClick) {
        btn.setButtonText(text);
        btn.setColour(juce::TextButton::buttonColourId, Tokens::surfaceRaised);
        btn.setColour(juce::TextButton::textColourOffId, Tokens::mutedDim);
        btn.setColour(juce::TextButton::buttonOnColourId, Tokens::selection);
        btn.setColour(juce::TextButton::textColourOnId, Tokens::accentInteractive);
        btn.onClick = onClick;
        addAndMakeVisible(btn);
    };
    setupQuickTabButton(favoritesTabButton, "FAVORITES", [this]() { toggleFavoritesView(); });
    setupQuickTabButton(historyTabButton, "HISTORY", [this]() { toggleHistoryView(); });
    favoritesTabButton.setTooltip("Browse favorite samples (F toggles the selected sample)");
    historyTabButton.setTooltip("Browse recently played samples");


    // Find Similar / Find Duplicates results overlay -- see PluginEditor.h
    // comment on resultsPanel. Starts hidden; showResultsPanel()/
    // hideResultsPanel() toggle it. Added last in z-order (after canvas) so
    // it paints on top.
    addChildComponent(resultsPanel);
    resultsPanel.setCloseCallback([this]() { hideResultsPanel(); });
    resultsPanel.setRowSelectedCallback([this](const juce::String& filePath) {
        selectSampleByPath(filePath);
    });

    // Smart Collections panel config
    addChildComponent(smartCollectionsPanel);
    smartCollectionsPanel.setEngine(&audioProcessor.getEngine());
    smartCollectionsPanel.setCloseCallback([this]() { hideSmartCollectionsPanel(); });
    smartCollectionsPanel.setSampleSelectedCallback([this](const SampleItem& item) {
        updateSelectionDetails(item);
        selectSampleByPath(item.filePath);
    });

    sidebarContent.addAndMakeVisible(smartCollectionsButton);
    smartCollectionsButton.setButtonText("SMART COLLECTIONS");
    smartCollectionsButton.setColour(juce::TextButton::buttonColourId, Tokens::surfaceRaised2);
    smartCollectionsButton.setColour(juce::TextButton::textColourOffId, Tokens::foreground);
    smartCollectionsButton.setTooltip("Build and reuse saved filters for your sample library");
    smartCollectionsButton.onClick = [this]() { showSmartCollectionsPanel(); };

    addChildComponent(sortPreviewPanel);
    sortPreviewPanel.setConfirmCallback([this](bool copyInsteadOfMove) {
        startSortLibrary(copyInsteadOfMove);
    });
    sortPreviewPanel.setCancelCallback([this]() {
        hideSortPreview();
    });
    sortPreviewPanel.setUndoPreviousCallback([this]() {
        hideSortPreview();
        performUndoSort();
    });

    // Restore persisted editor state (search text, naming style) -- see
    // PluginProcessor::getStateInformation()/setStateInformation(). Done here,
    // after both searchField and canvas exist, rather than in the processor
    // constructor, since restoring is purely an editor-UI concern.
    {
        auto restoredSearch = audioProcessor.getEditorSearchText();
        if (restoredSearch.isNotEmpty()) {
            searchField.setText(restoredSearch, juce::dontSendNotification);
            clearSearchButton.setVisible(true);
            canvas.setSearchQuery(restoredSearch);
            browser.setSearchQuery(restoredSearch);
        }
    }

    // 5. Start periodic GUI updates.
    startTimerHz(60);

    // Hide detailed controls by default until a sample is selected (Empty state polish)
    bpmLabel.setVisible(false);
    bpmEditor.setVisible(false);
    keyLabel.setVisible(false);
    keyEditor.setVisible(false);
    typeLabel.setVisible(false);
    typeCombo.setVisible(false);
    taxonomyLabel.setVisible(false);
    categoryCombo.setVisible(false);
    subcategoryEditor.setVisible(false);
    taxonomyStatusLabel.setVisible(false);
    suggestedTagsLabel.setVisible(false);
    audioModelLabel.setVisible(false);
    taxonomyNoteLabel.setVisible(false);
    taxonomyNoteEditor.setVisible(false);
    saveTaxonomyButton.setVisible(false);
    resetTaxonomyButton.setVisible(false);
    writeAbletonXmpButton.setVisible(false);
    playButton.setVisible(false);
    stopButton.setVisible(false);
    waveformPreview.setVisible(false);
    saveButton.setVisible(false);
    namingLabel.setVisible(false);
    namingCombo.setVisible(false);
    sortButton.setVisible(false);
    metadataGroup.setVisible(false);
    inspectorSummaryLabel.setVisible(false);
    retryAnalysisButton.setVisible(false);

    // Native macOS menu bar -- Standalone only. Hosted-in-a-DAW instances
    // (VST3/AU) must never replace the host's own menu bar or call
    // JUCEApplicationBase::quit() (there may not even be a JUCEApplication
    // instance in that case), so this is strictly gated on wrapperType.
   #if JUCE_MAC
    if (p.wrapperType == juce::AudioProcessor::wrapperType_Standalone) {
        menuModel.onScanFolder = [this]() { openFolderScanner(); };
        menuModel.onPreferences = [this]() { showPreferencesDialog(audioProcessor); };
        menuModel.onFindDuplicates = [this]() { showDuplicatesReport(); };
        menuModel.onFindSimilar = [this]() { showSimilarSamplesReport(); };
        menuModel.onImportEvidence = [this]() { showEvidencePacketDialog(); };
        menuModel.onExportDiagnostics = [this]() { exportDiagnosticsBundle(); };
        menuModel.onSortLibrary = [this]() { performSortLibrary(); };
        menuModel.onUndoSort = [this]() { performUndoSort(); };
        menuModel.onRemoveMissingFiles = [this]() { performRemoveMissingFiles(); };
        menuModel.onAbout = []() {
            juce::AlertWindow::showMessageBoxAsync(juce::MessageBoxIconType::InfoIcon,
                "About SLO",
                "SLO\nversion 1.0.0 (dev build)\n\n"
                "AI-assisted sample library management with similarity mapping, "
                "BPM/key detection, and duplicate detection.");
        };
        juce::MenuBarModel::setMacMainMenu(&menuModel);
        nativeMenuBarActive = true;
    }
   #endif
}

SmartSampleManagerAudioProcessorEditor::~SmartSampleManagerAudioProcessorEditor()
{
    setLookAndFeel(nullptr);

   #if JUCE_MAC
    if (nativeMenuBarActive) {
        juce::MenuBarModel::setMacMainMenu(nullptr);
    }
   #endif

    auto& savedProps = AppSettings::getInstance().getProps();
    savedProps.setValue("editorWidth", getWidth());
    savedProps.setValue("editorHeight", getHeight());
    savedProps.saveIfNeeded();
}

void SmartSampleManagerAudioProcessorEditor::paint(juce::Graphics& g)
{
    // Draw background layout border splits
    g.fillAll(Tokens::background);

    // A thin, global progress rule gives long scans an immediate visual rhythm
    // without stealing space from the browse surface. It follows the same
    // honest done/total counters shown in the status label and disappears once
    // the engine enters its finalising/ready state. It sits on the clear lower
    // edge of the header so child filter viewports cannot paint over it.
    const auto scanProgress = audioProcessor.getEngine().getScanProgress();
    if (scanProgress.inProgress && scanProgress.total > 0)
    {
        const float fraction = juce::jlimit(0.0f, 1.0f,
            static_cast<float>(scanProgress.done) / static_cast<float>(scanProgress.total));
        const float y = 50.0f;
        g.setColour(Tokens::border);
        g.fillRect(0.0f, y, static_cast<float>(getWidth()), 2.0f);
        g.setColour(Tokens::accentInteractive.withAlpha(0.9f));
        g.fillRect(0.0f, y, static_cast<float>(getWidth()) * fraction, 2.0f);
    }

    // Draw NITE DSP vector brand logo mark
    auto logoArea = juce::Rectangle<float>(16.0f, 15.0f, 22.0f, 22.0f);
    BrandIdentity::drawLogoMark(g, logoArea, Tokens::brandLogoColour);

    // Drag-and-drop import target. Order matters: the scrim is filled FIRST,
    // then the border and label are drawn on top. Before Phase 8.5 the border
    // was drawn first and then covered by a full-bounds 70%-opacity fill, so
    // the drop affordance -- the one thing that has to read instantly while
    // the user is mid-drag -- was rendered at 30% of its intended strength.
    if (isDragOver) {
        g.setColour(Tokens::background.withAlpha(0.7f));
        g.fillRect(getLocalBounds());

        g.setColour(Tokens::foreground.withAlpha(0.6f));
        g.drawRect(getLocalBounds(), 4.0f);

        g.setColour(Tokens::foreground);
        g.setFont(juce::Font(juce::FontOptions().withHeight(20.0f).withStyle("Bold")));
        const auto prompt = dragHasUnsupportedFiles
            ? "Drop audio or folders — unsupported items will be skipped"
            : "Drop samples or folders to add them";
        g.drawFittedText(prompt, getLocalBounds(), juce::Justification::centred, 1);
    }
}

void SmartSampleManagerAudioProcessorEditor::resized()
{
    auto area = getLocalBounds();
    const bool compactLayout = getWidth() < 900;

    // Header is deliberately compact: identity, workspace switcher and live
    // context only. Library actions stay in the inspector/menu instead of
    // competing with the primary browse workflow.
    auto headerArea = area.removeFromTop(52).reduced(Tokens::space4, 0);
    // Shift title label bounds right by 28px to leave room for the logo mark (22px logo + 6px gap)
    headerArea.removeFromLeft(28);
    titleLabel.setBounds(headerArea.removeFromLeft(compactLayout ? 104 : 182));

    // Position favorites & history tab buttons next to workspace switcher
    int favW = compactLayout ? 75 : 90;
    historyTabButton.setBounds(headerArea.removeFromRight(favW).reduced(2, 9));
    favoritesTabButton.setBounds(headerArea.removeFromRight(favW).reduced(2, 9));
    headerArea.removeFromRight(Tokens::space2);

    // Position tab buttons in header center
    int tabW = compactLayout ? 50 : 68;
    splitTabButton.setBounds(headerArea.removeFromRight(tabW).reduced(2, 9));
    mapTabButton.setBounds(headerArea.removeFromRight(tabW).reduced(2, 9));
    gridTabButton.setBounds(headerArea.removeFromRight(tabW).reduced(2, 9));
    headerArea.removeFromRight(compactLayout ? Tokens::space1 : Tokens::space3);

    // Keep model/scan state visible at every supported width. Compact mode
    // gets a short status chip in the remaining header space; the complete
    // DAW/map details remain available via its tooltip.
    statusLabel.setVisible(true);
    statusLabel.setBounds(headerArea.removeFromRight(compactLayout ? 150 : 330));

    // 2. Sidebar panel on the right (220px wide), hosted in a Viewport so
    // content scrolls rather than clips at small window heights (Phase 8.6B
    // fix -- see PluginEditor.h comment on sidebarViewport).
    auto sidebarArea = area.removeFromRight(compactLayout ? 230 : 270);
    sidebarViewport.setBounds(sidebarArea);
    // Reserve room for the vertical scrollbar so the content never needs a
    // horizontal one too.
    int contentWidth = sidebarArea.getWidth() - sidebarViewport.getScrollBarThickness();
    sidebarContent.setSize(contentWidth, sidebarContentHeight);
    layoutSidebarContent(contentWidth);

    // 3. Category Filter Bar. Desktop keeps actions and category pills on one
    // line; compact windows get a second, horizontally-scrollable pill row so
    // filtering never disappears at the minimum supported width.
    const int filterBarHeight = compactLayout ? 68 : 44;
    auto filterBarArea = area.removeFromTop(filterBarHeight).reduced(Tokens::space3, 0);
    auto actionRow = filterBarArea;
    if (compactLayout)
        actionRow = filterBarArea.removeFromTop(32);

    const auto searchWidth = compactLayout
        ? juce::jlimit(150, 190, actionRow.getWidth() / 3)
        : juce::jlimit(220, 350, actionRow.getWidth() / 3);
    auto searchArea = actionRow.removeFromLeft(searchWidth).reduced(0, compactLayout ? 2 : 5);
    // Keep the clear affordance in the same visual field as the editor. The
    // input loses only 24 px, while mouse users gain a discoverable one-click
    // escape hatch that mirrors the existing Escape shortcut.
    auto clearArea = searchArea.removeFromRight(24);
    searchField.setBounds(searchArea);
    clearSearchButton.setBounds(clearArea);
    actionRow.removeFromLeft(Tokens::space3);
    importButton.setBounds(actionRow.removeFromLeft(compactLayout ? 92 : 112).reduced(0, compactLayout ? 2 : 5));
    actionRow.removeFromLeft(Tokens::space2);
    reviewQueueButton.setButtonText(compactLayout ? "REVIEW" : "REVIEW QUEUE");
    reviewQueueButton.setBounds(actionRow.removeFromLeft(compactLayout ? 82 : 116).reduced(0, compactLayout ? 2 : 5));
    actionRow.removeFromLeft(Tokens::space2);
    sortLibraryTopButton.setVisible(!compactLayout);
    undoSortTopButton.setVisible(!compactLayout);
    if (!compactLayout)
    {
        sortLibraryTopButton.setBounds(actionRow.removeFromLeft(124).reduced(0, 5));
        actionRow.removeFromLeft(Tokens::space2);
        undoSortTopButton.setBounds(actionRow.removeFromLeft(96).reduced(0, 5));
        actionRow.removeFromLeft(Tokens::space2);
    }

    if (compactLayout)
    {
        filterBarArea.removeFromTop(4);
        filterBarViewport.setVisible(!filterButtons.isEmpty());
    }
    else
    {
        filterBarViewport.setVisible(!filterButtons.isEmpty());
    }

    if (!filterButtons.isEmpty() && filterBarViewport.isVisible()) {
        filterBarViewport.setBounds(filterBarArea);
        clearFiltersButton.setVisible(true);
        auto pillArea = juce::Rectangle<int>(0, 0, filterPillWidth * (filterButtons.size() + 1),
                                              filterBarArea.getHeight());
        filterBarContent.setSize(pillArea.getWidth(), pillArea.getHeight());
        clearFiltersButton.setBounds(pillArea.removeFromLeft(filterPillWidth).reduced(2, compactLayout ? 2 : 6));
        for (auto* btn : filterButtons) {
            btn->setBounds(pillArea.removeFromLeft(filterPillWidth).reduced(2, compactLayout ? 2 : 6));
        }
    }
    else
    {
        clearFiltersButton.setVisible(false);
    }

    // 4. Central workspace Canvas / Table list.
    auto workspaceArea = area.reduced(Tokens::space3, 0);
    // Preserve the complete workspace before SplitView consumes the rectangle
    // into map/divider/browser regions. Overlays are modal to the workspace,
    // not to whichever child region happens to be left in `workspaceArea`.
    const auto workspaceBounds = workspaceArea;
    if (currentLayoutMode == GridOnly) {
        canvas.setVisible(false);
        browser.setVisible(true);
        browser.setBounds(workspaceArea);
        splitDivider.setVisible(false);
    } else if (currentLayoutMode == MapOnly) {
        browser.setVisible(false);
        canvas.setVisible(true);
        canvas.setBounds(workspaceArea);
        splitDivider.setVisible(false);
    } else { // SplitView
        canvas.setVisible(true);
        browser.setVisible(true);
        splitDivider.setVisible(true);
        
        int totalH = workspaceArea.getHeight();
        int dividerHeight = 4;
        int canvasH = static_cast<int>((totalH - dividerHeight) * splitFraction);
        
        canvas.setBounds(workspaceArea.removeFromTop(canvasH));
        splitDivider.setBounds(workspaceArea.removeFromTop(dividerHeight));
        browser.setBounds(workspaceArea);
    }

    // Results overlay (Find Similar / Find Duplicates) -- floats above the
    // workspace, inset so context stays visible.
    resultsPanel.setBounds(workspaceBounds.reduced(workspaceBounds.getWidth() / 8,
                                                    workspaceBounds.getHeight() / 10));
    smartCollectionsPanel.setBounds(workspaceBounds);
    sortPreviewPanel.setBounds(getLocalBounds());
}

void SmartSampleManagerAudioProcessorEditor::layoutSidebarContent(int contentWidth)
{
    juce::Rectangle<int> full(0, 0, contentWidth, sidebarContentHeight);
    
    if (!hasSelection) {
        // Make the inspector's initial state feel intentional rather than
        // leaving a small label stranded at the top-left of a large panel.
        // Keep library-level actions reachable here as well. Compact hosted
        // plug-in layouts hide the duplicate top-toolbar actions to preserve
        // browse space, and those hosts do not have the Standalone menu bar;
        // hiding the sidebar actions too would strand sorting and reports until
        // a sample happened to be selected.
        nameVal.setBounds(full.removeFromTop(176).reduced(20));
        nameVal.setText("SELECT A SAMPLE\nChoose a row to inspect metadata", juce::dontSendNotification);
        nameVal.setJustificationType(juce::Justification::centred);
        nameVal.setColour(juce::Label::textColourId, Tokens::muted);

        sortButton.setVisible(true);
        findDuplicatesButton.setVisible(true);
        evidenceImportButton.setVisible(true);
        exportDiagnosticsButton.setVisible(true);
        smartCollectionsButton.setVisible(true);
        auto libraryActions = full.removeFromTop(200).reduced(10);
        sortButton.setBounds(libraryActions.removeFromTop(28));
        libraryActions.removeFromTop(8);
        findDuplicatesButton.setBounds(libraryActions.removeFromTop(28));
        libraryActions.removeFromTop(8);
        evidenceImportButton.setBounds(libraryActions.removeFromTop(28));
        libraryActions.removeFromTop(8);
        exportDiagnosticsButton.setBounds(libraryActions.removeFromTop(28));
        libraryActions.removeFromTop(8);
        smartCollectionsButton.setBounds(libraryActions.removeFromTop(28));
        return;
    }

    // Selected sample metadata group. Keep the card compact for the common
    // case; expand it only when the contextual retry action is actually
    // present so normal samples do not carry a conspicuous blank strip.
    const int metadataHeight = retryAnalysisButton.isVisible() ? 214 : 186;
    metadataGroup.setBounds(full.removeFromTop(metadataHeight).reduced(10));
    auto content = metadataGroup.getBounds().reduced(12);
    content.removeFromTop(10); // Offset under label header

    nameLabel.setBounds(content.removeFromTop(12));
    nameVal.setBounds(content.removeFromTop(20));
    content.removeFromTop(3);
    inspectorSummaryLabel.setBounds(content.removeFromTop(16));
    content.removeFromTop(5);
    
    // Waveform and Preview Transport Row
    const int previewHeight = retryAnalysisButton.isVisible() ? 84 : 56;
    auto previewRow = content.removeFromTop(previewHeight);
    waveformPreview.setBounds(previewRow.removeFromLeft(previewRow.getWidth() - 90));
    previewRow.removeFromLeft(8);
    playButton.setBounds(previewRow.removeFromTop(24));
    previewRow.removeFromTop(4);
    stopButton.setBounds(previewRow.removeFromTop(24));
    previewRow.removeFromTop(4);
    if (retryAnalysisButton.isVisible())
        retryAnalysisButton.setBounds(previewRow.removeFromTop(24));
    
    // Attributes / Editable Metadata Panel
    full.removeFromTop(8);
    auto attribsArea = full.removeFromTop(110).reduced(10);
    int colW = (attribsArea.getWidth() - 10) / 2;
    auto leftCol = attribsArea.removeFromLeft(colW);
    attribsArea.removeFromLeft(10);
    auto rightCol = attribsArea;
    
    bpmLabel.setBounds(leftCol.removeFromTop(12));
    bpmEditor.setBounds(leftCol.removeFromTop(24));
    leftCol.removeFromTop(6);
    typeLabel.setBounds(leftCol.removeFromTop(12));
    typeCombo.setBounds(leftCol.removeFromTop(24));

    keyLabel.setBounds(rightCol.removeFromTop(12));
    keyEditor.setBounds(rightCol.removeFromTop(24));
    rightCol.removeFromTop(6);
    namingLabel.setBounds(rightCol.removeFromTop(12));
    namingCombo.setBounds(rightCol.removeFromTop(24));

    // Save attribute changes row
    full.removeFromTop(8);
    auto saveAttrRow = full.removeFromTop(28).reduced(10, 2);
    saveButton.setBounds(saveAttrRow.removeFromLeft(120));
    saveAttrRow.removeFromLeft(8);
    sortButton.setBounds(saveAttrRow);

    // Ableton classification group
    full.removeFromTop(12);
    auto abletonArea = full.removeFromTop(225).reduced(10);
    
    taxonomyLabel.setBounds(abletonArea.removeFromTop(12));
    abletonArea.removeFromTop(4);
    categoryCombo.setBounds(abletonArea.removeFromTop(24));
    abletonArea.removeFromTop(6);
    subcategoryEditor.setBounds(abletonArea.removeFromTop(24));
    abletonArea.removeFromTop(6);
    taxonomyStatusLabel.setBounds(abletonArea.removeFromTop(14));
    suggestedTagsLabel.setBounds(abletonArea.removeFromTop(14));
    audioModelLabel.setBounds(abletonArea.removeFromTop(14));
    abletonArea.removeFromTop(6);

    taxonomyNoteLabel.setBounds(abletonArea.removeFromTop(12));
    taxonomyNoteEditor.setBounds(abletonArea.removeFromTop(24));
    abletonArea.removeFromTop(6);
    
    auto tagActionRow = abletonArea.removeFromTop(26);
    saveTaxonomyButton.setBounds(tagActionRow.removeFromLeft(colW));
    tagActionRow.removeFromLeft(10);
    resetTaxonomyButton.setBounds(tagActionRow);
    abletonArea.removeFromTop(6);
    writeAbletonXmpButton.setBounds(abletonArea.removeFromTop(26));

    // Discovery workflows
    full.removeFromTop(16);
    auto discoveryArea = full.removeFromTop(80).reduced(10);
    findSimilarButton.setBounds(discoveryArea.removeFromTop(28));
    discoveryArea.removeFromTop(8);
    findSimilarToReferenceButton.setBounds(discoveryArea.removeFromTop(28));

    // Library operations group
    full.removeFromTop(16);
    auto libArea = full.reduced(10);
    findDuplicatesButton.setBounds(libArea.removeFromTop(28));
    libArea.removeFromTop(8);
    evidenceImportButton.setBounds(libArea.removeFromTop(28));
    libArea.removeFromTop(8);
    exportDiagnosticsButton.setBounds(libArea.removeFromTop(28));
    libArea.removeFromTop(8);
    smartCollectionsButton.setBounds(libArea.removeFromTop(28));
}

bool SmartSampleManagerAudioProcessorEditor::isInterestedInFileDrag(const juce::StringArray& files)
{
    return std::any_of(files.begin(), files.end(), [](const juce::String& path) {
        return isSupportedDropPath(path);
    });
}

void SmartSampleManagerAudioProcessorEditor::fileDragEnter(const juce::StringArray& files, int x, int y)
{
    isDragOver = isInterestedInFileDrag(files);
    dragHasUnsupportedFiles = isDragOver && std::any_of(files.begin(), files.end(), [](const juce::String& path) {
        return !isSupportedDropPath(path);
    });
    repaint();
}

void SmartSampleManagerAudioProcessorEditor::fileDragExit(const juce::StringArray& files)
{
    isDragOver = false;
    dragHasUnsupportedFiles = false;
    repaint();
}

void SmartSampleManagerAudioProcessorEditor::filesDropped(const juce::StringArray& files, int x, int y)
{
    isDragOver = false;
    dragHasUnsupportedFiles = false;
    repaint();

    int queuedAny = 0;
    int unsupportedDrops = 0;
    for (const auto& file : files) {
        if (isSupportedDropPath(file)) {
            audioProcessor.getEngine().addPathToQueue(file.toStdString());
            ++queuedAny;
        } else {
            ++unsupportedDrops;
        }
    }
    if (unsupportedDrops == 0) return;
    if (queuedAny > 0) {
        // A scan is starting (or joining a running one): fold the drops the
        // UI pre-filtered into its receipt. Called AFTER the admissions above
        // so no fresh-scan reset can erase the credit (see noteSkippedDrops).
        audioProcessor.getEngine().noteSkippedDrops(unsupportedDrops);
    } else {
        // Nothing supportable was dropped, so no scan will start and no
        // receipt will ever report these -- say so now instead of staying
        // silent, which previously read as "the drop did nothing".
        juce::AlertWindow::showMessageBoxAsync(juce::MessageBoxIconType::InfoIcon,
            "Drop Skipped",
            juce::String(unsupportedDrops) + " dropped item"
                + (unsupportedDrops == 1 ? " is" : "s are")
                + " not audio SLO can read -- nothing was added. "
                  "Supported inputs are audio files and folders containing them.");
    }
}

void SmartSampleManagerAudioProcessorEditor::timerCallback()
{
    auto& engine = audioProcessor.getEngine();

    // Update DAW status display
    double dawBpm = audioProcessor.getDawBpm();
    bool isDawPlaying = audioProcessor.getIsDawPlaying();

    // Fast path, every tick (this timer now runs at 60Hz): drain any brand-new
    // samples off the engine's lock-free FIFO and append them directly to the
    // canvas. This is the common case during an active scan, and it avoids
    // copying the *entire* (potentially 100k+ item) sample list just to pick up
    // a handful of new ones — draining an empty FIFO is essentially free, so
    // this is safe to call unconditionally every frame.
    std::vector<SampleItem> freshlyAdded;
    int drained = engine.drainNewSampleEvents(freshlyAdded, 256);
    if (drained > 0) {
        canvas.appendNewSamples(freshlyAdded);
        lastKnownSampleCount += static_cast<size_t>(drained);

        bool categoriesChanged = false;
        for (const auto& s : freshlyAdded) {
            // Prefer the broad taxonomy category for filter pills. The legacy
            // instrumentType is still the useful fallback for older rows that
            // have not been assigned the newer category/subcategory pair.
            std::string c = ClassificationPresentation::filterCategory(
                s.category, s.instrumentType);
            if (std::find(currentCategories.begin(), currentCategories.end(), c) == currentCategories.end()) {
                currentCategories.push_back(c);
                categoriesChanged = true;
            }
        }
        if (categoriesChanged) {
            std::sort(currentCategories.begin(), currentCategories.end());
            updateCategoryButtons();
        }
    }

    // The engine bumps its version counter on ANY change to `samples`, including
    // ones the FIFO fast path above can't represent (an explicit UMAP re-anchor
    // moving existing points, a metadata edit changing an existing point's
    // category, reorganizeSamples() rewriting paths). getSampleCount() is O(1)
    // (no vector copy), so we can cheaply tell whether the FIFO already caught us
    // up to the engine's current size — if so, whatever changed wasn't a plain
    // append and we still need the full resync below; if the count differs, we
    // also need it (FIFO overflowed, or this is the very first load).
    uint64_t currentVersion = engine.getSamplesVersion();
    if (!hasCompletedInitialSampleSync || currentVersion != lastSeenSamplesVersion) {
        lastSeenSamplesVersion = currentVersion;
        hasCompletedInitialSampleSync = true;

        std::vector<SampleItem> activeSamples = engine.getSamples();
        lastKnownSampleCount = activeSamples.size();

        // Keep the inspector's cached item in lockstep with asynchronous scan
        // and classification updates. Without this, a selected sample could
        // remain visibly UNCLASSIFIED (or show stale BPM/key/confidence) while
        // its row and map point had already refreshed. Never overwrite an
        // actively edited inspector field; the next engine version after the
        // edit commits will refresh it safely.
        if (hasSelection)
        {
            const auto selectedIt = std::find_if(activeSamples.begin(), activeSamples.end(),
                [this](const SampleItem& item) { return item.filePath == selectedItem.filePath; });
            auto* focused = juce::Component::getCurrentlyFocusedComponent();
            const bool editingInspector = focused == &bpmEditor
                || focused == &keyEditor
                || focused == &typeCombo
                || focused == &categoryCombo
                || focused == &subcategoryEditor
                || focused == &taxonomyNoteEditor;
            if (selectedIt != activeSamples.end() && !editingInspector)
            {
                const auto& fresh = *selectedIt;
                const bool changed = fresh.name != selectedItem.name
                    || std::abs(fresh.bpm - selectedItem.bpm) > 1.0e-3f
                    || fresh.key != selectedItem.key
                    || fresh.instrumentType != selectedItem.instrumentType
                    || fresh.category != selectedItem.category
                    || fresh.subcategory != selectedItem.subcategory
                    || fresh.secondaryTags != selectedItem.secondaryTags
                    || std::abs(fresh.tagConfidence - selectedItem.tagConfidence) > 1.0e-4f
                    || fresh.tagSource != selectedItem.tagSource
                    || fresh.tagUserOverridden != selectedItem.tagUserOverridden
                    || fresh.winningEvidence != selectedItem.winningEvidence
                    || fresh.taxonomyVersion != selectedItem.taxonomyVersion
                    || fresh.embeddingStatus != selectedItem.embeddingStatus
                    || fresh.embeddingFailureCount != selectedItem.embeddingFailureCount;
                if (changed)
                    updateSelectionDetails(fresh);
            }
        }

        // Full resync (cheap append-only path in the common case — see
        // SampleCanvas::updateSamples)
        canvas.updateSamples(activeSamples);
        browser.updateSamples(activeSamples);

        // Dynamic category button syncing
        std::vector<std::string> cats;
        for (const auto& s : activeSamples) {
            // Cached rows can be visible and searchable before the current
            // processing pass flips isProcessed. Their persisted classifier
            // labels are still valid filter material, so don't hide the
            // category strip until a fresh DSP pass happens to complete.
            const bool hasCategoryEvidence = s.isProcessed
                || !s.category.empty()
                || (!s.instrumentType.empty() && s.instrumentType != "Unknown");
            if (!hasCategoryEvidence) continue;

            // Use the broad taxonomy category when available so the pills stay
            // stable (Drums/Bass/Vocals/...) instead of exploding into every
            // subcategory. Fall back to the legacy instrument label for rows
            // produced by older cache versions.
            std::string c = ClassificationPresentation::filterCategory(
                s.category, s.instrumentType);
            if (std::find(cats.begin(), cats.end(), c) == cats.end()) {
                cats.push_back(c);
            }
        }
        std::sort(cats.begin(), cats.end());

        bool categoriesChanged = false;
        if (cats.size() != currentCategories.size()) {
            categoriesChanged = true;
        } else {
            for (size_t i = 0; i < cats.size(); ++i) {
                if (cats[i] != currentCategories[i]) {
                    categoriesChanged = true;
                    break;
                }
            }
        }

        if (categoriesChanged) {
            currentCategories = cats;
            updateCategoryButtons();
        }
    }

    // Surfaces the model-load state explicitly rather than letting
    // similarity features look silently broken during/after startup -- see
    // docs/ASYNC_STARTUP.md. Uninitialized shouldn't be observable in
    // practice (initAsync() is called from the processor constructor before
    // the editor can exist), included for completeness.
    juce::String engineStatusPrefix;
    juce::Colour engineStatusColour = Tokens::mutedDim;
    juce::String engineStatusTooltip;
    const auto engineState = audioProcessor.getEngine().getEngineState();
    switch (engineState) {
        case EngineInitState::Uninitialized:
        case EngineInitState::Initializing:
            engineStatusPrefix = "Loading AI model... | ";
            engineStatusColour = Tokens::accentInteractive;
            engineStatusTooltip = "Loading the AI embedding model. Browsing and deterministic audio analysis remain available.";
            break;
        case EngineInitState::Degraded:
            engineStatusPrefix = "Similarity search unavailable (model failed to load) | ";
            engineStatusColour = Tokens::warningText;
            engineStatusTooltip = "The AI embedding model is unavailable. You can still browse, edit metadata, and use deterministic audio analysis.";
            break;
        case EngineInitState::Failed:
            engineStatusPrefix = "Engine unavailable | ";
            engineStatusColour = Tokens::danger;
            engineStatusTooltip = "The analysis engine is unavailable. Restart SLO after checking the model installation.";
            break;
        case EngineInitState::Ready:
            engineStatusColour = Tokens::success;
            engineStatusTooltip = "AI model ready. Similarity search and classifier evidence are available.";
            break;
    }

    // Sort Library progress -- polled rather than pushed, matching this
    // editor's existing timer-driven update pattern. See
    // docs/SORT_LIBRARY_BACKGROUND.md.
    auto sortProgress = audioProcessor.getEngine().getSortLibraryProgress();
    if (sortProgress.inProgress) {
        auto progressText = "Sorting " + juce::String(sortProgress.done) + "/"
            + juce::String(sortProgress.total) + " (click to cancel)";
        sortButton.setButtonText(progressText);
        sortLibraryTopButton.setButtonText(progressText);
    }

    bool canUndo = audioProcessor.getEngine().canUndoSort();
    undoSortTopButton.setEnabled(canUndo && !sortProgress.inProgress);
    undoSortTopButton.setColour(juce::TextButton::textColourOffId, canUndo ? Tokens::electricCyan : Tokens::mutedDim);

    const auto scanProgress = engine.getScanProgress();
    juce::String scanStatus;
    if (scanProgress.inProgress && scanProgress.total > 0)
    {
        scanStatus = "Analysing " + juce::String(scanProgress.done) + "/"
            + juce::String(scanProgress.total);
        if (scanProgress.failed > 0)
            scanStatus += " · " + juce::String(scanProgress.failed) + " failed";
    }
    else
    {
        scanStatus = engine.isBusy() ? "Finalising library" : "Ready";
        if (scanStatus == "Ready" && lastScanReceiptText.isNotEmpty())
            scanStatus += " — " + lastScanReceiptText;
    }
    const juce::String fullStatusMsg = engineStatusPrefix + scanStatus + " | DAW Sync: " + juce::String(dawBpm, 1) + " BPM [" +
                            (isDawPlaying ? "PLAYING" : "STOPPED") + "] | Map: " +
                            juce::String(static_cast<int>(lastKnownSampleCount)) + " samples";
    const juce::String statusMsg = getWidth() < 900
        ? engineStatusPrefix + scanStatus + " | "
            + juce::String(static_cast<int>(lastKnownSampleCount)) + " samples"
        : fullStatusMsg;

    statusLabel.setText(statusMsg, juce::dontSendNotification);
    statusLabel.setColour(juce::Label::textColourId, engineStatusColour);
    statusLabel.setTooltip(engineStatusTooltip + "\n" + fullStatusMsg);

    const bool scanVisualActive = scanProgress.inProgress && scanProgress.total > 0;
    if (scanVisualActive || scanProgressVisualActive)
        repaint();
    scanProgressVisualActive = scanVisualActive;

    // F-03 rescan-diff: fire once per completed run, on the true busyFlag
    // true->false edge (overlapping rescans merge into one run, matching the
    // engine's accumulated receipt semantics).
    if (wasScanInProgress && !scanVisualActive && !engine.isBusy())
    {
        const auto receipt = engine.getLastScanReceipt();
        lastScanReceiptText = formatScanReceipt(receipt);
        // Status line always carries the receipt; the modal is reserved for
        // runs worth interrupting: failures, skips, or bulk intake. A quiet
        // single-file retry should not pop a dialog.
        constexpr int kScanSummaryDialogThreshold = 50;
        if (receipt.failed > 0 || receipt.skippedNonAudio > 0
            || receipt.added + receipt.changed >= kScanSummaryDialogThreshold)
        {
            juce::AlertWindow::showMessageBoxAsync(
                (receipt.failed > 0) ? juce::MessageBoxIconType::WarningIcon
                                     : juce::MessageBoxIconType::InfoIcon,
                "Scan Complete", formatScanReceiptLong(receipt));
        }
    }
    else if (scanVisualActive)
    {
        lastScanReceiptText.clear();
    }
    wasScanInProgress = scanVisualActive || engine.isBusy();
}

void SmartSampleManagerAudioProcessorEditor::updateSelectionDetails(const SampleItem& item)
{
    bool wasSelected = hasSelection;
    selectedItem = item;
    hasSelection = true;

    // Show details if selection is newly active
    if (!wasSelected) {
        bpmLabel.setVisible(true);
        bpmEditor.setVisible(true);
        keyLabel.setVisible(true);
        keyEditor.setVisible(true);
        typeLabel.setVisible(true);
        typeCombo.setVisible(true);
        taxonomyLabel.setVisible(true);
        categoryCombo.setVisible(true);
        subcategoryEditor.setVisible(true);
        taxonomyStatusLabel.setVisible(true);
        suggestedTagsLabel.setVisible(true);
        // audioModelLabel visibility is decided per-selection below (F-02).
        taxonomyNoteLabel.setVisible(true);
        taxonomyNoteEditor.setVisible(true);
        saveTaxonomyButton.setVisible(true);
        resetTaxonomyButton.setVisible(true);
        writeAbletonXmpButton.setVisible(true);
        playButton.setVisible(true);
        stopButton.setVisible(true);
        waveformPreview.setVisible(true);
        saveButton.setVisible(true);
        namingLabel.setVisible(true);
        namingCombo.setVisible(true);
        sortButton.setVisible(true);
        metadataGroup.setVisible(true);
        inspectorSummaryLabel.setVisible(true);
        retryAnalysisButton.setVisible(item.embeddingStatus == EmbeddingStatus::FailedRetryable);
        retryAnalysisButton.setEnabled(true);
        retryAnalysisButton.setButtonText("RETRY AI");
        
        // Trigger sidebar content bounds recalculation
        resized();
    }

    // Selection can change while the inspector is already open. Keep the
    // contextual recovery action in sync without forcing a full sidebar
    // relayout on every ordinary metadata refresh.
    if (wasSelected) {
        const bool shouldShowRetry = item.embeddingStatus == EmbeddingStatus::FailedRetryable;
        if (retryAnalysisButton.isVisible() != shouldShowRetry) {
            retryAnalysisButton.setVisible(shouldShowRetry);
            retryAnalysisButton.setEnabled(true);
            retryAnalysisButton.setButtonText("RETRY AI");
            resized();
        }
    }

    // Truncate display name if too long
    juce::String displayName = item.name;
    if (displayName.length() > 25) {
        displayName = displayName.substring(0, 22) + "...";
    }

    nameVal.setJustificationType(juce::Justification::centredLeft);
    nameVal.setColour(juce::Label::textColourId, Tokens::foreground);
    nameVal.setText(displayName, juce::dontSendNotification);

    // Keep the important classifier state above the fold. The detailed
    // taxonomy status below remains the full diagnostic; this line is for
    // fast scanning while browsing a library.
    const float confidence = juce::jlimit(0.0f, 1.0f, item.tagConfidence);
    const int confidencePercent = static_cast<int>(std::round(confidence * 100.0f));
    const auto evidence = juce::String(ClassificationPresentation::evidenceLabel(
        item.tagSource, item.winningEvidence));
    const bool embeddingFailed = item.embeddingStatus == EmbeddingStatus::FailedRetryable
        || item.embeddingStatus == EmbeddingStatus::FailedPermanent;
    juce::String inspectorState;
    if (embeddingFailed)
        inspectorState = "AI ANALYSIS FAILED";
    else if (item.taxonomyVersion == 0 && item.category.empty() && item.subcategory.empty())
        inspectorState = "UNCLASSIFIED";
    else if (item.tagUserOverridden)
        inspectorState = "USER OVERRIDE";
    else if (item.category.empty() && item.subcategory.empty())
        inspectorState = "UNKNOWN";
    else if (confidence >= 0.75f)
        inspectorState = "HIGH CONFIDENCE";
    else if (confidence >= 0.5f)
        inspectorState = "REVIEWABLE";
    else
        inspectorState = "NEEDS REVIEW";

    const juce::String inspectorConfidenceText = embeddingFailed
        ? juce::String("unavailable")
        : item.taxonomyVersion == 0
        ? juce::String("pending")
        : juce::String(confidencePercent) + "%";
    inspectorSummaryBaseText = inspectorState + "  •  " + inspectorConfidenceText + " confidence  •  "
        + (evidence.isEmpty() ? juce::String("NO EVIDENCE") : evidence);
    inspectorSummaryBaseColour = embeddingFailed ? Tokens::danger
        : item.tagUserOverridden ? Tokens::accentInteractive
        : item.taxonomyVersion == 0 ? Tokens::mutedDim
        : confidence < 0.5f ? Tokens::danger
        : confidence >= 0.75f ? Tokens::success : Tokens::muted;
    updateSelectionFilterCue();
    inspectorSummaryLabel.setColour(juce::Label::textColourId,
        selectionHiddenByFilters ? Tokens::warningText : inspectorSummaryBaseColour);
    inspectorSummaryLabel.setTooltip(
        "Confidence: " + inspectorConfidenceText + " | Evidence: "
        + (evidence.isEmpty() ? juce::String("none") : evidence)
        + " | Taxonomy: "
        + juce::String(ClassificationPresentation::taxonomyVersionLabel(item.taxonomyVersion)));

    bpmEditor.setText(item.bpm > 0.0f
                          ? juce::String(static_cast<int>(std::round(item.bpm)))
                          : juce::String(),
                      juce::dontSendNotification);
    const bool oneShotKey = item.subcategory.find("Loop") == std::string::npos
        && item.subcategory.find("loop") == std::string::npos;
    keyEditor.setText(formatKeyForSampleName(juce::String(item.key), oneShotKey),
                      juce::dontSendNotification);
    waveformPreview.loadFile(juce::File(item.filePath));

    // Map instrument type string to combo box selection ID
    juce::String instType = item.instrumentType;
    instType = instType.toLowerCase();

    int selectedId = 10; // default "Other"
    if (instType.contains("kick")) selectedId = 1;
    else if (instType.contains("snare")) selectedId = 2;
    else if (instType.contains("hihat") || instType.contains("hat")) selectedId = 3;
    else if (instType.contains("clap")) selectedId = 4;
    else if (instType.contains("perc")) selectedId = 5;
    else if (instType.contains("bass")) selectedId = 6;
    else if (instType.contains("synth")) selectedId = 7;
    else if (instType.contains("loop")) selectedId = 8;
    else if (instType.contains("vocal")) selectedId = 9;

    typeCombo.setSelectedId(selectedId, juce::dontSendNotification);

    categoryCombo.setText(item.category, juce::dontSendNotification);
    subcategoryEditor.setText(item.subcategory, juce::dontSendNotification);
    // Notes are write-only correction context; never carry a previous sample's
    // note into a new selection or imply that it was persisted as sample data.
    taxonomyNoteEditor.clear();

    if (item.category.empty() && item.subcategory.empty()) {
        // B-007: distinguish "hasn't been scanned yet" from "was scanned and
        // genuinely doesn't fit any known category" -- these used to show the
        // identical "not yet classified" text, which silently hid every
        // correctly-detected Unknown/OOD result behind the same message a
        // never-scanned file shows. taxonomyVersion == 0 is the real signal
        // for "never classified under this taxonomy system"; if it's set,
        // classification DID run and genuinely produced no category (an
        // OOD-cleared result, see MlOverrideGate's "ml_ood" path) -- that's
        // not the same situation and must not read the same to the user.
        if (item.taxonomyVersion == 0) {
            taxonomyStatusLabel.setText(
                "not yet classified • "
                    + juce::String(ClassificationPresentation::evidenceLabel(
                        item.tagSource, item.winningEvidence))
                    + " • "
                    + juce::String(ClassificationPresentation::taxonomyVersionLabel(item.taxonomyVersion)),
                juce::dontSendNotification);
            taxonomyStatusLabel.setColour(juce::Label::textColourId, Tokens::mutedDim);
        } else {
            taxonomyStatusLabel.setText(
                "Unknown (doesn't match a known category) • "
                    + juce::String(ClassificationPresentation::evidenceLabel(
                        item.tagSource, item.winningEvidence))
                    + " • "
                    + juce::String(ClassificationPresentation::taxonomyVersionLabel(item.taxonomyVersion)),
                juce::dontSendNotification);
            taxonomyStatusLabel.setColour(juce::Label::textColourId, Tokens::danger);
        }
    } else if (item.tagUserOverridden) {
        taxonomyStatusLabel.setText(
            "user-set • "
                + juce::String(ClassificationPresentation::evidenceLabel(
                    item.tagSource, item.winningEvidence))
                + " • "
                + juce::String(ClassificationPresentation::taxonomyVersionLabel(item.taxonomyVersion)),
            juce::dontSendNotification);
    } else {
        // Confidence BANDING (SLO_PRODUCER_TAXONOMY_IMPLEMENTATION_PLAN_V1.md):
        // three graduated bands instead of a single "needs review or not"
        // threshold, so a producer can tell "pretty sure" apart from
        // "genuinely uncertain" rather than everything above 0.5 reading the
        // same. Below kNeedsReviewThreshold matches the pre-existing "don't
        // pretend certainty" design requirement -- the classification is
        // more likely to be wrong than right there, so it's still flagged
        // as NEEDS REVIEW, not just labeled "Low".
        constexpr float kNeedsReviewThreshold = 0.5f;
        constexpr float kHighConfidenceThreshold = 0.75f;
        juce::String confidenceText = juce::String(static_cast<int>(item.tagConfidence * 100.0f)) + "% confidence";
        juce::String band = (item.tagConfidence >= kHighConfidenceThreshold) ? "High"
                           : (item.tagConfidence >= kNeedsReviewThreshold) ? "Medium"
                                                                           : "Low";
        const juce::String confidenceSummary = item.tagConfidence < kNeedsReviewThreshold
            ? ("NEEDS REVIEW (" + band + ", " + confidenceText + ")")
            : (band + " (" + confidenceText + ")");
        const auto uncertainty = ClassificationPresentation::uncertaintyReason(
            item.tagSource, item.winningEvidence, item.tagConfidence);
        const juce::String uncertaintyText = uncertainty.empty()
            ? juce::String()
            : (" • why: " + juce::String(uncertainty));
        taxonomyStatusLabel.setText(
            confidenceSummary + " • "
                + juce::String(ClassificationPresentation::evidenceLabel(
                    item.tagSource, item.winningEvidence))
                + " • "
                + juce::String(ClassificationPresentation::taxonomyVersionLabel(item.taxonomyVersion))
                + uncertaintyText,
            juce::dontSendNotification);
        taxonomyStatusLabel.setColour(juce::Label::textColourId,
            item.tagConfidence < kNeedsReviewThreshold ? Tokens::danger
            : item.tagConfidence < kHighConfidenceThreshold ? Tokens::mutedDim
                                                             : Tokens::success);
    }

    auto suggestedTags = audioProcessor.getEngine().getPredictedTags(item.filePath);
    if (!suggestedTags.empty()) {
        juce::String tagList = "Suggested: ";
        for (size_t i = 0; i < suggestedTags.size(); ++i) {
            if (i > 0) tagList += ", ";
            tagList += juce::String(suggestedTags[i]);
        }
        suggestedTagsLabel.setText(tagList, juce::dontSendNotification);
    } else {
        suggestedTagsLabel.setText("", juce::dontSendNotification);
    }

    // F-02 split display: frozen audio-model view next to the fused shown
    // label. Read-only recompute (no fusion, no mutation); hidden when no
    // usable embedding is stored. The "differs" marker is the point: it
    // surfaces exactly the rows where filename/folder evidence overruled
    // (or agreed with) the acoustic model.
    const auto audioView = audioProcessor.getEngine().getAudioOnlyView(item.filePath);
    if (audioView.available) {
        juce::String audioText;
        if (audioView.isOod) {
            audioText = "Audio model: abstains (outside known domain)";
        } else if (audioView.unmapped) {
            audioText = "Audio model: " + juce::String(audioView.subcategory) + " (no taxonomy mapping)";
        } else {
            const juce::String audioLabel = juce::String(audioView.subcategory).isNotEmpty()
                ? juce::String(audioView.subcategory) : juce::String(audioView.category);
            audioText = "Audio model: " + audioLabel + " ("
                + juce::String(static_cast<int>(audioView.confidence * 100.0f)) + "%)";
        }
        const bool agrees = !audioView.isOod && !audioView.unmapped
            && audioView.subcategory == item.subcategory && audioView.category == item.category;
        bool differs = !agrees && !item.tagUserOverridden;
        if (differs)
            audioText += (item.category.empty() && item.subcategory.empty())
                ? " • shown: UNKNOWN" : " • differs from shown label";
        if (audioView.staleHead)
            audioText += " • head changed since classification";
        audioModelLabel.setText(audioText, juce::dontSendNotification);
        audioModelLabel.setColour(juce::Label::textColourId,
            differs ? Tokens::warningText : Tokens::mutedDim);
        audioModelLabel.setVisible(true);
    } else {
        audioModelLabel.setText("", juce::dontSendNotification);
        audioModelLabel.setVisible(false);
    }
}

void SmartSampleManagerAudioProcessorEditor::updateSelectionFilterCue()
{
    if (!hasSelection)
        return;

    const bool searchActive = searchField.getText().trim().isNotEmpty();
    const bool categoryActive = !filterButtons.isEmpty()
        && std::any_of(filterButtons.begin(), filterButtons.end(),
            [](const juce::TextButton* button) { return !button->getToggleState(); });
    const bool hidden = (searchActive || categoryActive)
        && !browser.isSampleVisible(juce::String(selectedItem.filePath));

    selectionHiddenByFilters = hidden;
    inspectorSummaryLabel.setText(selectionHiddenByFilters
        ? inspectorSummaryBaseText + "  •  HIDDEN BY FILTERS"
        : inspectorSummaryBaseText,
        juce::dontSendNotification);
    inspectorSummaryLabel.setColour(juce::Label::textColourId,
        selectionHiddenByFilters ? Tokens::warningText : inspectorSummaryBaseColour);
    inspectorSummaryLabel.setTooltip(selectionHiddenByFilters
        ? "The selected sample is outside the current search/category filter; clear filters to reveal its row"
        : "Classifier confidence and winning evidence for the selected sample");
}

void SmartSampleManagerAudioProcessorEditor::saveSidebarMetadata()
{
    if (!hasSelection) return;

    float bpm = bpmEditor.getText().getFloatValue();
    std::string key = keyEditor.getText().toStdString();
    std::string instrumentType = typeCombo.getText().toStdString();

    // Trigger asynchronous background tag writing
    audioProcessor.getEngine().updateMetadataAsync(selectedItem.filePath, bpm, key, instrumentType);

    // Show user-friendly visual feedback
    saveButton.setButtonText("SAVED!");
    juce::Component::SafePointer<SmartSampleManagerAudioProcessorEditor> safeThis(this);
    juce::Timer::callAfterDelay(1500, [safeThis]() {
        if (safeThis == nullptr) return;
        safeThis->saveButton.setButtonText("WRITE TO FILE");
    });
}

void SmartSampleManagerAudioProcessorEditor::openFolderScanner()
{
    auto& savedProps = AppSettings::getInstance().getProps();
    auto lastFolder = savedProps.getValue("lastScanFolder");
    juce::File startingDir = (lastFolder.isNotEmpty() && juce::File(lastFolder).isDirectory())
                                  ? juce::File(lastFolder)
                                  : juce::File::getSpecialLocation(juce::File::userHomeDirectory);

    fileChooser = std::make_unique<juce::FileChooser>(
        "Select a Sample Folder to Scan...",
        startingDir,
        "*"
    );

    juce::Component::SafePointer<SmartSampleManagerAudioProcessorEditor> safeThis(this);
    fileChooser->launchAsync(juce::FileBrowserComponent::openMode | juce::FileBrowserComponent::canSelectDirectories,
        [safeThis](const juce::FileChooser& fc) {
            if (safeThis == nullptr) return;
            juce::File result = fc.getResult();
            if (result.exists()) {
                safeThis->audioProcessor.getEngine().addPathToQueue(result.getFullPathName().toStdString());
                auto& props = AppSettings::getInstance().getProps();
                props.setValue("lastScanFolder", result.getFullPathName());
                props.saveIfNeeded();
            }
        }
    );
}

void SmartSampleManagerAudioProcessorEditor::showDuplicatesReport()
{
    auto exactGroups = audioProcessor.getEngine().findDuplicateGroups();
    auto nearGroups = audioProcessor.getEngine().findNearDuplicates(0.98f);

    if (exactGroups.empty() && nearGroups.empty()) {
        juce::AlertWindow::showMessageBoxAsync(juce::MessageBoxIconType::InfoIcon,
            "No Duplicates Found", "No exact or near-duplicate samples were found in the current library.");
        return;
    }

    int totalDuplicateFiles = 0;
    std::vector<ResultsPanel::Row> rows;

    // 1. Render exact duplicates
    if (!exactGroups.empty()) {
        for (size_t g = 0; g < exactGroups.size(); ++g) {
            const auto& group = exactGroups[g];
            ResultsPanel::Row header;
            header.primaryText = "[EXACT COPY] " + juce::String(group.items.size()) + " copies of same audio";
            header.secondaryText = "Group " + juce::String(static_cast<int>(g) + 1);
            rows.push_back(header);

            for (const auto& item : group.items) {
                ResultsPanel::Row row;
                row.primaryText = item.name;
                row.secondaryText = item.filePath;
                row.filePath = item.filePath;
                rows.push_back(row);
            }
            totalDuplicateFiles += static_cast<int>(group.items.size());
        }
    }

    // 2. Render near-duplicates
    if (!nearGroups.empty()) {
        for (size_t g = 0; g < nearGroups.size(); ++g) {
            const auto& group = nearGroups[g];
            ResultsPanel::Row header;
            header.primaryText = "[NEAR DUPLICATE] " + juce::String(group.items.size()) + " variants (similarity > 98%)";
            header.secondaryText = "Group " + juce::String(static_cast<int>(g) + 1);
            rows.push_back(header);

            for (const auto& item : group.items) {
                ResultsPanel::Row row;
                row.primaryText = item.name;
                row.secondaryText = item.filePath;
                row.filePath = item.filePath;
                rows.push_back(row);
            }
            totalDuplicateFiles += static_cast<int>(group.items.size());
        }
    }

    // Add a clear notice instructing the user about safety & non-destructiveness
    ResultsPanel::Row safetyNotice;
    safetyNotice.primaryText = "WARNING: Deleting duplicate files must be done manually.";
    safetyNotice.secondaryText = "SLO does not automate deletion to prevent accidental loss of project assets.";
    safetyNotice.filePath = ""; // Not selectable
    rows.insert(rows.begin(), safetyNotice);

    showResultsPanel("Duplicates Report (" + juce::String(totalDuplicateFiles) + " files)", rows);
}

void SmartSampleManagerAudioProcessorEditor::performSortLibrary()
{
    showSortPreview();
}

void SmartSampleManagerAudioProcessorEditor::showSortPreview()
{
    int namingStyle = namingCombo.getSelectedId();
    auto preview = audioProcessor.getEngine().previewSortLibrary(namingStyle, true);
    if (preview.totalCount == 0) {
        juce::AlertWindow::showMessageBoxAsync(
            juce::MessageBoxIconType::InfoIcon, "Sort Library",
            "No samples found in the library to sort. Scan a folder or drag in audio files first.");
        return;
    }
    sortPreviewPanel.setPreview(preview, namingStyle);
    sortPreviewPanel.setVisible(true);
    sortPreviewPanel.toFront(true);
    sortPreviewPanel.grabKeyboardFocus();
}

void SmartSampleManagerAudioProcessorEditor::hideSortPreview()
{
    sortPreviewPanel.setVisible(false);
}

void SmartSampleManagerAudioProcessorEditor::performUndoSort()
{
    if (!audioProcessor.getEngine().canUndoSort()) {
        juce::AlertWindow::showMessageBoxAsync(
            juce::MessageBoxIconType::InfoIcon, "Undo Sort",
            "No previous sort journal found to undo.");
        return;
    }

    juce::Component::SafePointer<SmartSampleManagerAudioProcessorEditor> safeThis(this);
    juce::AlertWindow::showOkCancelBox(
        juce::MessageBoxIconType::QuestionIcon, "Undo Last Sort",
        "This will restore sorted and renamed sample files back to their original locations and names based on the sort journal.\n\nContinue with Undo?",
        "Undo Sort", "Cancel", safeThis.getComponent(),
        juce::ModalCallbackFunction::create([safeThis](int result) {
            if (result != 1 || safeThis == nullptr) return;

            safeThis->undoSortTopButton.setEnabled(false);
            safeThis->undoSortTopButton.setButtonText("REVERTING...");

            safeThis->audioProcessor.getEngine().undoLastSortAsync([safeThis](SampleManagerEngine::UndoSortResult res) {
                if (safeThis == nullptr) return;
                safeThis->undoSortTopButton.setButtonText("UNDO SORT");
                safeThis->undoSortTopButton.setEnabled(safeThis->audioProcessor.getEngine().canUndoSort());

                juce::String message;
                if (res.success) {
                    message = "Successfully restored " + juce::String(res.revertedCount) + " file(s) to original paths.";
                } else {
                    message = "Undo completed with warnings: " + juce::String(res.revertedCount) + " file(s) restored, "
                        + juce::String(res.failedCount) + " failed.\n" + juce::String(res.errorMessage);
                }
                juce::AlertWindow::showMessageBoxAsync(
                    res.success ? juce::MessageBoxIconType::InfoIcon : juce::MessageBoxIconType::WarningIcon,
                    "Undo Sort", message);
            });
        }));
}

void SmartSampleManagerAudioProcessorEditor::startSortLibrary(bool copyInsteadOfMove)
{
    if (!copyInsteadOfMove) {
        juce::Component::SafePointer<SmartSampleManagerAudioProcessorEditor> safeThis(this);
        juce::AlertWindow::showOkCancelBox(
            juce::MessageBoxIconType::WarningIcon, "Move Files",
            "Moving files relocates them permanently on disk (SLO can restore them using Undo Last Sort).\n\nContinue with Move instead of Copy?",
            "Move Files", "Cancel", safeThis.getComponent(),
            juce::ModalCallbackFunction::create([safeThis](int confirmResult) {
                if (confirmResult == 1 && safeThis != nullptr) {
                    safeThis->doStartSortLibrary(false);
                }
            }));
        return;
    }

    doStartSortLibrary(true);
}

void SmartSampleManagerAudioProcessorEditor::doStartSortLibrary(bool copyInsteadOfMove)
{
    int namingStyle = namingCombo.getSelectedId();
    sortButton.setButtonText("Cancel Sort");
    sortButton.onClick = [this]() { audioProcessor.getEngine().cancelSortLibrary(); };
    sortLibraryTopButton.setButtonText("Cancel Sort");
    sortLibraryTopButton.onClick = [this]() { audioProcessor.getEngine().cancelSortLibrary(); };

    // SafePointer: this callback crosses a real async boundary (delivered
    // via MessageManager::callAsync from a background thread, potentially
    // long after a large sort starts -- see docs/SORT_LIBRARY_BACKGROUND.md),
    // so a bare [this] would be unsafe if the editor is closed before the
    // sort finishes. Same reasoning as the searchField/saveButton fixes
    // above.
    juce::Component::SafePointer<SmartSampleManagerAudioProcessorEditor> safeThis(this);
    audioProcessor.getEngine().reorganizeSamplesAsync(namingStyle, copyInsteadOfMove,
        [safeThis, copyInsteadOfMove](int moved, int failed, bool cancelled) {
            if (safeThis == nullptr) return;
            safeThis->sortButton.setButtonText(cancelled ? "CANCELLED" : "SORTED!");
            safeThis->sortButton.onClick = [safeThis]() { if (safeThis != nullptr) safeThis->performSortLibrary(); };
            safeThis->sortLibraryTopButton.setButtonText(cancelled ? "CANCELLED" : "SORTED!");
            safeThis->sortLibraryTopButton.onClick = [safeThis]() { if (safeThis != nullptr) safeThis->performSortLibrary(); };

            if (failed > 0 || cancelled) {
                const char* pastTense = copyInsteadOfMove ? "copied" : "moved";
                const char* infinitive = copyInsteadOfMove ? "copy" : "move";
                juce::String message = juce::String(moved) + " file(s) " + pastTense + " successfully.";
                if (failed > 0) message += " " + juce::String(failed) + " file(s) failed to " + infinitive
                    + " (left in their original location -- check disk space/permissions).";
                if (cancelled) message += " Operation was cancelled before finishing the rest of the library.";
                juce::AlertWindow::showMessageBoxAsync(
                    failed > 0 ? juce::MessageBoxIconType::WarningIcon : juce::MessageBoxIconType::InfoIcon,
                    "Sort Library", message);
            }

            juce::Timer::callAfterDelay(1500, [safeThis]() {
                if (safeThis == nullptr) return;
                safeThis->sortButton.setButtonText("SORT LIBRARY");
                safeThis->sortLibraryTopButton.setButtonText("SORT / RENAME");
            });
        });
}

void SmartSampleManagerAudioProcessorEditor::performRemoveMissingFiles()
{
    int removed = audioProcessor.getEngine().pruneMissingFiles();
    const int unavailable = audioProcessor.getEngine().getLastPruneUnavailableStorageCount();
    juce::String message;
    if (removed == 0)
        message = unavailable == 0
            ? "Every sample in the library still has its file on disk -- nothing to remove."
            : "No samples were removed from the library.";
    else
        message = juce::String(removed) + " sample" + (removed == 1 ? "" : "s")
            + " removed from the library (file no longer found on disk). "
              "Nothing was deleted from disk -- this only cleans up the library's own list.";
    if (unavailable > 0) {
        message += " " + juce::String(unavailable) + " sample"
            + (unavailable == 1 ? " was" : "s were")
            + " kept because the external drive is not currently connected.";
    }
    juce::AlertWindow::showMessageBoxAsync(
        (removed == 0 && unavailable == 0) ? juce::MessageBoxIconType::InfoIcon
                                           : juce::MessageBoxIconType::WarningIcon,
        "Remove Missing Files", message);
}

void SmartSampleManagerAudioProcessorEditor::showSimilarSamplesReport()
{
    if (!hasSelection) {
        juce::AlertWindow::showMessageBoxAsync(juce::MessageBoxIconType::InfoIcon,
            "Find Similar", "Select a sample on the canvas first.");
        return;
    }

    auto results = audioProcessor.getEngine().findSimilarSamples(selectedItem.filePath, 15);
    if (results.empty()) {
        juce::AlertWindow::showMessageBoxAsync(juce::MessageBoxIconType::InfoIcon,
            "Find Similar", "No similar samples found yet -- the library may still be scanning, "
            "or this is the only sample in it.");
        return;
    }

    // In-app results overlay instead of a native AlertWindow -- this was the
    // premier feature the UX audit flagged as costing MORE clicks than
    // normal browsing (read a name in a system alert, close it, manually
    // relocate the sample). Clicking a row now selects that sample directly,
    // via the same updateSelectionDetails() path canvas clicks use, so
    // PLAY/drag/tag-edit all work immediately without leaving the panel.
    // The refinement strip keeps the source context visible while routing
    // each deliberate adjustment through the engine's findSimilarRefined()
    // contract. It is unavailable for reference-file searches because those
    // are not selected library samples.
    std::vector<ResultsPanel::Row> rows;
    for (const auto& r : results) {
        ResultsPanel::Row row;
        row.primaryText = r.name;
        row.secondaryText = r.instrumentType.empty() ? juce::String("similar sound")
                                                       : juce::String(r.instrumentType);
        row.filePath = r.filePath;
        rows.push_back(row);
    }

    resultsPanel.silentlyResetRefinementSliders();
    resultsPanel.setRefinementVisible(true);
    resultsPanel.setRefinementChangedCallback([this](float brightness, float punchiness, float noise) {
        if (!hasSelection) return;
        SampleManagerEngine::TimbreRefinement ref;
        ref.brightnessShift = brightness;
        ref.punchShift = punchiness;
        ref.noiseShift = noise;
        auto refined = audioProcessor.getEngine().findSimilarRefined(selectedItem.filePath, ref, 15);
        std::vector<ResultsPanel::Row> updatedRows;
        for (const auto& r : refined) {
            ResultsPanel::Row row;
            row.primaryText = r.name;
            row.secondaryText = r.instrumentType.empty() ? juce::String("similar sound")
                                                           : juce::String(r.instrumentType);
            row.filePath = r.filePath;
            updatedRows.push_back(row);
        }
        resultsPanel.setContent("Similar to \"" + juce::String(selectedItem.name) + "\" (" + juce::String(updatedRows.size()) + ")", updatedRows);
        highlightSimilarOnMap(refined);
    });

    showResultsPanel("Similar to \"" + juce::String(selectedItem.name) + "\" (" + juce::String(results.size()) + ")", rows);
    highlightSimilarOnMap(results);
}

void SmartSampleManagerAudioProcessorEditor::showResultsPanel(const juce::String& title, const std::vector<ResultsPanel::Row>& rows)
{
    // Any new overlay invalidates whatever similarity neighbourhood the map was
    // showing. Similarity-producing callers re-arm it immediately afterwards via
    // highlightSimilarOnMap(); Favorites/History/Duplicates deliberately don't,
    // because those aren't similarity results and lighting the map up for them
    // would be a lie.
    canvas.clearSimilarSamples();

    resultsPanel.setContent(title, rows);
    resultsPanel.setVisible(true);
    resultsPanel.toFront(false);
    resultsPanel.grabKeyboardFocus();
}

void SmartSampleManagerAudioProcessorEditor::hideResultsPanel()
{
    resultsPanel.setVisible(false);
    resultsPanel.setRefinementVisible(false);
    canvas.clearSimilarSamples();
}

void SmartSampleManagerAudioProcessorEditor::highlightSimilarOnMap(const std::vector<SampleItem>& results)
{
    // Hand the map the engine's ranking as-is. The map draws those library
    // samples with a rank-weighted discovery emphasis at their real UMAP
    // positions -- it never moves a point, invents one, or draws a boundary.
    std::vector<std::string> paths;
    paths.reserve(results.size());
    for (const auto& r : results) paths.push_back(r.filePath);
    canvas.setSimilarSamples(paths);
}

void SmartSampleManagerAudioProcessorEditor::showReferenceSearchDialog()
{
    fileChooser = std::make_unique<juce::FileChooser>(
        "Select a Reference Audio File...",
        juce::File::getSpecialLocation(juce::File::userHomeDirectory),
        "*.wav;*.mp3;*.aif;*.aiff;*.flac;*.ogg"
    );

    juce::Component::SafePointer<SmartSampleManagerAudioProcessorEditor> safeThis(this);
    fileChooser->launchAsync(juce::FileBrowserComponent::openMode | juce::FileBrowserComponent::canSelectFiles,
        [safeThis](const juce::FileChooser& fc) {
            if (safeThis == nullptr) return;
            juce::File result = fc.getResult();
            if (result.exists()) {
                auto results = safeThis->audioProcessor.getEngine().findSimilarToReference(result.getFullPathName().toStdString(), 15);
                if (results.empty()) {
                    juce::AlertWindow::showMessageBoxAsync(juce::MessageBoxIconType::InfoIcon,
                        "Reference Search", "No similar samples found for this reference file.");
                    return;
                }

                std::vector<ResultsPanel::Row> rows;
                for (const auto& r : results) {
                    ResultsPanel::Row row;
                    row.primaryText = r.name;
                    row.secondaryText = r.instrumentType.empty() ? juce::String("similar sound")
                                                                   : juce::String(r.instrumentType);
                    row.filePath = r.filePath;
                    rows.push_back(row);
                }

                safeThis->resultsPanel.silentlyResetRefinementSliders();
                safeThis->resultsPanel.setRefinementVisible(false); // Refinement is only for selected DB samples
                safeThis->showResultsPanel("Similar to Reference: \"" + result.getFileName() + "\"", rows);
                // The reference file is external and has no UMAP coordinate, so
                // nothing is plotted for it -- only the library neighbourhood it
                // matched lights up. Inventing a position for it would be a
                // fabricated spatial claim.
                safeThis->highlightSimilarOnMap(results);
            }
        }
    );
}

void SmartSampleManagerAudioProcessorEditor::showReviewQueue(bool unknownOnly)
{
    constexpr float kReviewThreshold = 0.5f;
    const auto samples = audioProcessor.getEngine().getSamples();
    std::vector<SampleItem> reviewItems;
    reviewItems.reserve(samples.size());

    for (const auto& item : samples)
    {
        // User overrides are deliberate decisions and should not be put back
        // into the queue. Taxonomy version zero means classification has not
        // run yet, so it is a pending scan rather than a review decision.
        const bool embeddingFailed = item.embeddingStatus == EmbeddingStatus::FailedRetryable
            || item.embeddingStatus == EmbeddingStatus::FailedPermanent;
        if (item.tagUserOverridden || (item.taxonomyVersion == 0 && !embeddingFailed))
            continue;

        // An explicit ML abstention (ml_ood) is unknown even when legacy
        // instrument metadata is present; keep the presentation pinned to
        // ClassificationPresentation::isMlOod so the queue can never show a
        // stale label for an abstained row.
        const bool oodAbstention = ClassificationPresentation::isMlOod(item.tagSource);
        const bool classifiedUnknown = (item.category.empty() && item.subcategory.empty()) || oodAbstention;
        const bool lowConfidence = item.tagConfidence < kReviewThreshold && item.taxonomyVersion > 0;
        if (unknownOnly)
        {
            if (embeddingFailed || classifiedUnknown)
                reviewItems.push_back(item);
        }
        else if (embeddingFailed || classifiedUnknown || lowConfidence)
        {
            reviewItems.push_back(item);
        }
    }

    std::sort(reviewItems.begin(), reviewItems.end(), [](const SampleItem& lhs, const SampleItem& rhs) {
        const auto isUnknown = [](const SampleItem& item) {
            return (item.category.empty() && item.subcategory.empty())
                || ClassificationPresentation::isMlOod(item.tagSource);
        };
        const bool lhsUnknown = isUnknown(lhs);
        const bool rhsUnknown = isUnknown(rhs);
        if (lhsUnknown != rhsUnknown)
            return lhsUnknown > rhsUnknown;
        if (std::abs(lhs.tagConfidence - rhs.tagConfidence) > 1.0e-6f)
            return lhs.tagConfidence < rhs.tagConfidence;
        return lhs.filePath < rhs.filePath;
    });

    std::vector<ResultsPanel::Row> rows;
    rows.reserve(reviewItems.size());
    for (const auto& item : reviewItems)
    {
        const float confidence = juce::jlimit(0.0f, 1.0f, item.tagConfidence);
        const auto evidence = juce::String(ClassificationPresentation::evidenceLabel(
            item.tagSource, item.winningEvidence));
        const bool unknown = (item.category.empty() && item.subcategory.empty())
            || ClassificationPresentation::isMlOod(item.tagSource);
        const bool embeddingFailed = item.embeddingStatus == EmbeddingStatus::FailedRetryable
            || item.embeddingStatus == EmbeddingStatus::FailedPermanent;

        ResultsPanel::Row row;
        row.primaryText = juce::File(item.filePath).getFileName();
        row.secondaryText = (embeddingFailed ? juce::String("AI ANALYSIS FAILED")
                             : unknown ? juce::String("UNKNOWN")
                                     : juce::String(static_cast<int>(std::round(confidence * 100.0f))) + "% confidence")
            + "  •  " + (evidence.isEmpty() ? juce::String("no evidence") : evidence);
        if (embeddingFailed && item.embeddingFailureCount > 0)
            row.secondaryText += "  •  attempt " + juce::String(item.embeddingFailureCount);
        if (!unknown && !embeddingFailed)
        {
            // Actionable reason (weak/mixed/name-only) for low-confidence rows.
            // Unknown rows already carry the OOD abstention evidence chip, so
            // repeating the domain reason here would be noise.
            const auto reason = juce::String(ClassificationPresentation::uncertaintyReason(
                item.tagSource, item.winningEvidence, confidence));
            if (reason.isNotEmpty())
                row.secondaryText += "  •  " + reason;
        }
        if (!item.instrumentType.empty())
            row.secondaryText += "  •  " + juce::String(item.instrumentType);
        row.filePath = item.filePath;
        rows.push_back(std::move(row));
    }

    resultsPanel.silentlyResetRefinementSliders();
    resultsPanel.setRefinementVisible(false);
    resultsPanel.setAspectControlsVisible(false);
    showResultsPanel((unknownOnly ? "Unknown Queue (" : "Review Queue (") + juce::String(rows.size()) + ")", rows);
}

void SmartSampleManagerAudioProcessorEditor::showUnknownQueue()
{
    showReviewQueue(true);
}

void SmartSampleManagerAudioProcessorEditor::exportDiagnosticsBundle()
{
    // First save-mode FileChooser in the codebase: the bundle is support
    // material the user sends us, so it must go where they choose, as .json.
    // Reuses the shared fileChooser member like the three import choosers.
    fileChooser = std::make_unique<juce::FileChooser>(
        "Export Diagnostics Bundle...",
        juce::File::getSpecialLocation(juce::File::userHomeDirectory),
        "*.json");

    juce::Component::SafePointer<SmartSampleManagerAudioProcessorEditor> safeThis(this);
    fileChooser->launchAsync(
        juce::FileBrowserComponent::saveMode | juce::FileBrowserComponent::canSelectFiles,
        [safeThis](const juce::FileChooser& fc) {
            if (safeThis == nullptr) return;
            auto result = fc.getResult();
            if (result.getFullPathName().isEmpty()) return; // user cancelled
            if (result.getFileExtension().isEmpty())
                result = result.withFileExtension("json");
            const std::string bundle =
                safeThis->audioProcessor.getEngine().buildDiagnosticsBundle();
            if (!result.replaceWithText(bundle)) {
                juce::AlertWindow::showMessageBoxAsync(
                    juce::MessageBoxIconType::WarningIcon,
                    "Export Diagnostics",
                    "Could not write the bundle to:\n" + result.getFullPathName());
                return;
            }
            juce::AlertWindow::showMessageBoxAsync(
                juce::MessageBoxIconType::InfoIcon,
                "Export Diagnostics",
                "Diagnostics bundle saved to:\n" + result.getFullPathName()
                    + "\n\nSend this file with support requests -- it contains "
                      "versions, thresholds, scan receipt, evidence splits and "
                      "a recent log tail. No audio is included.");
        });
}

void SmartSampleManagerAudioProcessorEditor::showEvidencePacketDialog()
{
    fileChooser = std::make_unique<juce::FileChooser>(
        "Select AI Evidence Packet...",
        juce::File::getSpecialLocation(juce::File::userHomeDirectory),
        "*.json");

    juce::Component::SafePointer<SmartSampleManagerAudioProcessorEditor> safeThis(this);
    fileChooser->launchAsync(
        juce::FileBrowserComponent::openMode | juce::FileBrowserComponent::canSelectFiles,
        [safeThis](const juce::FileChooser& fc) {
            if (safeThis == nullptr) return;
            const auto result = fc.getResult();
            if (!result.existsAsFile()) return;

            // The parser enforces the packet's read-only safety contract,
            // absolute unique paths, bounded arrays, and review-only states.
            // Keep the UI bound smaller than the parser's hard limit so a
            // malformed/huge-but-valid packet cannot freeze the editor.
            const auto parsed = SloLabelFreeEvidence::parse(result, 50000, 1024);
            if (!parsed.success) {
                juce::AlertWindow::showMessageBoxAsync(
                    juce::MessageBoxIconType::WarningIcon,
                    "Import AI Evidence",
                    "Evidence packet rejected:\n" + parsed.error);
                return;
            }

            constexpr int kDisplayLimit = 2000;
            const int displayCount = juce::jmin(kDisplayLimit, parsed.packet.rows.size());
            std::vector<ResultsPanel::Row> rows;
            rows.reserve(static_cast<size_t>(displayCount));
            const auto boundedDisplayText = [](const juce::String& value, int maxLength = 160) {
                return value.substring(0, maxLength);
            };

            // Put the rows most useful for calibration first: explicit review
            // or unknown-domain decisions, OOD downgrades, then the lowest
            // agreement/highest novelty evidence. This is still only a view
            // ordering; the packet remains immutable and no label is created.
            std::vector<const SloLabelFreeEvidence::Row*> orderedRows;
            orderedRows.reserve(static_cast<size_t>(parsed.packet.rows.size()));
            for (const auto& evidence : parsed.packet.rows)
                orderedRows.push_back(&evidence);
            const auto reviewPriority = [](const SloLabelFreeEvidence::Row& evidence) {
                int priority = 0;
                if (evidence.hasFusionDecision
                    && (evidence.fusionDecision == "review"
                        || evidence.fusionDecision == "unknown_domain"))
                    priority += 4;
                if (evidence.oodOverride) priority += 2;
                if (evidence.hasNameCandidate) priority += 1;
                return priority;
            };
            std::sort(orderedRows.begin(), orderedRows.end(),
                [&reviewPriority](const auto* lhs, const auto* rhs) {
                    const int lhsPriority = reviewPriority(*lhs);
                    const int rhsPriority = reviewPriority(*rhs);
                    if (lhsPriority != rhsPriority) return lhsPriority > rhsPriority;
                    if (std::abs(lhs->modelAgreement - rhs->modelAgreement) > 1.0e-6)
                        return lhs->modelAgreement < rhs->modelAgreement;
                    if (lhs->hasOodNovelty && rhs->hasOodNovelty
                        && std::abs(lhs->oodNoveltyScore - rhs->oodNoveltyScore) > 1.0e-6)
                        return lhs->oodNoveltyScore > rhs->oodNoveltyScore;
                    return lhs->path < rhs->path;
                });

            for (int index = 0; index < displayCount; ++index) {
                const auto& evidence = *orderedRows[static_cast<size_t>(index)];
                ResultsPanel::Row row;
                const juce::File evidenceFile(evidence.path);
                row.primaryText = evidenceFile.getFileName().isNotEmpty()
                    ? boundedDisplayText(evidenceFile.getFileName(), 255)
                    : boundedDisplayText(evidence.path, 255);

                juce::StringArray details;
                details.add("Review: " + evidence.reviewState);
                details.add("Agreement: " + juce::String(evidence.modelAgreement, 2));
                if (evidence.hasOodNovelty)
                    details.add("Novelty: " + juce::String(evidence.oodNoveltyScore, 2));
                if (evidence.hasDomainRoute && evidence.domainSuggestion.isNotEmpty())
                    details.add("Domain: " + boundedDisplayText(evidence.domainSuggestion));
                if (evidence.ensembleSuggestion.isNotEmpty())
                    details.add("Ensemble: " + boundedDisplayText(evidence.ensembleSuggestion));
                if (evidence.hasSpecialist && evidence.specialistSuggestion.isNotEmpty())
                    details.add("Specialist: " + boundedDisplayText(evidence.specialistSuggestion));
                if (evidence.hasFusionDecision) {
                    auto fusion = "Fusion: " + evidence.fusionDecision;
                    if (evidence.fusionCandidateLabel.isNotEmpty())
                        fusion += " → " + boundedDisplayText(evidence.fusionCandidateLabel);
                    details.add(fusion);
                }
                if (evidence.hasNameCandidate)
                    details.add("Name candidate: " + boundedDisplayText(evidence.candidateFilename, 255));
                if (evidence.hasRetrievalEvidence && evidence.retrievalCandidateLabel.isNotEmpty())
                    details.add("Retrieval: " + boundedDisplayText(evidence.retrievalCandidateLabel));
                if (evidence.hasClusterDiscovery)
                    details.add("Cluster: " + juce::String(evidence.clusterDiscovery.clusterId)
                                + " (" + juce::String(evidence.clusterDiscovery.clusterSize) + ")");
                if (evidence.hasFftEvidence) {
                    juce::String fft = "FFT: ";
                    fft += evidence.fftCandidateLanes.isEmpty()
                        ? "measured"
                        : evidence.fftCandidateLanes.joinIntoString(", ");
                    fft += "  flux " + juce::String(evidence.fftFluxPeakRate, 1) + "/s";
                    details.add(boundedDisplayText(fft));
                }
                row.secondaryText = details.joinIntoString("  •  ");
                row.filePath = evidence.path;
                rows.push_back(std::move(row));
            }

            auto title = "AI Evidence: " + juce::String(parsed.packet.nRows) + " review rows";
            if (displayCount < parsed.packet.nRows)
                title += " (showing first " + juce::String(displayCount) + ")";
            if (parsed.packet.methodVersion.isNotEmpty())
                title += " · " + parsed.packet.methodVersion;

            safeThis->resultsPanel.silentlyResetRefinementSliders();
            safeThis->resultsPanel.setRefinementVisible(false);
            safeThis->resultsPanel.setAspectControlsVisible(false);
            safeThis->showResultsPanel(title, rows);
        });
}

void SmartSampleManagerAudioProcessorEditor::showSmartCollectionsPanel()
{
    smartCollectionsPanel.refreshAndShow();
    smartCollectionsPanel.toFront(false);
    smartCollectionsPanel.grabKeyboardFocus();
}

void SmartSampleManagerAudioProcessorEditor::hideSmartCollectionsPanel()
{
    smartCollectionsPanel.setVisible(false);
}

void SmartSampleManagerAudioProcessorEditor::toggleFavoritesView()
{
    showFavoritesOverlay = !showFavoritesOverlay;
    showHistoryOverlay = false; // Hide other overlays
    
    // Toggle active state visualization on buttons
    favoritesTabButton.setToggleState(showFavoritesOverlay, juce::dontSendNotification);
    historyTabButton.setToggleState(false, juce::dontSendNotification);

    if (showFavoritesOverlay) {
        auto favPaths = audioProcessor.getEngine().getFavorites();
        std::vector<ResultsPanel::Row> rows;
        
        for (const auto& path : favPaths) {
            juce::File f(path);
            ResultsPanel::Row r;
            r.primaryText = f.getFileName();
            r.secondaryText = f.getFullPathName();
            r.filePath = path;
            rows.push_back(r);
        }
        
        resultsPanel.silentlyResetRefinementSliders();
        resultsPanel.setRefinementVisible(false);
        showResultsPanel("Favorites (" + juce::String(rows.size()) + ")", rows);
    } else {
        hideResultsPanel();
    }
}

void SmartSampleManagerAudioProcessorEditor::toggleHistoryView()
{
    showHistoryOverlay = !showHistoryOverlay;
    showFavoritesOverlay = false; // Hide other overlays
    
    // Toggle active state visualization on buttons
    historyTabButton.setToggleState(showHistoryOverlay, juce::dontSendNotification);
    favoritesTabButton.setToggleState(false, juce::dontSendNotification);

    if (showHistoryOverlay) {
        auto historyEntries = audioProcessor.getEngine().getRecentPreviews(30);
        std::vector<ResultsPanel::Row> rows;
        
        for (const auto& entry : historyEntries) {
            juce::File f(entry.filePath);
            ResultsPanel::Row r;
            r.primaryText = f.getFileName();
            // Format preview time or display simple path details
            r.secondaryText = f.getFullPathName();
            r.filePath = entry.filePath;
            rows.push_back(r);
        }
        
        resultsPanel.silentlyResetRefinementSliders();
        resultsPanel.setRefinementVisible(false);
        showResultsPanel("Recently Auditioned (" + juce::String(rows.size()) + ")", rows);
    } else {
        hideResultsPanel();
    }
}
void SmartSampleManagerAudioProcessorEditor::selectSampleByPath(const juce::String& filePath)
{
    for (const auto& item : audioProcessor.getEngine().getSamples()) {
        if (item.filePath == filePath.toStdString()) {
            updateSelectionDetails(item);
            browser.selectSampleByPath(filePath.toStdString());
            canvas.selectSampleByPath(filePath.toStdString());
            break;
        }
    }
}

void SmartSampleManagerAudioProcessorEditor::updateCanvasFilters()
{
    std::vector<std::string> activeCategories;
    for (auto* btn : filterButtons) {
        if (btn->getToggleState()) {
            activeCategories.push_back(btn->getButtonText().toStdString());
        }
    }
    // The explicit ALL pill resets every category on. If category pills exist
    // and the user turns every one off, preserve that intentional empty state
    // instead of treating an empty vector as "no filter" (which would show all
    // rows again and make the controls feel broken).
    const bool categoryFilterActive = !filterButtons.isEmpty()
        && activeCategories.size() < static_cast<size_t>(filterButtons.size());
    clearFiltersButton.setToggleState(!filterButtons.isEmpty()
        && activeCategories.size() == static_cast<size_t>(filterButtons.size()),
        juce::dontSendNotification);
    canvas.setFilteredCategories(activeCategories, categoryFilterActive);
    browser.setFilteredCategories(activeCategories, categoryFilterActive);
    updateSelectionFilterCue();
}

void SmartSampleManagerAudioProcessorEditor::updateCategoryButtons()
{
    // Category discovery can happen while a scan is still adding rows. Keep
    // the user's existing toggle choices when rebuilding the pill strip; new
    // categories default on, while an intentional all-off state remains off.
    const bool hadPreviousButtons = !filterButtons.isEmpty();
    std::vector<std::pair<std::string, bool>> previousStates;
    previousStates.reserve(static_cast<size_t>(filterButtons.size()));
    for (auto* btn : filterButtons)
        previousStates.emplace_back(btn->getButtonText().toStdString(), btn->getToggleState());

    // Clear old filter buttons
    for (auto* btn : filterButtons) {
        filterBarContent.removeChildComponent(btn);
    }
    filterButtons.clear();

    // Do not invent filter controls before the first real library categories
    // arrive. A fresh launch should explain how to start, not present a row of
    // ten clickable pills that cannot yet filter anything.
    const auto cats = currentCategories;
    if (cats.empty())
    {
        filterBarContent.setSize(0, 0);
        resized();
        updateCanvasFilters();
        return;
    }

    for (const auto& catName : cats) {
        auto* btn = new juce::TextButton(catName);
        btn->setTooltip("Show or hide " + juce::String(catName) + " samples");
        btn->setWantsKeyboardFocus(true);
        btn->setClickingTogglesState(true);
        const auto previous = std::find_if(previousStates.begin(), previousStates.end(),
            [&catName](const auto& state) { return state.first == catName; });
        const bool enabled = !hadPreviousButtons || previous == previousStates.end()
            || previous->second;
        btn->setToggleState(enabled, juce::dontSendNotification);

        juce::Colour activeColor = canvas.getColourForInstrumentType(catName);
        // Every filter pill defaults to ON, so filling each one 100% opaque with
        // its category hue (and black text) meant the resting state of the app
        // was a row of ten solid saturated chips -- the single biggest source of
        // the "confetti" read, and it got louder once the category palette was
        // pushed up in saturation. The pill now renders as a tinted chip: a low-
        // alpha wash of its hue with the hue itself as the text colour. The
        // category is still identifiable at a glance, but the row sits back
        // instead of shouting, and the full-strength hues stay reserved for the
        // map dots where they actually encode position.
        btn->setColour(juce::TextButton::buttonOnColourId, activeColor.withAlpha(0.20f));
        btn->setColour(juce::TextButton::textColourOnId, activeColor);

        btn->setColour(juce::TextButton::buttonColourId, Tokens::surfaceRaised);
        btn->setColour(juce::TextButton::textColourOffId, Tokens::mutedDim);

        btn->onClick = [this]() {
            updateCanvasFilters();
        };

        filterBarContent.addAndMakeVisible(btn);
        filterButtons.add(btn);
    }

    // Relayout the buttons and refresh filters
    resized();
    updateCanvasFilters();
}

void SmartSampleManagerAudioProcessorEditor::updateLayoutMode()
{
    gridTabButton.setToggleState(currentLayoutMode == GridOnly, juce::dontSendNotification);
    mapTabButton.setToggleState(currentLayoutMode == MapOnly, juce::dontSendNotification);
    splitTabButton.setToggleState(currentLayoutMode == SplitView, juce::dontSendNotification);
    resized();
}

bool SmartSampleManagerAudioProcessorEditor::keyPressed(const juce::KeyPress& key)
{
    // Do not intercept hotkeys if the user is typing in a text field
    auto* currentlyFocused = juce::Component::getCurrentlyFocusedComponent();
    if (currentlyFocused != nullptr && dynamic_cast<juce::TextEditor*>(currentlyFocused) != nullptr)
    {
        // Escape is a useful, reversible browse action: clear the query and
        // return focus to the results instead of trapping the user in search.
        if (key == juce::KeyPress::escapeKey && currentlyFocused == &searchField)
        {
            searchField.clear();
            searchField.giveAwayKeyboardFocus();
            return true;
        }
        return false;
    }

    if (key == juce::KeyPress::upKey)
    {
        return browser.selectRelative(-1);
    }
    else if (key == juce::KeyPress::downKey)
    {
        return browser.selectRelative(1);
    }
    else if (key.getKeyCode() == juce::KeyPress::spaceKey)
    {
        if (hasSelection)
        {
            audioProcessor.playSample(selectedItem.filePath);
            return true;
        }
    }
    else if (key == juce::KeyPress::returnKey)
    {
        if (hasSelection)
        {
            audioProcessor.playSample(selectedItem.filePath);
            return true;
        }
    }
    else if ((key.getModifiers().isCommandDown() || key.getModifiers().isCtrlDown())
             && (key.getKeyCode() == 'f' || key.getKeyCode() == 'F'))
    {
        searchField.grabKeyboardFocus();
        return true;
    }
    else if (key.getKeyCode() == 'f' || key.getKeyCode() == 'F')
    {
        if (hasSelection)
        {
            bool isFav = audioProcessor.getEngine().isFavorite(selectedItem.filePath);
            audioProcessor.getEngine().setFavorite(selectedItem.filePath, !isFav);
            browser.updateSamples(audioProcessor.getEngine().getSamples());
            return true;
        }
    }
    else if (key.getKeyCode() == 's' || key.getKeyCode() == 'S')
    {
        if (hasSelection)
        {
            showSimilarSamplesReport();
            return true;
        }
    }
    else if (key.getKeyCode() == 'r' || key.getKeyCode() == 'R')
    {
        showReviewQueue();
        return true;
    }
    else if (key.getKeyCode() == 'u' || key.getKeyCode() == 'U')
    {
        showUnknownQueue();
        return true;
    }
    else if (key.getKeyCode() == 'a' || key.getKeyCode() == 'A')
    {
        // Keep the filter reset available from the keyboard as well as the
        // pill, while preserving the text-editor guard above for typed input.
        for (auto* btn : filterButtons)
            btn->setToggleState(true, juce::dontSendNotification);
        updateCanvasFilters();
        return true;
    }
    else if (key == juce::KeyPress(juce::KeyPress::escapeKey))
    {
        if (resultsPanel.isVisible())
        {
            hideResultsPanel();
            return true;
        }
        if (smartCollectionsPanel.isVisible())
        {
            hideSmartCollectionsPanel();
            return true;
        }
    }
    return false;
}
