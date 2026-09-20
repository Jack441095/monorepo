#include "SmartCollectionsPanel.h"
#include "DesignTokens.h"

SmartCollectionsPanel::SmartCollectionsPanel()
{
    setWantsKeyboardFocus(true);

    titleLabel.setFont(juce::Font(juce::FontOptions().withHeight(Tokens::fontHeading).withStyle("Bold")));
    titleLabel.setColour(juce::Label::textColourId, Tokens::foreground);
    titleLabel.setText("SMART COLLECTIONS", juce::dontSendNotification);
    addAndMakeVisible(titleLabel);

    closeButton.setButtonText("CLOSE");
    closeButton.setColour(juce::TextButton::buttonColourId, Tokens::surfaceRaised);
    closeButton.setColour(juce::TextButton::textColourOffId, Tokens::muted);
    closeButton.setTooltip("Close Smart Collections (Escape)");
    closeButton.onClick = [this]() { if (onClose) onClose(); };
    addAndMakeVisible(closeButton);

    collectionsListBox.setModel(this);
    collectionsListBox.setRowHeight(36);
    collectionsListBox.setColour(juce::ListBox::backgroundColourId, Tokens::surface);
    collectionsListBox.setColour(juce::ListBox::outlineColourId, Tokens::border);
    collectionsListBox.getVerticalScrollBar().setColour(juce::ScrollBar::thumbColourId, Tokens::borderStrong);
    addAndMakeVisible(collectionsListBox);

    // Starter presets -- sensible defaults a producer would actually reach
    // for, using only engine-real fields (Category/Key/BPM/Brightness/
    // Favorite). Shown in the same list as real collections until clicked,
    // at which point clicking creates them for real via saveCurrentRuleSet().
    starterPresets = {
        { "Membrane Kicks", "Circular Bessel membrane drum kicks", "Drums", "", 0.0f, 0.0f, 0, false, "Kick", "Skin / Mylar" },
        { "Metallic Cymbals & Bells", "High-Q metallic plate & bar resonances", "Drums", "", 0.0f, 0.0f, 0, false, "Crash / Cymbal", "Metal" },
        { "Organic Wood Hits", "Rapid acoustic damping wood percussion", "", "", 0.0f, 0.0f, 0, false, "", "Wood" },
        { "Stiff-String Basses", "Euler-Bernoulli inharmonic dispersion plucks", "Bass", "", 0.0f, 0.0f, 0, false, "Piano / Plucked String", "" },
        { "Bright Percussion", "Drums, brighter than average", "Drums", "", 0.0f, 0.0f, 3, false, "", "" },
        { "Deep Bass", "Bass category, darker than average", "Bass", "", 0.0f, 0.0f, 1, false, "", "" },
        { "Fast Loops (140+ BPM)", "Any category at or above 140 BPM", "", "", 140.0f, 999.0f, 0, false, "", "" },
        { "My Favorites", "Everything you've starred", "", "", 0.0f, 0.0f, 0, true, "", "" },
    };

    nameEditor.setTextToShowWhenEmpty("Collection name...", Tokens::mutedDim);
    nameEditor.setColour(juce::TextEditor::backgroundColourId, Tokens::surfaceRaised);
    nameEditor.setColour(juce::TextEditor::outlineColourId, Tokens::border);
    nameEditor.setColour(juce::TextEditor::textColourId, Tokens::foreground);
    nameEditor.setColour(juce::TextEditor::focusedOutlineColourId, Tokens::foreground);
    addAndMakeVisible(nameEditor);

    auto setupLabel = [this](juce::Label& l, const juce::String& text) {
        l.setText(text, juce::dontSendNotification);
        l.setFont(juce::Font(juce::FontOptions().withHeight(Tokens::fontLabel)));
        l.setColour(juce::Label::textColourId, Tokens::mutedDim);
        addAndMakeVisible(l);
    };
    setupLabel(categoryLabel, "Category");
    setupLabel(keyLabel, "Key");
    setupLabel(bpmLabel, "BPM range (blank = any)");
    setupLabel(brightnessLabel, "Brightness");
    setupLabel(physicalClassLabel, "Physics Resonator Class");
    setupLabel(materialLabel, "Acoustic Material");

    auto setupCombo = [this](juce::ComboBox& c) {
        c.setColour(juce::ComboBox::backgroundColourId, Tokens::surfaceRaised);
        c.setColour(juce::ComboBox::outlineColourId, Tokens::border);
        c.setColour(juce::ComboBox::textColourId, Tokens::foreground);
        c.setColour(juce::ComboBox::arrowColourId, Tokens::foreground);
        addAndMakeVisible(c);
    };
    setupCombo(categoryCombo);
    categoryCombo.addItem("Any category", 1);
    categoryCombo.addItem("Drums", 2);
    categoryCombo.addItem("Bass", 3);
    categoryCombo.addItem("Instruments", 4);
    categoryCombo.addItem("Vocals", 5);
    categoryCombo.addItem("FX", 6);
    categoryCombo.addItem("Ambience", 7);
    categoryCombo.setSelectedId(1, juce::dontSendNotification);

    setupCombo(brightnessCombo);
    brightnessCombo.addItem("Any brightness", 1);
    brightnessCombo.addItem("Darker", 2);
    brightnessCombo.addItem("Balanced", 3);
    brightnessCombo.addItem("Brighter", 4);
    brightnessCombo.setSelectedId(1, juce::dontSendNotification);

    setupCombo(physicalClassCombo);
    physicalClassCombo.addItem("Any physical class", 1);
    physicalClassCombo.addItem("Kick", 2);
    physicalClassCombo.addItem("Snare", 3);
    physicalClassCombo.addItem("Hi-Hat", 4);
    physicalClassCombo.addItem("Crash / Cymbal", 5);
    physicalClassCombo.addItem("Tom", 6);
    physicalClassCombo.addItem("Bass", 7);
    physicalClassCombo.addItem("Piano / Plucked String", 8);
    physicalClassCombo.setSelectedId(1, juce::dontSendNotification);

    setupCombo(materialCombo);
    materialCombo.addItem("Any material", 1);
    materialCombo.addItem("Wood", 2);
    materialCombo.addItem("Metal", 3);
    materialCombo.addItem("Skin / Mylar", 4);
    materialCombo.addItem("Glass / Ceramic", 5);
    materialCombo.setSelectedId(1, juce::dontSendNotification);

    keyEditor.setTextToShowWhenEmpty("Any key", Tokens::mutedDim);
    keyEditor.setColour(juce::TextEditor::backgroundColourId, Tokens::surfaceRaised);
    keyEditor.setColour(juce::TextEditor::outlineColourId, Tokens::border);
    keyEditor.setColour(juce::TextEditor::textColourId, Tokens::foreground);
    keyEditor.setColour(juce::TextEditor::focusedOutlineColourId, Tokens::foreground);
    addAndMakeVisible(keyEditor);

    auto setupBpmEditor = [this](juce::TextEditor& e, const juce::String& placeholder) {
        e.setInputRestrictions(5, "0123456789.");
        e.setTextToShowWhenEmpty(placeholder, Tokens::mutedDim);
        e.setColour(juce::TextEditor::backgroundColourId, Tokens::surfaceRaised);
        e.setColour(juce::TextEditor::outlineColourId, Tokens::border);
        e.setColour(juce::TextEditor::textColourId, Tokens::foreground);
        e.setColour(juce::TextEditor::focusedOutlineColourId, Tokens::foreground);
        addAndMakeVisible(e);
    };
    setupBpmEditor(bpmMinEditor, "Min");
    setupBpmEditor(bpmMaxEditor, "Max");

    favoriteOnlyToggle.setButtonText("Favorites only");
    favoriteOnlyToggle.setColour(juce::ToggleButton::textColourId, Tokens::foreground);
    favoriteOnlyToggle.setColour(juce::ToggleButton::tickColourId, Tokens::foreground);
    addAndMakeVisible(favoriteOnlyToggle);

    saveButton.setButtonText("SAVE COLLECTION");
    saveButton.setColour(juce::TextButton::buttonColourId, Tokens::surface);
    saveButton.setColour(juce::TextButton::textColourOffId, Tokens::foreground);
    saveButton.setTooltip("Save this filter as a reusable smart collection");
    saveButton.onClick = [this]() { saveCurrentRuleSet(); };
    addAndMakeVisible(saveButton);

    deleteButton.setButtonText("DELETE COLLECTION");
    deleteButton.setColour(juce::TextButton::buttonColourId, Tokens::surfaceRaised);
    deleteButton.setColour(juce::TextButton::textColourOffId, Tokens::danger);
    deleteButton.setTooltip("Delete the selected smart collection");
    deleteButton.onClick = [this]() { deleteEditingCollection(); };
    addChildComponent(deleteButton); // only visible when editing an existing collection

    emptyStateLabel.setFont(juce::Font(juce::FontOptions().withHeight(Tokens::fontBody)));
    emptyStateLabel.setColour(juce::Label::textColourId, Tokens::mutedDim);
    emptyStateLabel.setJustificationType(juce::Justification::centred);
    addChildComponent(emptyStateLabel);

    sampleResultsListBox.setModel(&sampleRowsModel);
    sampleResultsListBox.setRowHeight(36);
    sampleResultsListBox.setColour(juce::ListBox::backgroundColourId, Tokens::surface);
    sampleResultsListBox.setColour(juce::ListBox::outlineColourId, Tokens::border);
    sampleResultsListBox.getVerticalScrollBar().setColour(juce::ScrollBar::thumbColourId, Tokens::borderStrong);
    addChildComponent(sampleResultsListBox);

    showBuilderForNewCollection();
}

bool SmartCollectionsPanel::keyPressed(const juce::KeyPress& key)
{
    if (key == juce::KeyPress::escapeKey)
    {
        if (onClose) onClose();
        return true;
    }
    return false;
}

void SmartCollectionsPanel::setEngine(SampleManagerEngine* engineToUse)
{
    engine = engineToUse;
}

void SmartCollectionsPanel::refreshAndShow()
{
    collectionNames.clear();
    if (engine != nullptr)
        collectionNames = engine->getSmartCollectionNames();
    numRealCollections = static_cast<int>(collectionNames.size());
    collectionsListBox.updateContent();
    collectionsListBox.repaint();
    setVisible(true);
}

void SmartCollectionsPanel::setSampleSelectedCallback(std::function<void(const SampleItem&)> callback)
{
    onSampleSelected = std::move(callback);
}

void SmartCollectionsPanel::setCloseCallback(std::function<void()> callback)
{
    onClose = std::move(callback);
}

void SmartCollectionsPanel::paint(juce::Graphics& g)
{
    auto bounds = getLocalBounds().toFloat();
    g.setColour(Tokens::surface);
    g.fillRoundedRectangle(bounds, 8.0f);
    g.setColour(Tokens::border);
    g.drawRoundedRectangle(bounds.reduced(0.5f), 8.0f, 1.0f);

    if (hasKeyboardFocus(true))
    {
        g.setColour(Tokens::focusRing.withAlpha(0.72f));
        g.drawRoundedRectangle(bounds.reduced(1.0f), 8.0f, 1.5f);
    }

    // Divider between the collections list and the builder/results pane
    g.setColour(Tokens::border);
    g.drawVerticalLine(static_cast<int>(getWidth() * 0.32f), 44.0f, static_cast<float>(getHeight() - 12));
}

void SmartCollectionsPanel::resized()
{
    auto area = getLocalBounds().reduced(12);
    auto headerRow = area.removeFromTop(28);
    closeButton.setBounds(headerRow.removeFromRight(70));
    titleLabel.setBounds(headerRow);
    area.removeFromTop(8);

    int leftWidth = static_cast<int>(area.getWidth() * 0.32f) - 8;
    auto leftArea = area.removeFromLeft(leftWidth);
    area.removeFromLeft(16);
    collectionsListBox.setBounds(leftArea);

    // Right pane -- builder form
    auto rightArea = area;
    nameEditor.setBounds(rightArea.removeFromTop(26));
    rightArea.removeFromTop(10);

    categoryLabel.setBounds(rightArea.removeFromTop(14));
    categoryCombo.setBounds(rightArea.removeFromTop(24));
    rightArea.removeFromTop(8);

    keyLabel.setBounds(rightArea.removeFromTop(14));
    keyEditor.setBounds(rightArea.removeFromTop(24));
    rightArea.removeFromTop(8);

    bpmLabel.setBounds(rightArea.removeFromTop(14));
    auto bpmRow = rightArea.removeFromTop(24);
    bpmMinEditor.setBounds(bpmRow.removeFromLeft(bpmRow.getWidth() / 2 - 4));
    bpmRow.removeFromLeft(8);
    bpmMaxEditor.setBounds(bpmRow);
    rightArea.removeFromTop(8);

    brightnessLabel.setBounds(rightArea.removeFromTop(14));
    brightnessCombo.setBounds(rightArea.removeFromTop(24));
    rightArea.removeFromTop(8);

    auto physRow = rightArea.removeFromTop(42);
    int halfPhysW = (physRow.getWidth() - 8) / 2;
    auto leftPhys = physRow.removeFromLeft(halfPhysW);
    physRow.removeFromLeft(8);
    auto rightPhys = physRow;

    physicalClassLabel.setBounds(leftPhys.removeFromTop(14));
    leftPhys.removeFromTop(2);
    physicalClassCombo.setBounds(leftPhys.removeFromTop(24));

    materialLabel.setBounds(rightPhys.removeFromTop(14));
    rightPhys.removeFromTop(2);
    materialCombo.setBounds(rightPhys.removeFromTop(24));

    rightArea.removeFromTop(8);

    favoriteOnlyToggle.setBounds(rightArea.removeFromTop(24));
    rightArea.removeFromTop(12);

    auto buttonRow = rightArea.removeFromTop(28);
    if (deleteButton.isVisible()) {
        saveButton.setBounds(buttonRow.removeFromLeft(buttonRow.getWidth() / 2 - 4));
        buttonRow.removeFromLeft(8);
        deleteButton.setBounds(buttonRow);
    } else {
        saveButton.setBounds(buttonRow);
    }

    // Results pane occupies the same right-hand region as the builder, when active
    emptyStateLabel.setBounds(area);
    sampleResultsListBox.setBounds(area);
}

// ── Collections list (juce::ListBoxModel) ──────────────────────────────────

int SmartCollectionsPanel::getNumRows()
{
    return static_cast<int>(collectionNames.size() + starterPresets.size());
}

void SmartCollectionsPanel::paintListBoxItem(int rowNumber, juce::Graphics& g, int width, int height, bool rowIsSelected)
{
    if (rowIsSelected) {
        g.setColour(Tokens::surfaceRaised);
        g.fillRect(0, 0, width, height);
    }
    auto bounds = juce::Rectangle<int>(0, 0, width, height).reduced(10, 4);

    if (rowNumber < numRealCollections) {
        g.setColour(Tokens::foreground);
        g.setFont(juce::Font(juce::FontOptions().withHeight(13.0f)));
        g.drawFittedText(collectionNames[static_cast<size_t>(rowNumber)], bounds, juce::Justification::centredLeft, 1);
    } else {
        // Starter preset -- not yet created. Visually distinct ("+ " prefix,
        // dimmer) so it doesn't read as an already-existing collection.
        int presetIdx = rowNumber - numRealCollections;
        if (presetIdx < 0 || presetIdx >= static_cast<int>(starterPresets.size())) return;
        const auto& preset = starterPresets[static_cast<size_t>(presetIdx)];
        g.setColour(Tokens::mutedDim);
        g.setFont(juce::Font(juce::FontOptions().withHeight(13.0f)));
        g.drawFittedText("+ " + preset.name, bounds.removeFromTop(height / 2), juce::Justification::centredLeft, 1);
        g.setFont(juce::Font(juce::FontOptions().withHeight(10.0f)));
        g.drawFittedText(preset.description, bounds, juce::Justification::centredLeft, 1);
    }
}

void SmartCollectionsPanel::listBoxItemClicked(int row, const juce::MouseEvent&)
{
    if (row < 0) return;
    if (row < numRealCollections) {
        showResultsForCollection(collectionNames[static_cast<size_t>(row)]);
    } else {
        int presetIdx = row - numRealCollections;
        if (presetIdx < 0 || presetIdx >= static_cast<int>(starterPresets.size())) return;
        loadPresetIntoBuilder(starterPresets[static_cast<size_t>(presetIdx)]);
    }
}

// ── Builder / results toggling ──────────────────────────────────────────

void SmartCollectionsPanel::showBuilderForNewCollection()
{
    showingBuilder = true;
    editingCollectionName = {};
    nameEditor.setText({}, juce::dontSendNotification);
    categoryCombo.setSelectedId(1, juce::dontSendNotification);
    keyEditor.setText({}, juce::dontSendNotification);
    bpmMinEditor.setText({}, juce::dontSendNotification);
    bpmMaxEditor.setText({}, juce::dontSendNotification);
    brightnessCombo.setSelectedId(1, juce::dontSendNotification);
    physicalClassCombo.setSelectedId(1, juce::dontSendNotification);
    materialCombo.setSelectedId(1, juce::dontSendNotification);
    favoriteOnlyToggle.setToggleState(false, juce::dontSendNotification);
    saveButton.setButtonText("SAVE COLLECTION");
    deleteButton.setVisible(false);

    nameEditor.setVisible(true); categoryLabel.setVisible(true); categoryCombo.setVisible(true);
    keyLabel.setVisible(true); keyEditor.setVisible(true); bpmLabel.setVisible(true);
    bpmMinEditor.setVisible(true); bpmMaxEditor.setVisible(true);
    brightnessLabel.setVisible(true); brightnessCombo.setVisible(true);
    physicalClassLabel.setVisible(true); physicalClassCombo.setVisible(true);
    materialLabel.setVisible(true); materialCombo.setVisible(true);
    favoriteOnlyToggle.setVisible(true); saveButton.setVisible(true);
    emptyStateLabel.setVisible(false);
    sampleResultsListBox.setVisible(false);
    resized();
}

void SmartCollectionsPanel::loadPresetIntoBuilder(const StarterPreset& preset)
{
    showBuilderForNewCollection();
    nameEditor.setText(preset.name, juce::dontSendNotification);
    categoryCombo.setText(preset.category.isEmpty() ? "Any category" : preset.category, juce::dontSendNotification);
    keyEditor.setText(preset.key, juce::dontSendNotification);
    if (preset.bpmMin > 0.0f) bpmMinEditor.setText(juce::String(preset.bpmMin, 0), juce::dontSendNotification);
    if (preset.bpmMax > 0.0f) bpmMaxEditor.setText(juce::String(preset.bpmMax, 0), juce::dontSendNotification);
    brightnessCombo.setSelectedId(preset.brightnessBand + 1, juce::dontSendNotification);
    if (preset.physicalClass.isNotEmpty())
        physicalClassCombo.setText(preset.physicalClass, juce::dontSendNotification);
    else
        physicalClassCombo.setSelectedId(1, juce::dontSendNotification);
    if (preset.material.isNotEmpty())
        materialCombo.setText(preset.material, juce::dontSendNotification);
    else
        materialCombo.setSelectedId(1, juce::dontSendNotification);
    favoriteOnlyToggle.setToggleState(preset.favoriteOnly, juce::dontSendNotification);
}

void SmartCollectionsPanel::showBuilderForExistingCollection(const juce::String& name)
{
    // Editing an already-created collection's rules isn't reconstructable
    // from the stored JSON in a friendly way without re-parsing it back into
    // the form (deliberately not done this pass -- see
    // docs/SMART_SAMPLE_MANAGER_UX_AUDIT.md). Renaming/re-ruling an existing
    // collection today means delete + recreate, which DELETE COLLECTION next
    // to a fresh builder makes a two-click, obvious path for.
    showBuilderForNewCollection();
    editingCollectionName = name;
    nameEditor.setText(name, juce::dontSendNotification);
    saveButton.setButtonText("SAVE AS NEW / REPLACE");
    deleteButton.setVisible(true);
    resized();
}

void SmartCollectionsPanel::showResultsForCollection(const juce::String& name)
{
    showingBuilder = false;
    editingCollectionName = name;

    nameEditor.setVisible(false); categoryLabel.setVisible(false); categoryCombo.setVisible(false);
    keyLabel.setVisible(false); keyEditor.setVisible(false); bpmLabel.setVisible(false);
    bpmMinEditor.setVisible(false); bpmMaxEditor.setVisible(false);
    brightnessLabel.setVisible(false); brightnessCombo.setVisible(false);
    physicalClassLabel.setVisible(false); physicalClassCombo.setVisible(false);
    materialLabel.setVisible(false); materialCombo.setVisible(false);
    favoriteOnlyToggle.setVisible(false); saveButton.setVisible(false); deleteButton.setVisible(false);

    currentResultItems.clear();
    if (engine != nullptr)
        currentResultItems = engine->getSmartCollectionSamples(name.toStdString());

    if (currentResultItems.empty()) {
        emptyStateLabel.setText(
            "\"" + name + "\" has no matching samples right now.\n"
            "Nothing in your library currently fits this collection's rules -- "
            "add more samples or click it in the list again to edit the rules.",
            juce::dontSendNotification);
        emptyStateLabel.setVisible(true);
        sampleResultsListBox.setVisible(false);
    } else {
        emptyStateLabel.setVisible(false);
        sampleResultsListBox.setVisible(true);
        sampleResultsListBox.updateContent();
        sampleResultsListBox.repaint();
    }

    // Offer edit access via a small affordance: double-click header area isn't
    // wired here (kept simple) -- re-clicking DELETE + rebuilding is the
    // documented edit path (see showBuilderForExistingCollection's comment).
    resized();
}

void SmartCollectionsPanel::saveCurrentRuleSet()
{
    if (engine == nullptr) return;
    juce::String name = nameEditor.getText().trim();
    if (name.isEmpty()) {
        juce::AlertWindow::showMessageBoxAsync(juce::MessageBoxIconType::WarningIcon,
            "Smart Collections", "Give this collection a name before saving.");
        return;
    }

    engine->createSmartCollection(name.toStdString(), buildRulesJson().toStdString());
    refreshAndShow();
    showResultsForCollection(name);
}

void SmartCollectionsPanel::deleteEditingCollection()
{
    if (engine == nullptr || editingCollectionName.isEmpty()) return;
    juce::String nameToDelete = editingCollectionName;
    engine->deleteSmartCollection(nameToDelete.toStdString());
    refreshAndShow();
    showBuilderForNewCollection();
}

juce::String SmartCollectionsPanel::buildRulesJson() const
{
    // Flat AND-only schema -- matches SampleManagerEngine::getSmartCollectionSamples()
    // exactly (see this file's header comment). Fields left at their "any"
    // default are simply omitted rather than sent as wildcard values.
    auto* obj = new juce::DynamicObject();
    juce::var result(obj);

    juce::String category = categoryCombo.getText();
    if (category.isNotEmpty() && category != "Any category")
        obj->setProperty("category", category);

    juce::String key = keyEditor.getText().trim();
    if (key.isNotEmpty())
        obj->setProperty("key", key);

    juce::String bpmMinText = bpmMinEditor.getText().trim();
    if (bpmMinText.isNotEmpty())
        obj->setProperty("bpm_min", bpmMinText.getFloatValue());
    juce::String bpmMaxText = bpmMaxEditor.getText().trim();
    if (bpmMaxText.isNotEmpty())
        obj->setProperty("bpm_max", bpmMaxText.getFloatValue());

    // Brightness bands -- a simple, documented split of the spectral-centroid
    // range this app's samples typically fall in (roughly 0-8000Hz for one-
    // shots/loops). Not derived from the actual library's distribution (no
    // percentile computation this pass) -- directional, not precise. Never
    // shown to the user as Hz.
    int brightnessId = brightnessCombo.getSelectedId();
    if (brightnessId == 2) { // Darker
        obj->setProperty("centroid_max", 1800.0f);
    } else if (brightnessId == 3) { // Balanced
        obj->setProperty("centroid_min", 1800.0f);
        obj->setProperty("centroid_max", 4200.0f);
    } else if (brightnessId == 4) { // Brighter
        obj->setProperty("centroid_min", 4200.0f);
    }

    juce::String physClass = physicalClassCombo.getText();
    if (physClass.isNotEmpty() && physClass != "Any physical class")
        obj->setProperty("physical_class", physClass);

    juce::String mat = materialCombo.getText();
    if (mat.isNotEmpty() && mat != "Any material")
        obj->setProperty("material", mat);

    if (favoriteOnlyToggle.getToggleState())
        obj->setProperty("favorite", true);

    return juce::JSON::toString(result, true);
}

// ── Evaluated-samples list (inner ListBoxModel) ─────────────────────────────

int SmartCollectionsPanel::SampleRowsModel::getNumRows()
{
    return static_cast<int>(owner.currentResultItems.size());
}

void SmartCollectionsPanel::SampleRowsModel::paintListBoxItem(int rowNumber, juce::Graphics& g, int width, int height, bool rowIsSelected)
{
    if (rowNumber < 0 || rowNumber >= static_cast<int>(owner.currentResultItems.size())) return;
    const auto& item = owner.currentResultItems[static_cast<size_t>(rowNumber)];

    if (rowIsSelected) {
        g.setColour(Tokens::surfaceRaised);
        g.fillRect(0, 0, width, height);
    }
    auto bounds = juce::Rectangle<int>(0, 0, width, height).reduced(10, 4);
    g.setColour(Tokens::foreground);
    g.setFont(juce::Font(juce::FontOptions().withHeight(13.0f)));
    g.drawFittedText(item.name, bounds.removeFromTop(height / 2), juce::Justification::centredLeft, 1);

    g.setColour(Tokens::mutedDim);
    g.setFont(juce::Font(juce::FontOptions().withHeight(11.0f)));
    juce::String secondary = juce::String(item.category.empty() ? item.instrumentType : item.category);
    if (item.bpm > 0.0f) secondary += "  " + juce::String(static_cast<int>(item.bpm)) + " BPM";
    if (item.key != "Unknown" && !item.key.empty()) secondary += "  " + juce::String(item.key);
    g.drawFittedText(secondary, bounds, juce::Justification::centredLeft, 1);
}

void SmartCollectionsPanel::SampleRowsModel::listBoxItemClicked(int row, const juce::MouseEvent&)
{
    if (row < 0 || row >= static_cast<int>(owner.currentResultItems.size())) return;
    if (owner.onSampleSelected) owner.onSampleSelected(owner.currentResultItems[static_cast<size_t>(row)]);
}
