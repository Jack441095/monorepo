#pragma once

#include <JuceHeader.h>
#include <array>
#include <functional>
#include <string>
#include <vector>

// In-app results overlay for Find Similar and Find Duplicates -- UX-P1 fix
// (docs/SMART_SAMPLE_MANAGER_UX_AUDIT.md): both previously used
// juce::AlertWindow::showMessageBoxAsync, a native OS dialog that couldn't be
// acted on directly (read a name, close the dialog, manually relocate the
// sample). This panel shows results inside the app; clicking a row with a
// file path selects that sample via the same updateSelectionDetails() path
// canvas clicks already use, so PLAY/drag work immediately afterward.
class ResultsPanel : public juce::Component, private juce::ListBoxModel {
public:
    struct Row {
        juce::String primaryText;
        juce::String secondaryText;
        // Optional aspect ratings for retrieval results. Keeping this display
        // data in the generic panel avoids coupling the UI component to the
        // engine's evidence contract.
        struct AspectScores {
            bool valid = false;
            float overall = 0.0f;
            float embedding = 0.0f;
            float spectrum = 0.0f;
            float timbre = 0.0f;
            float pitch = 0.0f;
            float amplitude = 0.0f;
            float material = 0.0f;
            float impact = 0.0f;
            float stiffness = 0.0f;
        } aspects;
        // Empty filePath means the row is informational only (e.g. a
        // duplicate-group header) and isn't selectable.
        juce::String filePath;
    };

    ResultsPanel();
    ~ResultsPanel() override = default;

    void setContent(const juce::String& title, const std::vector<Row>& newRows);
    void setRowSelectedCallback(std::function<void(const juce::String&)> callback);
    void setCloseCallback(std::function<void()> callback);
    // Right-click / control-click on a row -- used by the Duplicate
    // Intelligence flow for "Reveal in Finder" (a safe, non-destructive
    // action; see PluginEditor::showDuplicatesReport()'s comment on why no
    // destructive delete action is wired up this pass). Not used by Find
    // Similar's rows -- only set where a caller actually wants it.
    void setRowRightClickedCallback(std::function<void(const juce::String&)> callback);

    // ── Find Similar 2.0 refinement strip ──────────────────────────────────
    // Optional row of bipolar sliders (Brighter/Darker, More Punch/Less Punch,
    // Cleaner/Noisier) shown above the results list -- lets the user nudge an
    // already-simple, one-click "Find Similar" result without ever seeing the
    // words "centroid"/"crest factor"/"zero crossing rate". Hidden by default;
    // showDuplicatesReport() and any non-similarity result list never call
    // setRefinementVisible(true), so those stay exactly as before. Values are
    // -1..1, matching SampleManagerEngine::TimbreRefinement's shift range
    // (see findSimilarRefined()'s brightnessShift * 5000Hz / punchinessShift *
    // 20 crest / noiseShift * 0.5 ZCR mapping) -- kept as plain floats here
    // rather than including SampleManagerEngine.h, so this panel stays a
    // generic reusable results overlay, not coupled to one engine struct.
    void setRefinementVisible(bool shouldBeVisible);
    // User-facing "RESET" action -- zeroes all three sliders AND re-fires
    // onRefinementChanged(0,0,0) so the results list actually returns to
    // neutral. Distinct from silentlyResetRefinementSliders() below.
    void resetRefinement();
    // Zeroes the sliders WITHOUT firing onRefinementChanged -- for opening a
    // fresh Find Similar result set, where the caller has already populated
    // the panel with the plain, unweighted default search and a requery
    // would pointlessly re-run findSimilarRefined() with a different (still
    // DSP-aware) ranking formula than the true one-click default.
    void silentlyResetRefinementSliders();
    // Called live as any slider moves (measured latency at real library scale
    // makes debouncing unnecessary -- see docs/SMART_SAMPLE_MANAGER_UX_RUNTIME_VALIDATION.md's
    // Find Similar refinement latency numbers).
    void setRefinementChangedCallback(std::function<void(float brightness, float punchiness, float noise)> callback);

    // Sononym-style independent aspect weights for the aspect retrieval path.
    // Values are non-negative multipliers; zero disables an aspect. This is
    // strictly a read-only ranking control and never changes taxonomy or file
    // names.
    void setAspectControlsVisible(bool shouldBeVisible);
    void silentlyResetAspectWeights();
    void setAspectWeightsChangedCallback(std::function<void(float embedding, float spectrum,
                                                            float pitch, float material,
                                                            float impact, float stiffness)> callback);

    // Modal-style overlays own keyboard focus while open so Escape is always
    // a reliable, reversible way back to the main browser.
    bool keyPressed(const juce::KeyPress& key) override;

    void paint(juce::Graphics&) override;
    void resized() override;

    // juce::ListBoxModel
    int getNumRows() override;
    void paintListBoxItem(int rowNumber, juce::Graphics&, int width, int height, bool rowIsSelected) override;
    void listBoxItemClicked(int row, const juce::MouseEvent&) override;
    void selectedRowsChanged(int lastRowSelected) override;

private:
    juce::Label titleLabel;
    juce::TextButton closeButton;
    juce::ListBox listBox;
    std::vector<Row> rows;
    juce::String emptyStateMessage;

    std::function<void(const juce::String&)> onRowSelected;
    std::function<void(const juce::String&)> onRowRightClicked;
    std::function<void()> onClose;
    int lastNotifiedRow = -1;

    // Refinement strip (hidden unless setRefinementVisible(true) is called --
    // see .h comment above).
    bool refinementVisible = false;
    juce::Label refinementHeading;
    juce::Label brightnessLabel;
    juce::Slider brightnessSlider;
    juce::Label punchLabel;
    juce::Slider punchSlider;
    juce::Label noiseLabel;
    juce::Slider noiseSlider;
    juce::TextButton resetRefinementButton;
    std::function<void(float, float, float)> onRefinementChanged;
    void fireRefinementChanged();

    bool aspectControlsVisible = false;
    juce::Label aspectHeading;
    std::array<juce::Label, 6> aspectLabels;
    std::array<juce::Slider, 6> aspectSliders;
    juce::TextButton resetAspectButton;
    std::function<void(float, float, float, float, float, float)> onAspectWeightsChanged;
    void fireAspectWeightsChanged();

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR(ResultsPanel)
};
