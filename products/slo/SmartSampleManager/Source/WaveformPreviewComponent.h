#pragma once

#include <JuceHeader.h>
#include <vector>
#include <cmath>
#include <algorithm>
#include "DesignTokens.h"

class WaveformPreviewComponent : public juce::Component, public juce::ChangeListener
{
public:
    WaveformPreviewComponent(juce::AudioFormatManager& formatManagerToUse)
        : formatManager(formatManagerToUse),
          thumbnailCache(5),
          thumbnail(512, formatManagerToUse, thumbnailCache)
    {
        thumbnail.addChangeListener(this);
    }
    
    ~WaveformPreviewComponent() override
    {
        thumbnail.removeChangeListener(this);
    }
    
    void loadFile(const juce::File& file)
    {
        currentFile = file;
        thumbnail.setSource(new juce::FileInputSource(file));
        transients.clear();
        selectedSliceIdx = -1;
        detectTransients(file);
        repaint();
    }
    
    void clear()
    {
        currentFile = juce::File();
        thumbnail.clear();
        transients.clear();
        selectedSliceIdx = -1;
        repaint();
    }
    
    void paint(juce::Graphics& g) override
    {
        auto bounds = getLocalBounds();
        
        // The waveform is an audition surface, not a decorative card. Keep
        // the treatment quiet so the selected sample and transport state lead.
        g.setColour(Tokens::surfaceRaised);
        g.fillRoundedRectangle(bounds.toFloat(), 6.0f);
        g.setColour(Tokens::border);
        g.drawRoundedRectangle(bounds.toFloat(), 6.0f, 1.0f);
        
        if (thumbnail.getNumChannels() == 0)
        {
            g.setColour(Tokens::mutedDim);
            g.setFont(juce::Font(juce::FontOptions().withHeight(12.0f)));
            g.drawFittedText("- No audio loaded -", bounds, juce::Justification::centred, 1);
            return;
        }
        
        double totalLen = thumbnail.getTotalLength();
        if (totalLen > 0.0) {
            std::vector<double> boundaries;
            boundaries.push_back(0.0);
            boundaries.insert(boundaries.end(), transients.begin(), transients.end());
            boundaries.push_back(totalLen);
 
            // Draw highlight overlay for selected slice
            if (selectedSliceIdx >= 0 && selectedSliceIdx < static_cast<int>(boundaries.size() - 1)) {
                double startT = boundaries[selectedSliceIdx];
                double endT = boundaries[selectedSliceIdx + 1];
                
                float x1 = 5.0f + static_cast<float>((bounds.getWidth() - 10) * (startT / totalLen));
                float x2 = 5.0f + static_cast<float>((bounds.getWidth() - 10) * (endT / totalLen));
                
                g.setColour(Tokens::selection);
                g.fillRect(x1, 5.0f, x2 - x1, static_cast<float>(bounds.getHeight() - 10));
            }
        }
 
        g.setColour(Tokens::accentInteractive.withAlpha(0.82f));
        thumbnail.drawChannels(g, bounds.reduced(5), 0.0, thumbnail.getTotalLength(), 1.0f);
        
        // Transients are an editorial hint, not an error state.
        g.setColour(Tokens::warningText.withAlpha(0.82f));
        if (totalLen > 0.0) {
            for (double t : transients) {
                float x = 5.0f + static_cast<float>((bounds.getWidth() - 10) * (t / totalLen));
                // Draw vertical dashed line
                for (int y = 5; y < bounds.getHeight() - 5; y += 4) {
                    g.drawRect(static_cast<int>(x), y, 1, 2);
                }
            }
        }
    }
    
    void changeListenerCallback(juce::ChangeBroadcaster* source) override
    {
        if (source == &thumbnail)
            repaint();
    }

    void mouseDown(const juce::MouseEvent& event) override
    {
        double totalLen = thumbnail.getTotalLength();
        if (totalLen <= 0.0) return;
        
        auto bounds = getLocalBounds();
        float contentWidth = static_cast<float>(bounds.getWidth() - 10);
        if (contentWidth <= 0.0f) return;
        
        double clickTime = ((event.position.getX() - 5.0f) / contentWidth) * totalLen;
        clickTime = juce::jlimit(0.0, totalLen, clickTime);
        
        std::vector<double> boundaries;
        boundaries.push_back(0.0);
        boundaries.insert(boundaries.end(), transients.begin(), transients.end());
        boundaries.push_back(totalLen);
        
        selectedSliceIdx = -1;
        for (size_t i = 0; i < boundaries.size() - 1; ++i) {
            if (clickTime >= boundaries[i] && clickTime <= boundaries[i + 1]) {
                selectedSliceIdx = static_cast<int>(i);
                break;
            }
        }
        repaint();
    }

    void mouseDrag(const juce::MouseEvent& event) override
    {
        if (event.mouseWasDraggedSinceMouseDown() && selectedSliceIdx >= 0)
        {
            juce::File exportFile = exportSliceToTempFile(selectedSliceIdx);
            if (exportFile.existsAsFile())
            {
                if (auto* container = juce::DragAndDropContainer::findParentDragContainerFor(this))
                {
                    juce::StringArray files = { exportFile.getFullPathName() };
                    container->performExternalDragDropOfFiles(files, false, this, []() {});
                }
            }
        }
    }
    
private:
    juce::AudioFormatManager& formatManager;
    juce::AudioThumbnailCache thumbnailCache;
    juce::AudioThumbnail thumbnail;
    std::vector<double> transients;

    juce::File currentFile;
    int selectedSliceIdx = -1;
    
    juce::File exportSliceToTempFile(int sliceIdx)
    {
        if (sliceIdx < 0 || currentFile.existsAsFile() == false)
            return {};
            
        double totalLen = thumbnail.getTotalLength();
        if (totalLen <= 0.0) return {};
        
        std::vector<double> boundaries;
        boundaries.push_back(0.0);
        boundaries.insert(boundaries.end(), transients.begin(), transients.end());
        boundaries.push_back(totalLen);
        
        if (sliceIdx >= static_cast<int>(boundaries.size() - 1))
            return {};
            
        double startSec = boundaries[sliceIdx];
        double endSec = boundaries[sliceIdx + 1];
        
        std::unique_ptr<juce::AudioFormatReader> reader(formatManager.createReaderFor(currentFile));
        if (!reader) return {};
        
        double sampleRate = reader->sampleRate;
        int numChannels = reader->numChannels;
        int bitsPerSample = reader->bitsPerSample;
        
        int64_t startSample = static_cast<int64_t>(startSec * sampleRate);
        int64_t endSample = static_cast<int64_t>(endSec * sampleRate);
        int64_t lengthSamples = endSample - startSample;
        if (lengthSamples <= 0) return {};
        
        juce::File tempDir = juce::File::getSpecialLocation(juce::File::tempDirectory)
                                .getChildFile("SmartSampleManager_Exports");
        tempDir.createDirectory();
        
        juce::String exportName = currentFile.getFileNameWithoutExtension() + "_slice_" + juce::String(sliceIdx) + ".wav";
        juce::File exportFile = tempDir.getChildFile(exportName);
        if (exportFile.existsAsFile())
            exportFile.deleteFile();
            
        std::unique_ptr<juce::FileOutputStream> outputStream(exportFile.createOutputStream());
        if (!outputStream) return {};
        
        juce::WavAudioFormat wavFormat;
        std::unique_ptr<juce::AudioFormatWriter> writer(wavFormat.createWriterFor(outputStream.get(),
                                                                                 sampleRate,
                                                                                 numChannels,
                                                                                 bitsPerSample,
                                                                                 {},
                                                                                 0));
        if (writer)
        {
            outputStream.release();
            
            int blockSize = 4096;
            juce::AudioBuffer<float> buffer(numChannels, blockSize);
            int64_t samplesRemaining = lengthSamples;
            int64_t currentReadPos = startSample;
            
            while (samplesRemaining > 0)
            {
                int samplesToRead = static_cast<int>(std::min(static_cast<int64_t>(blockSize), samplesRemaining));
                reader->read(&buffer, 0, samplesToRead, currentReadPos, true, true);
                writer->writeFromAudioSampleBuffer(buffer, 0, samplesToRead);
                
                samplesRemaining -= samplesToRead;
                currentReadPos += samplesToRead;
            }
            return exportFile;
        }
        
        return {};
    }

    void detectTransients(const juce::File& file)
    {
        std::unique_ptr<juce::AudioFormatReader> reader(formatManager.createReaderFor(file));
        if (!reader) return;
        
        double sampleRate = reader->sampleRate;
        int numChannels = reader->numChannels;
        int lengthInSamples = static_cast<int>(reader->lengthInSamples);
        
        int hopSize = 512;
        int numHops = lengthInSamples / hopSize;
        if (numHops <= 0) return;
        
        std::vector<float> energy(numHops, 0.0f);
        juce::AudioBuffer<float> tempBuffer(numChannels, hopSize);
        
        for (int hop = 0; hop < numHops; ++hop)
        {
            reader->read(&tempBuffer, 0, hopSize, hop * hopSize, true, false);
            float hopSum = 0.0f;
            for (int ch = 0; ch < numChannels; ++ch)
            {
                auto* channelData = tempBuffer.getReadPointer(ch);
                for (int i = 0; i < hopSize; ++i)
                {
                    hopSum += channelData[i] * channelData[i];
                }
            }
            energy[hop] = std::sqrt(hopSum / (hopSize * numChannels));
        }
        
        std::vector<float> diff(numHops, 0.0f);
        for (int i = 1; i < numHops; ++i)
        {
            diff[i] = std::max(0.0f, energy[i] - energy[i - 1]);
        }
        
        float maxDiff = 0.0f;
        for (float d : diff) maxDiff = std::max(maxDiff, d);
        float threshold = maxDiff * 0.15f;
        if (threshold < 0.01f) threshold = 0.01f;
        
        for (int i = 2; i < numHops - 2; ++i)
        {
            if (diff[i] > threshold && diff[i] > diff[i - 1] && diff[i] > diff[i + 1])
            {
                double timeInSec = static_cast<double>(i * hopSize) / sampleRate;
                transients.push_back(timeInSec);
            }
        }
    }
};
