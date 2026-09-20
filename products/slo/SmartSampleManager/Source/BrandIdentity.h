#pragma once

#include <JuceHeader.h>
#include "DesignTokens.h"

namespace BrandIdentity
{
    // Draw the custom NITE DSP geometric vector logo mark (a modern minimalist waveforms concept)
    inline void drawLogoMark(juce::Graphics& g, juce::Rectangle<float> bounds, juce::Colour logoColour)
    {
        g.saveState();
        g.setColour(logoColour);
        
        // Define a modern geometric logo: a combination of vertical soundwave/SLO line bars
        // forming a sleek diamond/N mark.
        juce::Path logoPath;
        
        float x = bounds.getX();
        float y = bounds.getY();
        float w = bounds.getWidth();
        float h = bounds.getHeight();
        
        // 4 geometric columns representing SLO optimization bars
        float colW = w / 7.0f;
        float gap = colW;
        
        // Col 1 (short left)
        logoPath.addRoundedRectangle(x, y + h * 0.3f, colW, h * 0.4f, colW * 0.5f);
        // Col 2 (medium-tall left-center)
        logoPath.addRoundedRectangle(x + colW + gap, y + h * 0.1f, colW, h * 0.8f, colW * 0.5f);
        // Col 3 (medium-tall right-center)
        logoPath.addRoundedRectangle(x + (colW + gap) * 2, y + h * 0.15f, colW, h * 0.7f, colW * 0.5f);
        // Col 4 (short right)
        logoPath.addRoundedRectangle(x + (colW + gap) * 3, y + h * 0.35f, colW, h * 0.3f, colW * 0.5f);
        
        g.fillPath(logoPath);
        g.restoreState();
    }
}
