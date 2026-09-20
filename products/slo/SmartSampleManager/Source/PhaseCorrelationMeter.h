#pragma once

#include <JuceHeader.h>
#include "DesignTokens.h"

// PhaseCorrelationMeter: Hardware-style Phase Correlation & Mix Collision Visualizer.
//
// Renders real-time stereo/inter-track phase correlation [-1.0 ... +1.0] with:
//  - Ballistic-smoothed needle with dynamic glow
//  - Danger (cancel), caution (decorrelated), and emerald (in-phase) safety zones
//  - Inset LCD styling matching NITE DSP hardware design language
//  - Interactive collision warnings (Sub-masking @ Hz, Phase inversion advisory, HPF cut target)
class PhaseCorrelationMeter : public juce::Component
{
public:
    PhaseCorrelationMeter()
    {
        setOpaque(false);
    }

    void updateCollisionState(float phaseCorrelation, bool lowEndMasking, float clashFreqHz, float recommendedHpfHz)
    {
        targetCorrelation = juce::jlimit(-1.0f, 1.0f, phaseCorrelation);
        hasMasking = lowEndMasking;
        collisionFreq = clashFreqHz;
        recHpf = recommendedHpfHz;

        // Smooth ballistics (hardware needle inertia)
        currentCorrelation += 0.35f * (targetCorrelation - currentCorrelation);
        repaint();
    }

    void reset()
    {
        targetCorrelation = 1.0f;
        currentCorrelation = 1.0f;
        hasMasking = false;
        collisionFreq = 0.0f;
        recHpf = 0.0f;
        repaint();
    }

    float getCurrentCorrelation() const noexcept { return currentCorrelation; }
    bool isMaskingActive() const noexcept { return hasMasking; }

    void paint(juce::Graphics& g) override
    {
        auto bounds = getLocalBounds().toFloat();
        if (bounds.isEmpty())
            return;

        // 1. Background LCD Inset Box
        g.setColour(Tokens::lcdBackground);
        g.fillRoundedRectangle(bounds, 4.0f);
        g.setColour(Tokens::border);
        g.drawRoundedRectangle(bounds.reduced(0.5f), 4.0f, 1.0f);

        auto inner = bounds.reduced(6.0f, 4.0f);

        // 2. Title & Value Readout Row
        auto topRow = inner.removeFromTop(12.0f);
        g.setFont(juce::Font(juce::FontOptions().withHeight(9.5f).withStyle("Bold")));
        g.setColour(Tokens::mutedDim);
        g.drawText("CORRELATION", topRow.removeFromLeft(80.0f), juce::Justification::left, false);

        juce::String corrText = juce::String::formatted(currentCorrelation >= 0.0f ? "+%.2f" : "%.2f", currentCorrelation);
        juce::Colour corrColour;
        if (currentCorrelation < 0.0f)
            corrColour = Tokens::redError;
        else if (currentCorrelation < 0.4f)
            corrColour = Tokens::amberWarning;
        else
            corrColour = Tokens::emeraldGreen;

        g.setColour(corrColour);
        g.drawText(corrText, topRow, juce::Justification::right, false);

        inner.removeFromTop(2.0f);

        // 3. Meter Track Bar
        auto meterTrack = inner.removeFromTop(10.0f);
        g.setColour(Tokens::surfaceRaised);
        g.fillRoundedRectangle(meterTrack, 3.0f);

        // Zero marker at mid-point
        float midX = meterTrack.getCentreX();
        g.setColour(Tokens::muted.withAlpha(0.5f));
        g.drawVerticalLine(juce::roundToInt(midX), meterTrack.getY() - 1.0f, meterTrack.getBottom() + 1.0f);

        // Needle and fill position
        float normVal = (currentCorrelation + 1.0f) * 0.5f; // [0.0, 1.0]
        float needleX = meterTrack.getX() + normVal * meterTrack.getWidth();
        needleX = juce::jlimit(meterTrack.getX() + 2.0f, meterTrack.getRight() - 2.0f, needleX);

        // Fill from center (0.0) to needle
        if (std::abs(needleX - midX) > 1.0f)
        {
            auto fillRect = juce::Rectangle<float>(
                std::min(midX, needleX), meterTrack.getY() + 1.0f,
                std::abs(needleX - midX), meterTrack.getHeight() - 2.0f);
            g.setColour(corrColour.withAlpha(0.60f));
            g.fillRect(fillRect);
        }

        // Glowing needle
        g.setColour(corrColour);
        g.fillRect(needleX - 1.5f, meterTrack.getY() - 1.0f, 3.0f, meterTrack.getHeight() + 2.0f);
        g.setColour(corrColour.withAlpha(0.25f));
        g.fillRect(needleX - 3.5f, meterTrack.getY() - 2.0f, 7.0f, meterTrack.getHeight() + 4.0f);

        inner.removeFromTop(2.0f);

        // 4. Tick Labels Row (-1, 0, +1)
        auto tickRow = inner.removeFromTop(9.0f);
        g.setFont(juce::Font(juce::FontOptions().withHeight(8.0f)));
        g.setColour(Tokens::mutedDim);
        g.drawText("-1", tickRow.removeFromLeft(20.0f), juce::Justification::left, false);
        g.drawText("0", tickRow.withX(midX - 10.0f).withWidth(20.0f), juce::Justification::centred, false);
        g.drawText("+1", tickRow.removeFromRight(20.0f), juce::Justification::right, false);

        inner.removeFromTop(2.0f);

        // 5. Collision / Masking Advisory Badge
        if (hasMasking)
        {
            auto alertBox = inner;
            juce::Colour alertBg = (currentCorrelation < 0.0f)
                ? Tokens::redError.withAlpha(0.18f)
                : Tokens::amberWarning.withAlpha(0.18f);
            juce::Colour alertBorder = (currentCorrelation < 0.0f)
                ? Tokens::redError.withAlpha(0.6f)
                : Tokens::amberWarning.withAlpha(0.6f);
            juce::Colour alertText = (currentCorrelation < 0.0f)
                ? Tokens::redError
                : Tokens::amberWarning;

            g.setColour(alertBg);
            g.fillRoundedRectangle(alertBox, 3.0f);
            g.setColour(alertBorder);
            g.drawRoundedRectangle(alertBox.reduced(0.5f), 3.0f, 1.0f);

            g.setFont(juce::Font(juce::FontOptions().withHeight(8.5f).withStyle("Bold")));
            g.setColour(alertText);

            juce::String msg;
            if (currentCorrelation < 0.0f)
                msg = juce::String::formatted("PHASE CANCEL @ %.0fHz | INVERT PHASE", collisionFreq);
            else
                msg = juce::String::formatted("SUB MASKING @ %.0fHz | REC HPF: %.0fHz", collisionFreq, recHpf);

            g.drawText(msg, alertBox, juce::Justification::centred, true);
        }
        else if (currentCorrelation >= 0.5f && currentCorrelation <= 1.0f)
        {
            auto infoBox = inner;
            g.setFont(juce::Font(juce::FontOptions().withHeight(8.5f)));
            g.setColour(Tokens::emeraldGreen.withAlpha(0.7f));
            g.drawText("IN-PHASE / LOW-END CLEAR", infoBox, juce::Justification::centred, true);
        }
    }

private:
    float currentCorrelation = 1.0f;
    float targetCorrelation = 1.0f;
    bool hasMasking = false;
    float collisionFreq = 0.0f;
    float recHpf = 0.0f;

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR(PhaseCorrelationMeter)
};

