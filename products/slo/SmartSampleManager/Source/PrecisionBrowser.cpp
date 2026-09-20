#include "PrecisionBrowser.h"
#include "DesignTokens.h"
#include "SearchLexicon.h"
#include "ClassificationPresentation.h"
#include <algorithm>
#include <cmath>

PrecisionBrowser::PrecisionBrowser(SampleManagerEngine& e)
    : engine(e)
{
    setWantsKeyboardFocus(true);
    setMouseClickGrabsKeyboardFocus(true);
    addAndMakeVisible(table);
    addAndMakeVisible(summaryLabel);
    summaryLabel.setFont(juce::Font(juce::FontOptions().withHeight(Tokens::fontLabel)));
    summaryLabel.setColour(juce::Label::textColourId, Tokens::mutedDim);
    summaryLabel.setJustificationType(juce::Justification::centredLeft);
    table.setModel(this);
    
    // Set headers
    auto& header = table.getHeader();
    header.addColumn("PLAY", colPlayState, 45, 30, 60, juce::TableHeaderComponent::visible | juce::TableHeaderComponent::resizable);
    header.addColumn("FAV", colFavorite, 45, 30, 60, juce::TableHeaderComponent::visible | juce::TableHeaderComponent::resizable);
    header.addColumn("SAMPLE", colFilename, 260, 120, 1000, juce::TableHeaderComponent::defaultFlags);
    header.addColumn("CATEGORY", colCategory, 90, 50, 200, juce::TableHeaderComponent::defaultFlags);
    header.addColumn("KEY", colKey, 50, 40, 100, juce::TableHeaderComponent::defaultFlags);
    header.addColumn("BPM", colBpm, 50, 40, 100, juce::TableHeaderComponent::defaultFlags);
    header.addColumn("LENGTH", colDuration, 60, 50, 110, juce::TableHeaderComponent::defaultFlags);
    header.addColumn("PHYSICS", colAcousticPhysics, 160, 100, 300, juce::TableHeaderComponent::defaultFlags);
    header.setColour(juce::TableHeaderComponent::backgroundColourId, Tokens::surface);
    header.setColour(juce::TableHeaderComponent::textColourId, Tokens::mutedDim);
    header.setColour(juce::TableHeaderComponent::outlineColourId, Tokens::border);
    
    table.setColour(juce::ListBox::backgroundColourId, Tokens::background);
    table.setColour(juce::ListBox::outlineColourId, Tokens::border);
    table.setColour(juce::ListBox::textColourId, Tokens::foreground);
    // The table's own scrollbar was never given a colour, so it rendered in
    // JUCE's stock blue -- against the warm near-black it was the single
    // loudest cool element on screen. Neutral chrome, not an accent.
    table.getVerticalScrollBar().setColour(juce::ScrollBar::thumbColourId, Tokens::borderStrong);
    table.getHorizontalScrollBar().setColour(juce::ScrollBar::thumbColourId, Tokens::borderStrong);
    table.setRowHeight(Tokens::controlHeight); // High-density scanning row height
    table.setMultipleSelectionEnabled(false);
    table.addMouseListener(this, true);
    table.setVisible(false);
}

void PrecisionBrowser::updateSamples(const std::vector<SampleItem>& newSamples)
{
    if (!selectedFilePath.empty())
    {
        const bool stillInLibrary = std::any_of(newSamples.begin(), newSamples.end(),
            [this](const SampleItem& item) { return item.filePath == selectedFilePath; });
        if (!stillInLibrary)
            selectedFilePath.clear();
    }
    allSamples = newSamples;
    setSearchQuery(searchQueryLower);
}

void PrecisionBrowser::setSearchQuery(const juce::String& query)
{
    // Selection is path-based rather than row-based so it survives a filter
    // transition where the selected sample is temporarily not visible.
    const auto selectedPath = juce::String(selectedFilePath);

    searchQueryLower = query.trim().toLowerCase();
    samples.clear();
    samples.reserve(allSamples.size());

    for (const auto& item : allSamples)
    {
        const auto categoryText = ClassificationPresentation::filterText(
            item.category, item.subcategory, item.instrumentType, item.tagSource);
        bool categoryMatches = !categoryFilterActive;
        if (categoryFilterActive && !filteredCategories.empty()) {
            for (const auto& activeCategory : filteredCategories) {
                if (ClassificationPresentation::matchesCategoryFilter(categoryText, activeCategory)) {
                    categoryMatches = true;
                    break;
                }
            }
        }
        if (!categoryMatches)
            continue;

        juce::String searchable = juce::String(item.name) + " " + item.key + " "
            + item.category + " " + item.subcategory + " " + item.instrumentType + " "
            + juce::String(static_cast<int>(item.bpm)) + " "
            + juce::String(item.audioFeatures.physics.physicalClass) + " "
            + juce::String(item.audioFeatures.physics.physicalBadge);
        for (const auto& tag : item.secondaryTags)
            searchable += " " + juce::String(tag);
        if (SloSearchLexicon::matches(searchable, searchQueryLower))
            samples.push_back(item);
    }

    applySort();

    selectedRow = -1;
    if (selectedPath.isNotEmpty())
    {
        for (size_t i = 0; i < samples.size(); ++i)
        {
            if (samples[i].filePath == selectedPath.toStdString())
            {
                selectedRow = static_cast<int>(i);
                break;
            }
        }
    }
    table.updateContent();
    table.setVisible(!samples.empty());
    if (selectedRow >= 0)
        table.selectRow(selectedRow, false, false);
    table.repaint();

    if (samples.empty())
    {
        const bool trulyEmpty = allSamples.empty() && searchQueryLower.isEmpty()
            && filteredCategories.empty();
        summaryLabel.setText(trulyEmpty
            ? "No samples yet — scan a library folder to begin."
            : "No matching samples — refine or clear search or category filters.",
            juce::dontSendNotification);
        summaryLabel.setColour(juce::Label::textColourId, Tokens::muted);
    }
    else
    {
        auto summary = juce::String(samples.size()) + " of " + juce::String(allSamples.size()) + " samples";
        // All category pills start enabled, so their vector being non-empty is
        // not itself evidence that the view is narrowed. Report "filtered"
        // only when the visible row count actually excludes library entries.
        const bool categoryActuallyFilters = categoryFilterActive
            && samples.size() < allSamples.size();
        if (searchQueryLower.isNotEmpty() || categoryActuallyFilters) summary += " - filtered";
        summaryLabel.setText(summary, juce::dontSendNotification);
        summaryLabel.setColour(juce::Label::textColourId, Tokens::mutedDim);
    }
}

void PrecisionBrowser::setFilteredCategories(const std::vector<std::string>& activeCategories)
{
    // Preserve the simple public/test call contract: a non-empty list narrows
    // the view, while an empty list means the default unfiltered view.
    setFilteredCategories(activeCategories, !activeCategories.empty());
}

void PrecisionBrowser::setFilteredCategories(const std::vector<std::string>& activeCategories,
                                              bool filterActive)
{
    filteredCategories = activeCategories;
    categoryFilterActive = filterActive;
    setSearchQuery(searchQueryLower);
}

void PrecisionBrowser::setSelectedCallback(std::function<void(const SampleItem&)> callback)
{
    onSelect = std::move(callback);
}

void PrecisionBrowser::setDoubleClickedCallback(std::function<void(const SampleItem&)> callback)
{
    onDoubleClick = std::move(callback);
}

void PrecisionBrowser::setEmptyStateActionCallback(std::function<void()> callback)
{
    onEmptyStateAction = std::move(callback);
}

SampleItem PrecisionBrowser::getSelectedItem() const
{
    if (selectedRow >= 0 && selectedRow < static_cast<int>(samples.size()))
        return samples[static_cast<size_t>(selectedRow)];
    return {};
}

bool PrecisionBrowser::hasSelection() const
{
    return selectedRow >= 0 && selectedRow < static_cast<int>(samples.size());
}

bool PrecisionBrowser::isSampleVisible(const juce::String& filePath) const
{
    const auto target = filePath.toStdString();
    return std::any_of(samples.begin(), samples.end(),
        [&target](const SampleItem& item) { return item.filePath == target; });
}

void PrecisionBrowser::selectRow(int rowNumber)
{
    if (rowNumber >= 0 && rowNumber < static_cast<int>(samples.size()))
    {
        selectedRow = rowNumber;
        selectedFilePath = samples[static_cast<size_t>(selectedRow)].filePath;
        table.selectRow(rowNumber, false, true);
        if (onSelect)
            onSelect(samples[static_cast<size_t>(selectedRow)]);
    }
}

bool PrecisionBrowser::selectRelative(int rowDelta)
{
    if (samples.empty() || rowDelta == 0)
        return false;

    const int rowCount = static_cast<int>(samples.size());
    const int target = selectedRow < 0
        ? (rowDelta > 0 ? 0 : rowCount - 1)
        : juce::jlimit(0, rowCount - 1, selectedRow + rowDelta);

    if (target == selectedRow)
        return false;

    selectRow(target);
    return true;
}

void PrecisionBrowser::selectSampleByPath(const juce::String& filePath)
{
    for (size_t i = 0; i < samples.size(); ++i)
    {
        if (samples[i].filePath == filePath.toStdString())
        {
            selectRow(static_cast<int>(i));
            break;
        }
    }
}

int PrecisionBrowser::getNumRows()
{
    return static_cast<int>(samples.size());
}

void PrecisionBrowser::paintRowBackground(juce::Graphics& g, int rowNumber, int width, int height, bool rowIsSelected)
{
    if (rowIsSelected)
    {
        g.fillAll(Tokens::selection);
        g.setColour(Tokens::accentInteractive);
        g.drawVerticalLine(0, 0.0f, static_cast<float>(height));
    }
    else if (rowNumber % 2 == 0)
    {
        g.fillAll(Tokens::surfaceRaised.withAlpha(0.3f));
    }
}

void PrecisionBrowser::paintCell(juce::Graphics& g, int rowNumber, int columnId, int width, int height, bool rowIsSelected)
{
    if (rowNumber < 0 || rowNumber >= static_cast<int>(samples.size()))
        return;

    const auto& item = samples[static_cast<size_t>(rowNumber)];
    g.setColour(Tokens::foreground);
    g.setFont(juce::Font(juce::FontOptions().withHeight(Tokens::fontBody)));
    
    juce::Rectangle<int> bounds(4, 0, width - 8, height);

    switch (columnId)
    {
        case colPlayState:
        {
            // Draw a clean, crisp vector play triangle in the center
            float w = 8.0f;
            float h = 10.0f;
            float x = (static_cast<float>(width) - w) / 2.0f;
            float y = (static_cast<float>(height) - h) / 2.0f;
            
            juce::Path p;
            p.addTriangle(x, y, x, y + h, x + w, y + (h / 2.0f));
            
            g.setColour(rowIsSelected ? Tokens::accentInteractive : Tokens::mutedDim);
            g.fillPath(p);
            break;
        }
        case colFavorite:
        {
            bool fav = engine.isFavorite(item.filePath);
            g.setColour(fav ? Tokens::favorite : Tokens::mutedDim.withAlpha(0.25f));
            
            // Draw a clean vector star icon
            float cx = static_cast<float>(width) / 2.0f;
            float cy = static_cast<float>(height) / 2.0f;
            float rOuter = 6.0f;
            float rInner = 2.5f;
            
            juce::Path p;
            p.startNewSubPath(cx, cy - rOuter);
            for (int i = 1; i < 10; ++i)
            {
                float angle = static_cast<float>(i) * juce::MathConstants<float>::pi / 5.0f;
                float r = (i % 2 == 0) ? rOuter : rInner;
                p.lineTo(cx + r * std::sin(angle), cy - r * std::cos(angle));
            }
            p.closeSubPath();
            
            if (fav)
                g.fillPath(p);
            else
                g.strokePath(p, juce::PathStrokeType(1.0f));
            break;
        }
        case colFilename:
        {
            g.setFont(juce::Font(juce::FontOptions().withHeight(Tokens::fontBody)));
            g.drawFittedText(item.name, bounds, juce::Justification::centredLeft, 1);
            break;
        }
        case colCategory:
        {
            // Rows are admitted to the browser before the background DSP/AI
            // pass finishes. A bare dash looked like missing metadata and
            // made an active scan feel stalled; make the transient state
            // explicit while keeping failure states distinct below.
            if (!item.isProcessed
                && item.embeddingStatus == EmbeddingStatus::NotAnalysed)
            {
                g.setColour(Tokens::accentInteractive);
                g.drawFittedText("ANALYSING", bounds, juce::Justification::centredLeft, 1);
                break;
            }

            const bool embeddingFailed = item.embeddingStatus == EmbeddingStatus::FailedRetryable
                || item.embeddingStatus == EmbeddingStatus::FailedPermanent;
            if (embeddingFailed)
            {
                g.setColour(Tokens::danger);
                const auto failureLabel = item.embeddingStatus == EmbeddingStatus::FailedPermanent
                    ? juce::String("AI FAILED") : juce::String("AI RETRY");
                g.drawFittedText(failureLabel, bounds, juce::Justification::centredLeft, 1);
                break;
            }

            g.setColour(Tokens::mutedDim);
            const auto label = ClassificationPresentation::primaryLabel(
                item.category, item.subcategory, item.instrumentType, item.tagSource);
            g.drawFittedText(label.empty() ? "-" : label, bounds, juce::Justification::centredLeft, 1);
            break;
        }
        case colKey:
        {
            g.setColour(Tokens::muted);
            const bool oneShot = item.subcategory.find("Loop") == std::string::npos
                && item.subcategory.find("loop") == std::string::npos;
            const auto keyLabel = formatKeyForSampleName(juce::String(item.key), oneShot);
            g.drawFittedText(keyLabel.isEmpty() ? "-" : keyLabel, bounds,
                             juce::Justification::centredLeft, 1);
            break;
        }
        case colBpm:
        {
            g.setColour(Tokens::muted);
            const auto bpmLabel = item.bpm > 0.0f
                ? juce::String(static_cast<int>(std::round(item.bpm)))
                : juce::String("-");
            g.drawFittedText(bpmLabel, bounds, juce::Justification::centredLeft, 1);
            break;
        }
        case colDuration:
        {
            g.setColour(Tokens::mutedDim);
            g.drawFittedText(juce::String(item.durationSeconds, 2) + "s", bounds, juce::Justification::centredLeft, 1);
            break;
        }
        case colAcousticPhysics:
        {
            g.setColour(Tokens::electricCyan);
            juce::String badge = item.audioFeatures.physics.physicalBadge;
            if (badge.isEmpty())
                badge = item.audioFeatures.physics.physicalClass;
            if (badge.isEmpty())
                badge = "-";
            g.drawFittedText(badge, bounds, juce::Justification::centredLeft, 1);
            break;
        }
    }
}

void PrecisionBrowser::cellClicked(int rowNumber, int columnId, const juce::MouseEvent& event)
{
    if (rowNumber < 0 || rowNumber >= static_cast<int>(samples.size()))
        return;

    selectedRow = rowNumber;
    const auto& item = samples[static_cast<size_t>(rowNumber)];
    selectedFilePath = item.filePath;
    
    if (columnId == colPlayState)
    {
        if (onDoubleClick)
            onDoubleClick(item);
    }
    else if (columnId == colFavorite)
    {
        bool isFav = engine.isFavorite(item.filePath);
        engine.setFavorite(item.filePath, !isFav);
        table.repaintRow(rowNumber);
    }
    
    if (onSelect)
        onSelect(item);
}

void PrecisionBrowser::cellDoubleClicked(int rowNumber, int columnId, const juce::MouseEvent& event)
{
    if (rowNumber < 0 || rowNumber >= static_cast<int>(samples.size()))
        return;
        
    if (onDoubleClick)
        onDoubleClick(samples[static_cast<size_t>(rowNumber)]);
}

void PrecisionBrowser::deleteKeyPressed(int lastSelectedRow)
{
}

juce::var PrecisionBrowser::getDragSourceDescription(const juce::SparseSet<int>& selectedRows)
{
    // The table's built-in description starts JUCE's internal component drag.
    // Ableton needs a native macOS file drag, initiated by mouseDrag() below.
    return {};
}

void PrecisionBrowser::mouseDrag(const juce::MouseEvent& event)
{
    if (externalDragInProgress || !event.mouseWasDraggedSinceMouseDown() || !hasSelection())
        return;

    const auto file = juce::File(samples[static_cast<size_t>(selectedRow)].filePath);
    if (!file.existsAsFile())
        return;

    externalDragInProgress = juce::DragAndDropContainer::performExternalDragDropOfFiles(
        { file.getFullPathName() }, false, event.eventComponent,
        [this]() { externalDragInProgress = false; });
}

void PrecisionBrowser::paint(juce::Graphics& g)
{
    emptyActionBounds = {};

    // Keep keyboard focus legible at the view boundary, including when the
    // child table owns focus. This mirrors the map's focus ring and avoids a
    // silent change of interaction state when switching LIST/MAP/SPLIT.
    if (hasKeyboardFocus(true) || table.hasKeyboardFocus(true))
    {
        g.setColour(Tokens::focusRing.withAlpha(0.72f));
        g.drawRoundedRectangle(getLocalBounds().toFloat().reduced(1.0f),
                               Tokens::cornerRadiusSm, 1.5f);
    }

    if (!samples.empty())
    {
        emptyActionHovered = false;
        return;
    }

    auto area = getLocalBounds().reduced(24);
    area.removeFromTop(Tokens::controlHeightCompact);
    const int cardWidth = juce::jmin(520, juce::jmax(240, area.getWidth() - 16));
    const int cardHeight = juce::jmin(172, juce::jmax(138, area.getHeight() - 24));
    const auto card = area.withSizeKeepingCentre(cardWidth, cardHeight);

    g.setColour(Tokens::surface);
    g.fillRoundedRectangle(card.toFloat(), Tokens::cornerRadiusLg);
    g.setColour(Tokens::border);
    g.drawRoundedRectangle(card.toFloat().reduced(0.5f), Tokens::cornerRadiusLg, 1.0f);

    const bool scanning = engine.isBusy();
    const bool libraryEmpty = allSamples.empty();
    const auto centre = card.getCentre();
    g.setColour(scanning ? Tokens::accentInteractive : Tokens::muted);
    g.drawEllipse(static_cast<float>(centre.x - 16), static_cast<float>(centre.y - 45), 32.0f, 32.0f, 2.0f);
    g.setColour(scanning ? Tokens::accentInteractive : Tokens::mutedDim);
    g.fillEllipse(static_cast<float>(centre.x - 4), static_cast<float>(centre.y - 33), 8.0f, 8.0f);

    const juce::String title = scanning ? "SCANNING LIBRARY"
        : libraryEmpty ? "LIBRARY EMPTY" : "NO MATCHES";
    const juce::String hint = scanning ? "Analysing samples — this view will update automatically."
        : libraryEmpty ? "Drop audio here or scan a folder to build your library."
                       : "Try a broader search or clear the filter to see more samples.";

    g.setColour(Tokens::foreground);
    g.setFont(juce::Font(juce::FontOptions().withHeight(12.0f).withStyle("Bold")));
    g.drawFittedText(title, card.withTrimmedTop(56).withHeight(22), juce::Justification::centred, 1);
    g.setColour(Tokens::muted);
    g.setFont(juce::Font(juce::FontOptions().withHeight(11.0f)));
    g.drawFittedText(hint, card.withTrimmedTop(82).withTrimmedBottom(libraryEmpty && !scanning ? 48 : 18),
                     juce::Justification::centred, 2);

    if (libraryEmpty && !scanning)
    {
        emptyActionBounds = card.withSizeKeepingCentre(132, 24);
        emptyActionBounds.setY(card.getBottom() - emptyActionBounds.getHeight() - 12);
        g.setColour(emptyActionHovered ? Tokens::surfaceHover : Tokens::surfaceRaised);
        g.fillRoundedRectangle(emptyActionBounds.toFloat(), Tokens::cornerRadiusSm);
        g.setColour(emptyActionHovered ? Tokens::foreground : Tokens::accentInteractive);
        g.drawRoundedRectangle(emptyActionBounds.toFloat().reduced(0.5f), Tokens::cornerRadiusSm, 1.0f);
        g.setColour(Tokens::foreground);
        g.setFont(juce::Font(juce::FontOptions().withHeight(10.0f).withStyle("Bold")));
        g.drawFittedText("SCAN LIBRARY", emptyActionBounds, juce::Justification::centred, 1);
    }
}

void PrecisionBrowser::mouseDown(const juce::MouseEvent& event)
{
    if (allSamples.empty() && samples.empty() && emptyActionBounds.contains(event.position.toInt()))
    {
        grabKeyboardFocus();
        if (onEmptyStateAction)
            onEmptyStateAction();
    }
}

void PrecisionBrowser::mouseMove(const juce::MouseEvent& event)
{
    if (!allSamples.empty() || !samples.empty())
        return;

    const bool wasHovered = emptyActionHovered;
    emptyActionHovered = emptyActionBounds.contains(event.position.toInt());
    setMouseCursor(emptyActionHovered ? juce::MouseCursor::PointingHandCursor
                                       : juce::MouseCursor::NormalCursor);
    if (emptyActionHovered != wasHovered)
        repaint();
}

void PrecisionBrowser::mouseExit(const juce::MouseEvent& event)
{
    juce::ignoreUnused(event);
    if (!emptyActionHovered)
        return;
    emptyActionHovered = false;
    setMouseCursor(juce::MouseCursor::NormalCursor);
    repaint();
}

void PrecisionBrowser::resized()
{
    auto bounds = getLocalBounds();
    summaryLabel.setBounds(bounds.removeFromTop(Tokens::controlHeightCompact));
    table.setBounds(bounds);
}

void PrecisionBrowser::sortOrderChanged(int newSortColumnId, bool isAscending)
{
    if (newSortColumnId != currentSortColumnId || isAscending != currentSortAscending)
    {
        currentSortColumnId = newSortColumnId;
        currentSortAscending = isAscending;
        
        // Preserve selection
        const auto selectedPath = juce::String(selectedFilePath);
            
        applySort();
        
        // Restore selection row index
        selectedRow = -1;
        if (selectedPath.isNotEmpty())
        {
            for (size_t i = 0; i < samples.size(); ++i)
            {
                if (samples[i].filePath == selectedPath.toStdString())
                {
                    selectedRow = static_cast<int>(i);
                    break;
                }
            }
        }
        
        table.updateContent();
        if (selectedRow >= 0)
            table.selectRow(selectedRow, false, false);
        table.repaint();
    }
}

static int getKeyPriority(const std::string& key)
{
    // Custom musical sorting ordering: Circle of Fifths / Camelot-like values order or chromatic base
    // A standard minor/major structured mapping:
    // C Major, G Major, D Major, A Major, E Major, B Major, F# Major, C# Major, G# Major, D# Major, A# Major, F Major
    // C Minor, G Minor, D Minor, A Minor, E Minor, B Minor, F# Minor, C# Minor, G# Minor, D# Minor, A# Minor, F Minor
    // Let's define a clean chromatic base so it's musically intuitive and stable
    static const std::vector<std::string> orderedKeys = {
        "C Major", "C# Major", "D Major", "D# Major", "E Major", "F Major", "F# Major", "G Major", "G# Major", "A Major", "A# Major", "B Major",
        "C Minor", "C# Minor", "D Minor", "D# Minor", "E Minor", "F Minor", "F# Minor", "G Minor", "G# Minor", "A Minor", "A# Minor", "B Minor"
    };
    
    for (size_t i = 0; i < orderedKeys.size(); ++i)
    {
        if (juce::String(key).equalsIgnoreCase(juce::String(orderedKeys[i])))
            return static_cast<int>(i);
    }
    return 999; // Unknown keys at the bottom
}

void PrecisionBrowser::applySort()
{
    if (currentSortColumnId < 0)
        return;
        
    bool ascending = currentSortAscending;
    int colId = currentSortColumnId;
    
    std::sort(samples.begin(), samples.end(), [colId, ascending](const SampleItem& a, const SampleItem& b) {
        bool comparisonResult = false;
        
        switch (colId)
        {
            case colFilename:
            {
                int cmp = juce::String(a.name).compareIgnoreCase(b.name);
                if (cmp != 0)
                    comparisonResult = (cmp < 0);
                else
                    comparisonResult = a.filePath < b.filePath; // fallback stable order
                break;
            }
            case colCategory:
            {
                std::string catA = a.category.empty() ? "zzz" : a.category;
                std::string catB = b.category.empty() ? "zzz" : b.category;
                int cmp = juce::String(catA).compareIgnoreCase(catB);
                if (cmp != 0)
                    comparisonResult = (cmp < 0);
                else
                    comparisonResult = a.filePath < b.filePath;
                break;
            }
            case colKey:
            {
                int prioA = getKeyPriority(a.key);
                int prioB = getKeyPriority(b.key);
                if (prioA != prioB)
                    comparisonResult = (prioA < prioB);
                else
                    comparisonResult = a.filePath < b.filePath;
                break;
            }
            case colBpm:
            {
                if (std::abs(a.bpm - b.bpm) > 0.001f)
                    comparisonResult = (a.bpm < b.bpm);
                else
                    comparisonResult = a.filePath < b.filePath;
                break;
            }
            case colDuration:
            {
                if (std::abs(a.durationSeconds - b.durationSeconds) > 0.001f)
                    comparisonResult = (a.durationSeconds < b.durationSeconds);
                else
                    comparisonResult = a.filePath < b.filePath;
                break;
            }
            case colAcousticPhysics:
            {
                std::string physA = a.audioFeatures.physics.physicalBadge.empty() ? a.audioFeatures.physics.physicalClass : a.audioFeatures.physics.physicalBadge;
                std::string physB = b.audioFeatures.physics.physicalBadge.empty() ? b.audioFeatures.physics.physicalClass : b.audioFeatures.physics.physicalBadge;
                int cmp = juce::String(physA).compareIgnoreCase(physB);
                if (cmp != 0)
                    comparisonResult = (cmp < 0);
                else
                    comparisonResult = a.filePath < b.filePath;
                break;
            }
            default:
                return false;
        }
        
        return ascending ? comparisonResult : !comparisonResult;
    });
}
