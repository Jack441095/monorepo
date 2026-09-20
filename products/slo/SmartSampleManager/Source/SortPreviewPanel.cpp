#include "SortPreviewPanel.h"
#include "DesignTokens.h"

SortPreviewPanel::SortPreviewPanel(SampleManagerEngine& eng)
    : engine(eng)
{
    setWantsKeyboardFocus(true);

    setOpaque(false);

    titleLabel.setText("SORT & RENAME PREVIEW", juce::dontSendNotification);
    titleLabel.setFont(juce::Font(16.0f, juce::Font::bold));
    titleLabel.setColour(juce::Label::textColourId, Tokens::foreground);
    addAndMakeVisible(titleLabel);

    summaryLabel.setFont(juce::Font(13.0f, juce::Font::plain));
    summaryLabel.setColour(juce::Label::textColourId, Tokens::muted);
    addAndMakeVisible(summaryLabel);

    closeButton.setButtonText(juce::String::charToString(0x2715)); // multiplication X
    closeButton.setColour(juce::TextButton::buttonColourId, juce::Colours::transparentBlack);
    closeButton.setColour(juce::TextButton::textColourOffId, Tokens::muted);
    closeButton.setTooltip("Close the sort preview without changing files");
    closeButton.onClick = [this]() {
        if (onCancel) onCancel();
        setVisible(false);
    };
    addAndMakeVisible(closeButton);

    searchField.setTextToShowWhenEmpty("Filter preview items...", Tokens::muted);
    searchField.setColour(juce::TextEditor::backgroundColourId, Tokens::lcdBackground);
    searchField.setColour(juce::TextEditor::textColourId, Tokens::foreground);
    searchField.setColour(juce::TextEditor::outlineColourId, Tokens::border);
    searchField.onTextChange = [this]() {
        searchQuery = searchField.getText().trim().toLowerCase();
        applyFilter();
    };
    addAndMakeVisible(searchField);

    auto setupFilterBtn = [this](juce::TextButton& btn, const juce::String& text, FilterMode mode) {
        btn.setButtonText(text);
        btn.setColour(juce::TextButton::buttonColourId, mode == currentFilter ? Tokens::surfaceActive : Tokens::surfaceRaised);
        btn.setColour(juce::TextButton::textColourOffId, mode == currentFilter ? Tokens::electricCyan : Tokens::foreground);
        btn.onClick = [this, mode]() {
            currentFilter = mode;
            filterAllButton.setColour(juce::TextButton::buttonColourId, currentFilter == filterAll ? Tokens::surfaceActive : Tokens::surfaceRaised);
            filterAllButton.setColour(juce::TextButton::textColourOffId, currentFilter == filterAll ? Tokens::electricCyan : Tokens::foreground);
            filterEligibleButton.setColour(juce::TextButton::buttonColourId, currentFilter == filterEligibleOnly ? Tokens::surfaceActive : Tokens::surfaceRaised);
            filterEligibleButton.setColour(juce::TextButton::textColourOffId, currentFilter == filterEligibleOnly ? Tokens::electricCyan : Tokens::foreground);
            filterExcludedButton.setColour(juce::TextButton::buttonColourId, currentFilter == filterExcludedOnly ? Tokens::surfaceActive : Tokens::surfaceRaised);
            filterExcludedButton.setColour(juce::TextButton::textColourOffId, currentFilter == filterExcludedOnly ? Tokens::electricCyan : Tokens::foreground);
            applyFilter();
        };
        addAndMakeVisible(btn);
    };

    setupFilterBtn(filterAllButton, "All (0)", filterAll);
    setupFilterBtn(filterEligibleButton, "Ready to Rename (0)", filterEligibleOnly);
    setupFilterBtn(filterExcludedButton, "Excluded by Safety Gate (0)", filterExcludedOnly);

    // Setup Table
    auto& header = table.getHeader();
    header.addColumn("Action", colStatus, 80, 60, 100);
    header.addColumn("Current Filename", colOriginalName, 210, 120, 400);
    header.addColumn(" ", colArrow, 24, 24, 24);
    header.addColumn("Proposed Filename", colProposedName, 230, 120, 450);
    header.addColumn("Target Subfolder", colFolder, 150, 90, 300);
    header.addColumn("Key / BPM", colKeyBpm, 100, 70, 140);
    header.addColumn("Safety Status", colPolicyReason, 140, 90, 250);

    table.setModel(this);
    table.setColour(juce::TableListBox::backgroundColourId, Tokens::background);
    table.setColour(juce::ListBox::outlineColourId, Tokens::border);
    table.setRowHeight(26);
    addAndMakeVisible(table);

    // Bottom Action buttons
    copyButton.setButtonText("Copy (Recommended)");
    copyButton.setColour(juce::TextButton::buttonColourId, Tokens::emeraldGreen.withAlpha(0.25f));
    copyButton.setColour(juce::TextButton::textColourOffId, Tokens::emeraldGreen);
    copyButton.setTooltip("Create organized copies and leave the originals untouched");
    copyButton.onClick = [this]() {
        if (onConfirm) onConfirm(true);
        setVisible(false);
    };
    addAndMakeVisible(copyButton);

    moveButton.setButtonText("Move Files");
    moveButton.setColour(juce::TextButton::buttonColourId, Tokens::amberWarning.withAlpha(0.25f));
    moveButton.setColour(juce::TextButton::textColourOffId, Tokens::amberWarning);
    moveButton.setTooltip("Move files into the proposed folders after confirmation");
    moveButton.onClick = [this]() {
        if (onConfirm) onConfirm(false);
        setVisible(false);
    };
    addAndMakeVisible(moveButton);

    cancelButton.setButtonText("Cancel");
    cancelButton.setColour(juce::TextButton::buttonColourId, Tokens::surfaceRaised);
    cancelButton.setColour(juce::TextButton::textColourOffId, Tokens::foreground);
    cancelButton.setTooltip("Close the preview without applying changes");
    cancelButton.onClick = [this]() {
        if (onCancel) onCancel();
        setVisible(false);
    };
    addAndMakeVisible(cancelButton);

    undoPreviousButton.setButtonText("Undo Previous Sort...");
    undoPreviousButton.setColour(juce::TextButton::buttonColourId, Tokens::surfaceRaised);
    undoPreviousButton.setColour(juce::TextButton::textColourOffId, Tokens::electricCyan);
    undoPreviousButton.setTooltip("Restore files from the last completed sort");
    undoPreviousButton.onClick = [this]() {
        if (onUndoPrevious) onUndoPrevious();
    };
    addAndMakeVisible(undoPreviousButton);
}

void SortPreviewPanel::setPreview(const SampleManagerEngine::SortPreviewResult& result, int style)
{
    currentResult = result;
    namingStyle = style;

    filterAllButton.setButtonText("All (" + juce::String(result.totalCount) + ")");
    filterEligibleButton.setButtonText("Ready to Rename (" + juce::String(result.eligibleCount) + ")");
    filterExcludedButton.setButtonText("Excluded by Gate (" + juce::String(result.skippedCount) + ")");

    juce::String summary = juce::String(result.totalCount) + " total samples  \u2022  "
        + juce::String(result.eligibleCount) + " will be organized and renamed  \u2022  "
        + juce::String(result.skippedCount) + " preserved in place by safety policy";
    if (result.collisionCount > 0) {
        summary += "  \u2022  " + juce::String(result.collisionCount) + " collisions auto-suffixed";
    }
    summaryLabel.setText(summary, juce::dontSendNotification);

    undoPreviousButton.setVisible(engine.canUndoSort());

    applyFilter();
}

void SortPreviewPanel::applyFilter()
{
    filteredItems.clear();
    for (const auto& item : currentResult.items) {
        if (currentFilter == filterEligibleOnly && !item.eligible) continue;
        if (currentFilter == filterExcludedOnly && item.eligible) continue;

        if (searchQuery.isNotEmpty()) {
            bool matches = juce::String(item.sourceFilename).toLowerCase().contains(searchQuery)
                        || juce::String(item.destinationFilename).toLowerCase().contains(searchQuery)
                        || juce::String(item.category).toLowerCase().contains(searchQuery)
                        || juce::String(item.subcategory).toLowerCase().contains(searchQuery)
                        || juce::String(item.key).toLowerCase().contains(searchQuery)
                        || juce::String(item.policyReason).toLowerCase().contains(searchQuery);
            if (!matches) continue;
        }

        filteredItems.push_back(item);
    }

    table.updateContent();
    table.repaint();
}

void SortPreviewPanel::setConfirmCallback(std::function<void(bool)> callback) { onConfirm = std::move(callback); }
void SortPreviewPanel::setCancelCallback(std::function<void()> callback) { onCancel = std::move(callback); }
void SortPreviewPanel::setUndoPreviousCallback(std::function<void()> callback) { onUndoPrevious = std::move(callback); }

int SortPreviewPanel::getNumRows()
{
    return static_cast<int>(filteredItems.size());
}

void SortPreviewPanel::paintRowBackground(juce::Graphics& g, int rowNumber, int width, int height, bool rowIsSelected)
{
    if (rowIsSelected) {
        g.fillAll(Tokens::surfaceActive);
    } else if (rowNumber % 2 == 1) {
        g.fillAll(Tokens::surface.withAlpha(0.4f));
    }
}

void SortPreviewPanel::paintCell(juce::Graphics& g, int rowNumber, int columnId, int width, int height, bool rowIsSelected)
{
    if (rowNumber < 0 || rowNumber >= static_cast<int>(filteredItems.size())) return;
    const auto& item = filteredItems[rowNumber];

    auto r = juce::Rectangle<int>(0, 0, width, height).reduced(4, 2);
    g.setFont(12.0f);

    switch (columnId)
    {
        case colStatus:
        {
            auto pillRect = r.reduced(2, 2).toFloat();
            if (!item.eligible) {
                g.setColour(Tokens::amberWarning.withAlpha(0.2f));
                g.fillRoundedRectangle(pillRect, 4.0f);
                g.setColour(Tokens::amberWarning);
                g.drawText("SKIPPED", r, juce::Justification::centred);
            } else if (item.willCollide) {
                g.setColour(Tokens::electricCyan.withAlpha(0.2f));
                g.fillRoundedRectangle(pillRect, 4.0f);
                g.setColour(Tokens::electricCyan);
                g.drawText("COLLISION", r, juce::Justification::centred);
            } else {
                g.setColour(Tokens::emeraldGreen.withAlpha(0.2f));
                g.fillRoundedRectangle(pillRect, 4.0f);
                g.setColour(Tokens::emeraldGreen);
                g.drawText("RENAME", r, juce::Justification::centred);
            }
            break;
        }

        case colOriginalName:
            g.setColour(Tokens::foreground);
            g.drawText(juce::String(item.sourceFilename), r, juce::Justification::centredLeft, true);
            break;

        case colArrow:
            g.setColour(Tokens::muted);
            g.drawText(juce::String::charToString(0x2192), r, juce::Justification::centred); // right arrow
            break;

        case colProposedName:
            if (item.eligible) {
                g.setColour(Tokens::electricCyan);
                g.drawText(juce::String(item.destinationFilename), r, juce::Justification::centredLeft, true);
            } else {
                g.setColour(Tokens::muted);
                g.drawText(juce::String(item.sourceFilename) + " (unchanged)", r, juce::Justification::centredLeft, true);
            }
            break;

        case colFolder:
        {
            juce::File dest(item.destinationPath);
            juce::String folder = dest.getParentDirectory().getFileName();
            g.setColour(item.eligible ? Tokens::foreground : Tokens::muted);
            g.drawText(folder, r, juce::Justification::centredLeft, true);
            break;
        }

        case colKeyBpm:
        {
            juce::String desc;
            if (!item.key.empty()) desc += juce::String(item.key);
            if (item.bpm > 0.0f) {
                if (desc.isNotEmpty()) desc += "  ";
                desc += juce::String(juce::roundToInt(item.bpm)) + " BPM";
            }
            if (desc.isEmpty()) desc = "-";
            g.setColour(Tokens::muted);
            g.drawText(desc, r, juce::Justification::centredLeft, true);
            break;
        }

        case colPolicyReason:
        {
            g.setColour(item.eligible ? Tokens::muted : Tokens::amberWarning);
            g.drawText(juce::String(item.policyReason), r, juce::Justification::centredLeft, true);
            break;
        }
    }
}

void SortPreviewPanel::paint(juce::Graphics& g)
{
    // Dim the background behind modal dialog
    g.fillAll(juce::Colours::black.withAlpha(0.65f));

    // Card boundary
    auto bounds = getLocalBounds().reduced(24, 20).toFloat();
    g.setColour(Tokens::surface);
    g.fillRoundedRectangle(bounds, 8.0f);

    g.setColour(Tokens::borderStrong);
    g.drawRoundedRectangle(bounds, 8.0f, 1.5f);

    if (hasKeyboardFocus(true))
    {
        g.setColour(Tokens::focusRing.withAlpha(0.72f));
        g.drawRoundedRectangle(bounds.reduced(1.0f), 8.0f, 1.5f);
    }
}

void SortPreviewPanel::resized()
{
    auto area = getLocalBounds().reduced(36, 32);

    // Top title bar
    auto headerRow = area.removeFromTop(28);
    closeButton.setBounds(headerRow.removeFromRight(28));
    titleLabel.setBounds(headerRow);

    area.removeFromTop(4);
    summaryLabel.setBounds(area.removeFromTop(20));

    area.removeFromTop(10);

    // Filter and search row. The fixed desktop arrangement is efficient when
    // there is room, but it clips the search field at compact plugin widths.
    // Stack the search field above the three filters in that case so every
    // action remains reachable and legible.
    const bool compactFilters = getWidth() < 900;
    if (compactFilters) {
        searchField.setBounds(area.removeFromTop(28));
        area.removeFromTop(6);
        auto filterRow = area.removeFromTop(28);
        const int filterW = juce::jmax(72, (filterRow.getWidth() - 12) / 3);
        filterAllButton.setBounds(filterRow.removeFromLeft(filterW));
        filterRow.removeFromLeft(6);
        filterEligibleButton.setBounds(filterRow.removeFromLeft(filterW));
        filterRow.removeFromLeft(6);
        filterExcludedButton.setBounds(filterRow);
    } else {
        auto filterRow = area.removeFromTop(28);
        searchField.setBounds(filterRow.removeFromRight(200));
        filterRow.removeFromRight(12);

        filterAllButton.setBounds(filterRow.removeFromLeft(90));
        filterRow.removeFromLeft(6);
        filterEligibleButton.setBounds(filterRow.removeFromLeft(160));
        filterRow.removeFromLeft(6);
        filterExcludedButton.setBounds(filterRow.removeFromLeft(200));
    }

    area.removeFromTop(12);

    // Bottom action row
    auto actionRow = area.removeFromBottom(34);
    if (undoPreviousButton.isVisible()) {
        undoPreviousButton.setBounds(actionRow.removeFromLeft(170));
    }
    cancelButton.setBounds(actionRow.removeFromRight(90));
    actionRow.removeFromRight(8);
    moveButton.setBounds(actionRow.removeFromRight(110));
    actionRow.removeFromRight(8);
    copyButton.setBounds(actionRow.removeFromRight(160));

    area.removeFromBottom(12);

    // Center table
    table.setBounds(area);
}

bool SortPreviewPanel::keyPressed(const juce::KeyPress& key)
{
    if (key.isKeyCode(juce::KeyPress::escapeKey)) {
        if (onCancel) onCancel();
        setVisible(false);
        return true;
    }
    return false;
}
