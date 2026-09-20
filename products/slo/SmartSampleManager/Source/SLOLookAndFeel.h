#pragma once

#include <JuceHeader.h>
#include "DesignTokens.h"

// A small, deliberately restrained JUCE look-and-feel for SLO.
//
// JUCE's default LookAndFeel is useful for prototypes, but its bevels,
// gradients, blue scrollbars, and platform-dependent control metrics make a
// dense pro-audio surface feel like a generic utility window.  This class
// keeps the interaction model native while giving every control the same
// sharp, flat material language: warm dark surfaces, one-pixel borders,
// compact type, and a single amber focus/selection accent.
class SLOLookAndFeel final : public juce::LookAndFeel_V4
{
public:
    SLOLookAndFeel()
    {
        setColour(juce::TextButton::buttonColourId, Tokens::surfaceRaised);
        setColour(juce::TextButton::buttonOnColourId, Tokens::selection);
        setColour(juce::TextButton::textColourOffId, Tokens::foreground);
        setColour(juce::TextButton::textColourOnId, Tokens::foreground);
        setColour(juce::ComboBox::backgroundColourId, Tokens::surfaceRaised);
        setColour(juce::ComboBox::outlineColourId, Tokens::border);
        setColour(juce::ComboBox::textColourId, Tokens::foreground);
        setColour(juce::ComboBox::arrowColourId, Tokens::muted);
        setColour(juce::TextEditor::backgroundColourId, Tokens::surfaceRaised);
        setColour(juce::TextEditor::textColourId, Tokens::foreground);
        setColour(juce::TextEditor::outlineColourId, Tokens::border);
        setColour(juce::TextEditor::focusedOutlineColourId, Tokens::focusRing);
        setColour(juce::TextEditor::highlightColourId, Tokens::selection);
        setColour(juce::TextEditor::highlightedTextColourId, Tokens::foreground);
        setColour(juce::PopupMenu::backgroundColourId, Tokens::surface);
        setColour(juce::PopupMenu::textColourId, Tokens::foreground);
        setColour(juce::PopupMenu::highlightedBackgroundColourId, Tokens::selection);
        setColour(juce::PopupMenu::highlightedTextColourId, Tokens::foreground);
        setColour(juce::TooltipWindow::backgroundColourId, Tokens::surfaceRaised);
        setColour(juce::TooltipWindow::textColourId, Tokens::foreground);
        setColour(juce::TooltipWindow::outlineColourId, Tokens::border);
    }

    void drawButtonBackground(juce::Graphics& g, juce::Button& button,
                              const juce::Colour& backgroundColour,
                              bool shouldDrawButtonAsHighlighted,
                              bool shouldDrawButtonAsDown) override
    {
        auto bounds = button.getLocalBounds().toFloat().reduced(0.5f);
        auto fill = backgroundColour;

        if (button.getToggleState())
        {
            const auto onColour = button.findColour(juce::TextButton::buttonOnColourId);
            if (onColour != juce::Colour())
                fill = onColour;
        }

        g.setColour(fill);
        g.fillRoundedRectangle(bounds, Tokens::cornerRadius);

        if (shouldDrawButtonAsHighlighted)
        {
            g.setColour(Tokens::hoverWash);
            g.fillRoundedRectangle(bounds, Tokens::cornerRadius);
        }
        if (shouldDrawButtonAsDown)
        {
            g.setColour(Tokens::pressedWash);
            g.fillRoundedRectangle(bounds, Tokens::cornerRadius);
        }

        const auto border = button.hasKeyboardFocus(true)
            ? Tokens::focusRing
            : (button.getToggleState() ? Tokens::accentInteractive.withAlpha(0.72f)
                                       : Tokens::border);
        g.setColour(border);
        g.drawRoundedRectangle(bounds, Tokens::cornerRadius, button.hasKeyboardFocus(true) ? 1.5f : 1.0f);
    }

    void drawButtonText(juce::Graphics& g, juce::TextButton& button,
                        bool, bool) override
    {
        const auto colour = button.findColour(button.getToggleState()
            ? juce::TextButton::textColourOnId
            : juce::TextButton::textColourOffId);
        g.setColour(colour);
        g.setFont(juce::Font(juce::FontOptions().withHeight(
            button.getHeight() <= Tokens::controlHeightCompact ? 10.0f : 11.0f)
            .withStyle("Bold")));
        g.drawFittedText(button.getButtonText(), button.getLocalBounds().reduced(8, 0),
                         juce::Justification::centred, 1);
    }

    void drawComboBox(juce::Graphics& g, int width, int height, bool isButtonDown,
                      int, int, int, int, juce::ComboBox& box) override
    {
        auto bounds = juce::Rectangle<float>(0.5f, 0.5f,
                                             static_cast<float>(width) - 1.0f,
                                             static_cast<float>(height) - 1.0f);
        g.setColour(box.findColour(juce::ComboBox::backgroundColourId));
        g.fillRoundedRectangle(bounds, Tokens::cornerRadiusSm);

        if (isButtonDown)
        {
            g.setColour(Tokens::pressedWash);
            g.fillRoundedRectangle(bounds, Tokens::cornerRadiusSm);
        }

        g.setColour(box.hasKeyboardFocus(true) ? Tokens::focusRing
                                                : box.findColour(juce::ComboBox::outlineColourId));
        g.drawRoundedRectangle(bounds, Tokens::cornerRadiusSm,
                               box.hasKeyboardFocus(true) ? 1.5f : 1.0f);

        const auto arrowColour = box.findColour(juce::ComboBox::arrowColourId);
        g.setColour(arrowColour);
        const float arrowX = static_cast<float>(width) - 14.0f;
        const float centreY = static_cast<float>(height) * 0.5f;
        juce::Path arrow;
        arrow.addTriangle(arrowX - 3.5f, centreY - 1.5f,
                          arrowX + 3.5f, centreY - 1.5f,
                          arrowX, centreY + 3.0f);
        g.fillPath(arrow);
    }

    void positionComboBoxText(juce::ComboBox& box, juce::Label& label) override
    {
        label.setBounds(8, 0, juce::jmax(0, box.getWidth() - 28), box.getHeight());
        label.setFont(juce::Font(juce::FontOptions().withHeight(11.0f)));
        label.setColour(juce::Label::textColourId,
                        box.findColour(juce::ComboBox::textColourId));
        label.setColour(juce::Label::backgroundColourId, juce::Colours::transparentBlack);
    }

    void drawTextEditorOutline(juce::Graphics& g, int width, int height,
                               juce::TextEditor& editor) override
    {
        const auto bounds = juce::Rectangle<float>(0.5f, 0.5f,
                                                   static_cast<float>(width) - 1.0f,
                                                   static_cast<float>(height) - 1.0f);
        g.setColour(editor.hasKeyboardFocus(true)
            ? editor.findColour(juce::TextEditor::focusedOutlineColourId)
            : editor.findColour(juce::TextEditor::outlineColourId));
        g.drawRoundedRectangle(bounds, Tokens::cornerRadiusSm,
                               editor.hasKeyboardFocus(true) ? 1.5f : 1.0f);
    }

    void drawLinearSlider(juce::Graphics& g, int x, int y, int width, int height,
                          float sliderPos, float minSliderPos, float maxSliderPos,
                          const juce::Slider::SliderStyle style,
                          juce::Slider& slider) override
    {
        const bool horizontal = style == juce::Slider::LinearHorizontal;
        juce::ignoreUnused(minSliderPos, maxSliderPos);
        if (!horizontal && style != juce::Slider::LinearVertical)
            return;

        const float centre = horizontal
            ? static_cast<float>(y) + static_cast<float>(height) * 0.5f
            : static_cast<float>(x) + static_cast<float>(width) * 0.5f;
        const float start = horizontal ? static_cast<float>(x + 5) : static_cast<float>(y + 5);
        const float end = horizontal ? static_cast<float>(x + width - 5) : static_cast<float>(y + height - 5);

        g.setColour(slider.findColour(juce::Slider::backgroundColourId));
        if (horizontal)
            g.drawLine(start, centre, end, centre, 3.0f);
        else
            g.drawLine(centre, start, centre, end, 3.0f);

        const auto active = slider.isEnabled()
            ? Tokens::accentInteractive.withAlpha(0.82f)
            : Tokens::disabled;
        g.setColour(active);
        if (horizontal)
            g.drawLine(start, centre, sliderPos, centre, 3.0f);
        else
            g.drawLine(centre, sliderPos, centre, end, 3.0f);

        const float radius = juce::jlimit(4.0f, 6.0f,
                                          static_cast<float>(juce::jmin(width, height)) * 0.28f);
        g.setColour(slider.hasKeyboardFocus(true) ? Tokens::focusRing
                                                   : slider.findColour(juce::Slider::thumbColourId));
        if (horizontal)
            g.fillEllipse(sliderPos - radius, centre - radius, radius * 2.0f, radius * 2.0f);
        else
            g.fillEllipse(centre - radius, sliderPos - radius, radius * 2.0f, radius * 2.0f);
    }

    void drawToggleButton(juce::Graphics& g, juce::ToggleButton& button,
                          bool shouldDrawButtonAsHighlighted,
                          bool shouldDrawButtonAsDown) override
    {
        auto area = button.getLocalBounds().reduced(2, 1);
        auto box = area.removeFromLeft(16).withSizeKeepingCentre(14, 14).toFloat();
        const bool active = button.getToggleState();
        auto fill = active ? Tokens::accentInteractive : Tokens::surfaceRaised;
        if (shouldDrawButtonAsHighlighted)
            fill = fill.overlaidWith(Tokens::hoverWash);
        if (shouldDrawButtonAsDown)
            fill = fill.overlaidWith(Tokens::pressedWash);

        g.setColour(fill);
        g.fillRoundedRectangle(box, 3.0f);
        g.setColour(button.hasKeyboardFocus(true) ? Tokens::focusRing : Tokens::border);
        g.drawRoundedRectangle(box, 3.0f, button.hasKeyboardFocus(true) ? 1.5f : 1.0f);

        if (active)
        {
            juce::Path tick;
            tick.startNewSubPath(box.getX() + 3.0f, box.getCentreY());
            tick.lineTo(box.getX() + 6.0f, box.getBottom() - 3.0f);
            tick.lineTo(box.getRight() - 2.5f, box.getY() + 3.0f);
            g.setColour(Tokens::background);
            g.strokePath(tick, juce::PathStrokeType(1.5f, juce::PathStrokeType::curved,
                                                    juce::PathStrokeType::rounded));
        }

        g.setColour(button.findColour(juce::ToggleButton::textColourId));
        g.setFont(juce::Font(juce::FontOptions().withHeight(10.0f)));
        g.drawFittedText(button.getButtonText(), area, juce::Justification::centredLeft, 1);
    }

    void drawGroupComponentOutline(juce::Graphics& g, int width, int height,
                                    const juce::String& text,
                                    const juce::Justification& justification,
                                    juce::GroupComponent& group) override
    {
        const auto bounds = juce::Rectangle<float>(0.5f, 0.5f,
                                                   static_cast<float>(width) - 1.0f,
                                                   static_cast<float>(height) - 1.0f);
        g.setColour(group.findColour(juce::GroupComponent::outlineColourId));
        g.drawRoundedRectangle(bounds, Tokens::cornerRadiusLg, 1.0f);

        if (text.isNotEmpty())
        {
            auto titleBounds = juce::Rectangle<int>(12, 0, width - 24, 18);
            g.setColour(group.findColour(juce::GroupComponent::textColourId));
            g.setFont(juce::Font(juce::FontOptions().withHeight(Tokens::fontLabel)
                                     .withStyle("Bold")));
            g.drawFittedText(text.toUpperCase(), titleBounds, justification, 1);
        }
    }

    void drawTableHeaderBackground(juce::Graphics& g,
                                   juce::TableHeaderComponent& header) override
    {
        g.fillAll(header.findColour(juce::TableHeaderComponent::backgroundColourId));
        g.setColour(Tokens::border);
        g.drawHorizontalLine(header.getHeight() - 1, 0.0f,
                             static_cast<float>(header.getWidth()));
    }

    void drawTableHeaderColumn(juce::Graphics& g, juce::TableHeaderComponent& header,
                               const juce::String& columnName, int, int width, int height,
                               bool isMouseOver, bool isMouseDown, int) override
    {
        if (isMouseOver || isMouseDown)
        {
            g.setColour(isMouseDown ? Tokens::selection : Tokens::hoverWash);
            g.fillRect(0, 0, width, height);
        }

        g.setColour(Tokens::border);
        g.drawVerticalLine(width - 1, 4.0f, static_cast<float>(height - 4));
        g.setColour(header.findColour(juce::TableHeaderComponent::textColourId));
        g.setFont(juce::Font(juce::FontOptions().withHeight(9.0f).withStyle("Bold")));
        g.drawFittedText(columnName.toUpperCase(), juce::Rectangle<int>(8, 0, width - 16, height),
                         juce::Justification::centredLeft, 1);
    }

    void drawScrollbar(juce::Graphics& g, juce::ScrollBar& scrollbar,
                       int x, int y, int width, int height,
                       bool isScrollbarVertical, int thumbStartPosition,
                       int thumbSize, bool isMouseOver, bool isMouseDown) override
    {
        juce::ignoreUnused(scrollbar);
        const int trackLength = isScrollbarVertical ? height : width;
        const int crossLength = isScrollbarVertical ? width : height;
        if (thumbSize <= 0 || trackLength <= 0)
            return;

        auto thumb = isScrollbarVertical
            ? juce::Rectangle<int>(x + 2, y + thumbStartPosition,
                                   juce::jmax(3, crossLength - 4), thumbSize)
            : juce::Rectangle<int>(x + thumbStartPosition, y + 2,
                                   thumbSize, juce::jmax(3, crossLength - 4));
        auto colour = (isMouseOver || isMouseDown)
            ? Tokens::muted
            : Tokens::borderStrong;
        g.setColour(colour.withAlpha(isMouseDown ? 0.95f : 0.8f));
        g.fillRoundedRectangle(thumb.toFloat(), 2.0f);
    }
};
