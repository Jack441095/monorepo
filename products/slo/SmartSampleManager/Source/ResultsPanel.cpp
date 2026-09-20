#include "ResultsPanel.h"
#include "DesignTokens.h"

#include <algorithm>

ResultsPanel::ResultsPanel()
{
    setWantsKeyboardFocus(true);

    titleLabel.setFont(juce::Font(juce::FontOptions().withHeight(16.0f).withStyle("Bold")));
    titleLabel.setColour(juce::Label::textColourId, Tokens::foreground);
    addAndMakeVisible(titleLabel);

    closeButton.setButtonText("CLOSE");
    closeButton.setColour(juce::TextButton::buttonColourId, Tokens::surfaceRaised);
    closeButton.setColour(juce::TextButton::textColourOffId, Tokens::muted);
    closeButton.setTooltip("Close this results panel (Escape)");
    closeButton.onClick = [this]() { if (onClose) onClose(); };
    addAndMakeVisible(closeButton);

    listBox.setModel(this);
    listBox.setRowHeight(44);
    listBox.setColour(juce::ListBox::backgroundColourId, Tokens::surface);
    listBox.setColour(juce::ListBox::outlineColourId, Tokens::border);
    listBox.getVerticalScrollBar().setColour(juce::ScrollBar::thumbColourId, Tokens::borderStrong);
    addAndMakeVisible(listBox);

    // Refinement strip -- built but not shown until setRefinementVisible(true).
    refinementHeading.setText("REFINE RESULTS", juce::dontSendNotification);
    refinementHeading.setFont(juce::Font(juce::FontOptions().withHeight(Tokens::fontLabel).withStyle("Bold")));
    refinementHeading.setColour(juce::Label::textColourId, Tokens::mutedDim);
    addChildComponent(refinementHeading);

    auto setupRefineSlider = [this](juce::Label& label, juce::Slider& slider, const juce::String& text) {
        label.setText(text, juce::dontSendNotification);
        label.setFont(juce::Font(juce::FontOptions().withHeight(Tokens::fontLabel)));
        label.setColour(juce::Label::textColourId, Tokens::mutedDim);
        label.setJustificationType(juce::Justification::centred);
        addChildComponent(label);

        slider.setSliderStyle(juce::Slider::LinearHorizontal);
        slider.setRange(-1.0, 1.0, 0.01);
        slider.setValue(0.0, juce::dontSendNotification);
        slider.setTextBoxStyle(juce::Slider::NoTextBox, true, 0, 0);
        slider.setColour(juce::Slider::backgroundColourId, Tokens::surfaceRaised);
        slider.setColour(juce::Slider::trackColourId, Tokens::border);
        slider.setColour(juce::Slider::thumbColourId, Tokens::foreground);
        slider.onValueChange = [this]() { fireRefinementChanged(); };
        addChildComponent(slider);
    };
    setupRefineSlider(brightnessLabel, brightnessSlider, "TONE (Dark ↔ Bright)");
    setupRefineSlider(punchLabel, punchSlider, "ATTACK (Soft ↔ Punchy)");
    setupRefineSlider(noiseLabel, noiseSlider, "TEXTURE (Clean ↔ Noisy)");

    resetRefinementButton.setButtonText("RESET");
    resetRefinementButton.setColour(juce::TextButton::buttonColourId, Tokens::surfaceRaised);
    resetRefinementButton.setColour(juce::TextButton::textColourOffId, Tokens::mutedDim);
    resetRefinementButton.setTooltip("Reset tone, attack, and texture refinement");
    resetRefinementButton.onClick = [this]() { resetRefinement(); };
    addChildComponent(resetRefinementButton);

    // Aspect retrieval strip -- the controls mirror the independent ratings
    // shown in each result row. They are hidden until a caller presents an
    // aspect-scored result set, so duplicate/favourites/history panels keep
    // their existing compact layout.
    aspectHeading.setText("SOUND DNA SIMILARITY ASPECTS", juce::dontSendNotification);
    aspectHeading.setFont(juce::Font(juce::FontOptions().withHeight(Tokens::fontLabel).withStyle("Bold")));
    aspectHeading.setColour(juce::Label::textColourId, Tokens::mutedDim);
    addChildComponent(aspectHeading);

    const std::array<juce::String, 6> aspectNames = {
        "EMBED", "SPECTRUM", "PITCH", "MATERIAL", "IMPACT", "STIFFNESS"
    };
    for (size_t i = 0; i < aspectSliders.size(); ++i) {
        auto& label = aspectLabels[i];
        auto& slider = aspectSliders[i];
        label.setText(aspectNames[i], juce::dontSendNotification);
        label.setFont(juce::Font(juce::FontOptions().withHeight(Tokens::fontLabel)));
        label.setColour(juce::Label::textColourId, Tokens::mutedDim);
        label.setJustificationType(juce::Justification::centred);
        addChildComponent(label);

        slider.setSliderStyle(juce::Slider::LinearHorizontal);
        slider.setRange(0.0, 2.0, 0.01);
        slider.setValue(1.0, juce::dontSendNotification);
        slider.setTextBoxStyle(juce::Slider::NoTextBox, true, 0, 0);
        slider.setColour(juce::Slider::backgroundColourId, Tokens::surfaceRaised);
        slider.setColour(juce::Slider::trackColourId, Tokens::border);
        slider.setColour(juce::Slider::thumbColourId, Tokens::foreground);
        slider.setTooltip(aspectNames[i] + " weight (0 disables this aspect)");
        slider.onValueChange = [this]() { fireAspectWeightsChanged(); };
        addChildComponent(slider);
    }

    resetAspectButton.setButtonText("RESET");
    resetAspectButton.setColour(juce::TextButton::buttonColourId, Tokens::surfaceRaised);
    resetAspectButton.setColour(juce::TextButton::textColourOffId, Tokens::mutedDim);
    resetAspectButton.setTooltip("Restore equal weighting for every similarity aspect");
    resetAspectButton.onClick = [this]() {
        silentlyResetAspectWeights();
        fireAspectWeightsChanged();
    };
    addChildComponent(resetAspectButton);
}

bool ResultsPanel::keyPressed(const juce::KeyPress& key)
{
    if (key == juce::KeyPress::escapeKey)
    {
        if (onClose) onClose();
        return true;
    }
    return false;
}

void ResultsPanel::setContent(const juce::String& title, const std::vector<Row>& newRows)
{
    titleLabel.setText(title, juce::dontSendNotification);
    rows = newRows;
    lastNotifiedRow = -1;
    emptyStateMessage = (title.containsIgnoreCase("review queue") || title.containsIgnoreCase("unknown queue"))
        ? (title.containsIgnoreCase("unknown")
            ? "No unknown samples — everything matched the known taxonomy."
            : "No samples need review right now.")
        : "No results for this view.";
    const bool hasAspectRows = std::any_of(rows.begin(), rows.end(),
        [](const Row& row) { return row.aspects.valid; });
    listBox.setRowHeight(hasAspectRows ? 58 : 44);
    listBox.setVisible(!rows.empty());
    listBox.updateContent();
    listBox.repaint();
}

void ResultsPanel::setRowSelectedCallback(std::function<void(const juce::String&)> callback)
{
    onRowSelected = std::move(callback);
}

void ResultsPanel::setCloseCallback(std::function<void()> callback)
{
    onClose = std::move(callback);
}

void ResultsPanel::setRefinementVisible(bool shouldBeVisible)
{
    refinementVisible = shouldBeVisible;
    refinementHeading.setVisible(shouldBeVisible);
    brightnessLabel.setVisible(shouldBeVisible);
    brightnessSlider.setVisible(shouldBeVisible);
    punchLabel.setVisible(shouldBeVisible);
    punchSlider.setVisible(shouldBeVisible);
    noiseLabel.setVisible(shouldBeVisible);
    noiseSlider.setVisible(shouldBeVisible);
    resetRefinementButton.setVisible(shouldBeVisible);
    resized();
}

void ResultsPanel::resetRefinement()
{
    silentlyResetRefinementSliders();
    fireRefinementChanged();
}

void ResultsPanel::silentlyResetRefinementSliders()
{
    brightnessSlider.setValue(0.0, juce::dontSendNotification);
    punchSlider.setValue(0.0, juce::dontSendNotification);
    noiseSlider.setValue(0.0, juce::dontSendNotification);
}

void ResultsPanel::setRefinementChangedCallback(std::function<void(float, float, float)> callback)
{
    onRefinementChanged = std::move(callback);
}

void ResultsPanel::setAspectControlsVisible(bool shouldBeVisible)
{
    aspectControlsVisible = shouldBeVisible;
    aspectHeading.setVisible(shouldBeVisible);
    for (size_t i = 0; i < aspectLabels.size(); ++i) {
        aspectLabels[i].setVisible(shouldBeVisible);
        aspectSliders[i].setVisible(shouldBeVisible);
    }
    resetAspectButton.setVisible(shouldBeVisible);
    resized();
}

void ResultsPanel::silentlyResetAspectWeights()
{
    for (auto& slider : aspectSliders)
        slider.setValue(1.0, juce::dontSendNotification);
}

void ResultsPanel::setAspectWeightsChangedCallback(
    std::function<void(float, float, float, float, float, float)> callback)
{
    onAspectWeightsChanged = std::move(callback);
}

void ResultsPanel::fireAspectWeightsChanged()
{
    if (!onAspectWeightsChanged) return;
    onAspectWeightsChanged(static_cast<float>(aspectSliders[0].getValue()),
                           static_cast<float>(aspectSliders[1].getValue()),
                           static_cast<float>(aspectSliders[2].getValue()),
                           static_cast<float>(aspectSliders[3].getValue()),
                           static_cast<float>(aspectSliders[4].getValue()),
                           static_cast<float>(aspectSliders[5].getValue()));
}

void ResultsPanel::fireRefinementChanged()
{
    if (onRefinementChanged) {
        onRefinementChanged(static_cast<float>(brightnessSlider.getValue()),
                             static_cast<float>(punchSlider.getValue()),
                             static_cast<float>(noiseSlider.getValue()));
    }
}

void ResultsPanel::paint(juce::Graphics& g)
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

    if (rows.empty())
    {
        const auto emptyArea = getLocalBounds().reduced(24).withTrimmedTop(52);
        g.setColour(Tokens::muted);
        g.drawEllipse(static_cast<float>(emptyArea.getCentreX() - 15),
                      static_cast<float>(emptyArea.getCentreY() - 28), 30.0f, 30.0f, 2.0f);
        g.setColour(Tokens::foreground);
        g.setFont(juce::Font(juce::FontOptions().withHeight(12.0f).withStyle("Bold")));
        g.drawFittedText("ALL CLEAR", emptyArea.withTrimmedTop(40).withHeight(22),
                         juce::Justification::centred, 1);
        g.setColour(Tokens::muted);
        g.setFont(juce::Font(juce::FontOptions().withHeight(11.0f)));
        g.drawFittedText(emptyStateMessage, emptyArea.withTrimmedTop(68).withTrimmedBottom(8),
                         juce::Justification::centred, 2);
    }
}

void ResultsPanel::resized()
{
    auto area = getLocalBounds().reduced(12);
    auto headerRow = area.removeFromTop(28);
    closeButton.setBounds(headerRow.removeFromRight(70));
    titleLabel.setBounds(headerRow);
    area.removeFromTop(8);

    if (refinementVisible) {
        refinementHeading.setBounds(area.removeFromTop(16));
        area.removeFromTop(2);

        auto sliderRow = area.removeFromTop(38);
        int sliderW = (sliderRow.getWidth() - 80 - 16) / 3; // 3 sliders + reset button + 2 gaps
        auto layoutOne = [&sliderRow, sliderW](juce::Label& label, juce::Slider& slider) {
            auto col = sliderRow.removeFromLeft(sliderW);
            label.setBounds(col.removeFromTop(14));
            slider.setBounds(col);
        };
        layoutOne(brightnessLabel, brightnessSlider);
        sliderRow.removeFromLeft(8);
        layoutOne(punchLabel, punchSlider);
        sliderRow.removeFromLeft(8);
        layoutOne(noiseLabel, noiseSlider);
        sliderRow.removeFromLeft(8);
        resetRefinementButton.setBounds(sliderRow.removeFromTop(24));

        area.removeFromTop(8);
    }

    if (aspectControlsVisible) {
        aspectHeading.setBounds(area.removeFromTop(16));
        area.removeFromTop(2);

        constexpr int resetWidth = 64;
        constexpr int gap = 6;
        const bool compactAspects = getWidth() < 620;
        if (compactAspects) {
            // Six columns at compact widths turn the labels into unreadable
            // ellipses. Two rows of three preserve a practical touch target
            // while keeping the list itself visible below the controls.
            for (size_t rowIndex = 0; rowIndex < 2; ++rowIndex) {
                auto sliderRow = area.removeFromTop(38);
                const int sliderW = std::max(56, (sliderRow.getWidth() - gap * 2) / 3);
                for (size_t colIndex = 0; colIndex < 3; ++colIndex) {
                    const size_t index = rowIndex * 3 + colIndex;
                    auto col = sliderRow.removeFromLeft(sliderW);
                    aspectLabels[index].setBounds(col.removeFromTop(14));
                    aspectSliders[index].setBounds(col);
                    if (colIndex < 2) sliderRow.removeFromLeft(gap);
                }
                if (rowIndex == 0) area.removeFromTop(4);
            }
            resetAspectButton.setBounds(area.removeFromTop(24).withWidth(resetWidth));
        } else {
            auto sliderRow = area.removeFromTop(38);
            const int sliderW = std::max(30, (sliderRow.getWidth() - resetWidth - gap * 6) / 6);
            for (size_t i = 0; i < aspectSliders.size(); ++i) {
                auto col = sliderRow.removeFromLeft(sliderW);
                aspectLabels[i].setBounds(col.removeFromTop(14));
                aspectSliders[i].setBounds(col);
                if (i + 1 < aspectSliders.size()) sliderRow.removeFromLeft(gap);
            }
            sliderRow.removeFromLeft(gap);
            resetAspectButton.setBounds(sliderRow.removeFromTop(24));
        }
        area.removeFromTop(8);
    }

    listBox.setBounds(area);
}

int ResultsPanel::getNumRows()
{
    return static_cast<int>(rows.size());
}

void ResultsPanel::paintListBoxItem(int rowNumber, juce::Graphics& g, int width, int height, bool rowIsSelected)
{
    if (rowNumber < 0 || rowNumber >= static_cast<int>(rows.size())) return;
    const auto& row = rows[static_cast<size_t>(rowNumber)];
    const bool selectable = row.filePath.isNotEmpty();

    if (rowIsSelected && selectable) {
        g.setColour(Tokens::surfaceRaised);
        g.fillRect(0, 0, width, height);
    }

    auto bounds = juce::Rectangle<int>(0, 0, width, height).reduced(12, 4);

    g.setColour(selectable ? Tokens::foreground
                            : Tokens::mutedDim); // informational rows
    g.setFont(juce::Font(juce::FontOptions().withHeight(14.0f)));
    g.drawFittedText(row.primaryText, bounds.removeFromTop(height / 2), juce::Justification::centredLeft, 1);

    g.setColour(Tokens::mutedDim);
    g.setFont(juce::Font(juce::FontOptions().withHeight(12.0f)));
    if (row.aspects.valid) {
        const auto scoreText = "overall " + juce::String(row.aspects.overall, 2)
            + "  ·  embed " + juce::String(row.aspects.embedding, 2)
            + "  ·  pitch " + juce::String(row.aspects.pitch, 2)
            + "  ·  mat " + juce::String(row.aspects.material, 2)
            + "  ·  impact " + juce::String(row.aspects.impact, 2)
            + "  ·  stiff " + juce::String(row.aspects.stiffness, 2);
        g.drawFittedText(row.secondaryText, bounds.removeFromTop(bounds.getHeight() / 2),
                         juce::Justification::centredLeft, 1);
        g.setColour(Tokens::accentInteractive);
        g.drawFittedText(scoreText, bounds, juce::Justification::centredLeft, 1);
    } else {
        g.drawFittedText(row.secondaryText, bounds, juce::Justification::centredLeft, 1);
    }
}

void ResultsPanel::listBoxItemClicked(int row, const juce::MouseEvent& e)
{
    if (row < 0 || row >= static_cast<int>(rows.size())) return;
    const auto& r = rows[static_cast<size_t>(row)];
    if (r.filePath.isEmpty()) return;

    if (e.mods.isPopupMenu()) {
        if (onRowRightClicked) onRowRightClicked(r.filePath);
    }
}

void ResultsPanel::selectedRowsChanged(int lastRowSelected)
{
    if (lastRowSelected < 0 || lastRowSelected >= static_cast<int>(rows.size()))
        return;

    const auto& row = rows[static_cast<size_t>(lastRowSelected)];
    if (row.filePath.isEmpty() || lastRowSelected == lastNotifiedRow)
        return;

    lastNotifiedRow = lastRowSelected;
    if (onRowSelected)
        onRowSelected(row.filePath);
}

void ResultsPanel::setRowRightClickedCallback(std::function<void(const juce::String&)> callback)
{
    onRowRightClicked = std::move(callback);
}
