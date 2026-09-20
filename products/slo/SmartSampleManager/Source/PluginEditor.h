#pragma once

#include <JuceHeader.h>
#include "PluginProcessor.h"
#include "SampleCanvas.h"
#include "WaveformPreviewComponent.h"
#include "AppSettings.h"
#include "MainMenuModel.h"
#include "PreferencesWindow.h"
#include "ResultsPanel.h"
#include "SortPreviewPanel.h"
#include "PrecisionBrowser.h"
#include "SmartCollectionsPanel.h"
#include "BrandIdentity.h"
#include "SLOLookAndFeel.h"

class SmartSampleManagerAudioProcessorEditor : public juce::AudioProcessorEditor,
                                               public juce::FileDragAndDropTarget,
                                               public juce::DragAndDropContainer,
                                               public juce::Timer
{
public:
    SmartSampleManagerAudioProcessorEditor(SmartSampleManagerAudioProcessor&);
    ~SmartSampleManagerAudioProcessorEditor() override;

    void paint(juce::Graphics&) override;
    void resized() override;

    // FileDragAndDropTarget implementation
    bool isInterestedInFileDrag(const juce::StringArray& files) override;
    void fileDragEnter(const juce::StringArray& files, int x, int y) override;
    void fileDragExit(const juce::StringArray& files) override;
    void filesDropped(const juce::StringArray& files, int x, int y) override;

    // Timer implementation for periodic UI updates
    void timerCallback() override;

    // Keyboard navigation and commands
    bool keyPressed(const juce::KeyPress& key) override;

private:
    SmartSampleManagerAudioProcessor& audioProcessor;

    // A single look-and-feel keeps native JUCE controls visually coherent
    // across the editor, overlays, and the scrollable inspector.
    SLOLookAndFeel lookAndFeel;

    // Components
    SampleCanvas canvas;
    PrecisionBrowser browser;
    WaveformPreviewComponent waveformPreview;

    // Layout tabs
    juce::TextButton gridTabButton;
    juce::TextButton mapTabButton;
    juce::TextButton splitTabButton;
    enum LayoutMode { GridOnly, MapOnly, SplitView };
    LayoutMode currentLayoutMode = SplitView;
    void updateLayoutMode();

    // In-app Find Similar / Find Duplicates results overlay -- replaces the
    // native juce::AlertWindow report dialogs (UX-P1 #2 in
    // docs/SMART_SAMPLE_MANAGER_UX_AUDIT.md: those dialogs couldn't be acted
    // on directly). Built in an earlier pass but never wired into the editor
    // or the CMake source list until this phase -- see
    // docs/SLO_UX_AUDIT.md for that finding.
    ResultsPanel resultsPanel;
    void showResultsPanel(const juce::String& title, const std::vector<ResultsPanel::Row>& rows);
    void hideResultsPanel();
    SortPreviewPanel sortPreviewPanel;
    void showSortPreview();
    void hideSortPreview();
    void performUndoSort();
    // Mirrors a similarity result onto the Sample Map. See the .cpp comment --
    // this is view state only; nothing about the engine's result is altered.
    void highlightSimilarOnMap(const std::vector<SampleItem>& results);
    void selectSampleByPath(const juce::String& filePath);

    // Header Components
    juce::Label titleLabel;
    juce::Label statusLabel;

    // Draggable Split Divider Component
    class SplitDivider : public juce::Component
    {
    public:
        SplitDivider()
        {
            setMouseCursor(juce::MouseCursor::UpDownResizeCursor);
            setWantsKeyboardFocus(true);
            setMouseClickGrabsKeyboardFocus(true);
            setName("MAP/LIST resize divider");
        }
        void paint(juce::Graphics& g) override
        {
            const bool emphasized = hovered || hasKeyboardFocus(true);
            g.fillAll(emphasized ? Tokens::surfaceHover : Tokens::border);
            // Draw a centered drag handle. It brightens on hover/focus so the
            // resize affordance is discoverable without becoming a permanent
            // visual stripe through the two browsing surfaces.
            g.setColour(emphasized ? Tokens::accentInteractive : Tokens::mutedDim);
            const float cx = static_cast<float>(getWidth()) * 0.5f;
            const float cy = static_cast<float>(getHeight()) * 0.5f;
            g.fillRoundedRectangle(cx - (emphasized ? 16.0f : 12.0f),
                                   cy - (emphasized ? 1.5f : 1.0f),
                                   emphasized ? 32.0f : 24.0f,
                                   emphasized ? 3.0f : 2.0f,
                                   1.0f);
            if (hasKeyboardFocus(true))
            {
                g.setColour(Tokens::focusRing.withAlpha(0.72f));
                g.drawRect(getLocalBounds().toFloat().reduced(1.0f), 1.5f);
            }
        }
        void mouseDown(const juce::MouseEvent& e) override
        {
            grabKeyboardFocus();
            dragStartLimit = static_cast<float>(e.getScreenPosition().y);
            if (onDragStart) onDragStart();
        }
        void mouseEnter(const juce::MouseEvent& e) override
        {
            juce::ignoreUnused(e);
            hovered = true;
            repaint();
        }
        void mouseExit(const juce::MouseEvent& e) override
        {
            juce::ignoreUnused(e);
            hovered = false;
            repaint();
        }
        void mouseDrag(const juce::MouseEvent& e) override
        {
            if (onDrag)
                onDrag(static_cast<int>(static_cast<float>(e.getScreenPosition().y) - dragStartLimit));
        }
        bool keyPressed(const juce::KeyPress& key) override
        {
            if (key == juce::KeyPress::upKey)
            {
                if (onKeyStep) onKeyStep(-1);
                return true;
            }
            if (key == juce::KeyPress::downKey)
            {
                if (onKeyStep) onKeyStep(1);
                return true;
            }
            return false;
        }
        std::function<void()> onDragStart;
        std::function<void(int)> onDrag;
        std::function<void(int)> onKeyStep;
    private:
        float dragStartLimit = 0.0f;
        bool hovered = false;
    };
    SplitDivider splitDivider;
    float splitFraction = 0.5f; // Initial 50/50 vertical division
    int dragStartSplitY = 0;

    // Favorites & History UI elements
    juce::TextButton favoritesTabButton;
    juce::TextButton historyTabButton;
    bool showFavoritesOverlay = false;
    bool showHistoryOverlay = false;
    void toggleFavoritesView();
    void toggleHistoryView();


    // Smart Collections panel overlay
    SmartCollectionsPanel smartCollectionsPanel;
    juce::TextButton smartCollectionsButton;
    void showSmartCollectionsPanel();
    void hideSmartCollectionsPanel();

    // Free-text search (filename/key/instrument/BPM), debounced -- see
    // searchDebounceGeneration below.
    juce::TextEditor searchField;
    juce::TextButton clearSearchButton;
    int searchDebounceGeneration = 0;

    // Sidebar/Metadata Editor Panel Components
    //
    // Phase 8.6B fix: the sidebar's ~20 stacked controls need roughly 650-700px
    // of vertical space, but the window's documented minimum height is 500px --
    // at that size (or anywhere close to it) the trailing controls (Sort
    // Library, Find Duplicates) used to be clipped to zero height or pushed
    // fully off-screen, a real regression flagged by earlier UX phases and
    // reconfirmed by source inspection in 8.6A. Wrapping the sidebar's
    // content in a Viewport makes it scroll instead of clip -- every control
    // stays reachable at any window size, which is the actual fix section 16
    // asks for (no false fixed-height assumption) rather than just raising
    // the minimum window size as a band-aid.
    juce::Viewport sidebarViewport;
    juce::Component sidebarContent; // the Viewport's viewed component; owns nothing, just a layout host
    void layoutSidebarContent(int contentWidth);
    static constexpr int sidebarContentHeight = 900; // see layoutSidebarContent() -- sum of all row heights below plus margins

    juce::GroupComponent metadataGroup;
    
    juce::Label nameLabel;
    juce::Label nameVal;
    // Compact at-a-glance classifier state. Detailed taxonomy editing stays
    // below, but confidence/evidence remains visible in the inspector header.
    juce::Label inspectorSummaryLabel;
    juce::TextButton retryAnalysisButton;
    
    juce::Label bpmLabel;
    juce::TextEditor bpmEditor;
    
    juce::Label keyLabel;
    juce::TextEditor keyEditor;
    
    juce::Label typeLabel;
    juce::ComboBox typeCombo; // Combo box is better for Instrument Type selection!

    // Ableton taxonomy (Category/Subcategory) -- see AbletonTaxonomy.h.
    // Deliberately separate from typeCombo/instrumentType above, which is
    // the pre-existing single-string classifier this doesn't replace.
    juce::Label taxonomyLabel;
    juce::ComboBox categoryCombo;
    juce::TextEditor subcategoryEditor;
    juce::Label taxonomyStatusLabel;   // confidence/evidence/taxonomy version, or an explicit unknown/user state
    juce::Label suggestedTagsLabel;    // Visually displays secondary suggested tags
    juce::Label audioModelLabel;       // F-02: frozen audio-model view vs fused shown label (read-only)
    juce::Label taxonomyNoteLabel;     // Optional first-class correction context for active learning
    juce::TextEditor taxonomyNoteEditor;
    juce::TextButton saveTaxonomyButton;
    juce::TextButton resetTaxonomyButton;
    // Experimental Tier-3 write: pushes the current tags into the sample's
    // folder Ableton XMP sidecar (see AbletonXmpWriter.h). Separate from
    // saveTaxonomyButton above -- that only edits this app's own database;
    // this is the one action that touches something Ableton itself reads.
    juce::TextButton writeAbletonXmpButton;

    juce::TextButton saveButton;
    juce::TextButton playButton;
    juce::TextButton stopButton;
    juce::TextButton findSimilarButton;
    juce::TextButton findSimilarToReferenceButton; // Reference Search
    juce::TextButton sortButton;
    juce::TextButton sortLibraryTopButton;
    juce::TextButton undoSortTopButton;
    juce::TextButton importButton;
    juce::TextButton reviewQueueButton;
    juce::TextButton evidenceImportButton;
    juce::TextButton exportDiagnosticsButton;
    juce::TextButton findDuplicatesButton;

    juce::Label namingLabel;
    juce::ComboBox namingCombo;

    std::unique_ptr<juce::FileChooser> fileChooser;

    // Visual drag-over indicator
    bool isDragOver = false;
    bool dragHasUnsupportedFiles = false;

    // Current selected item cache
    SampleItem selectedItem;
    bool hasSelection = false;
    juce::String inspectorSummaryBaseText;
    juce::Colour inspectorSummaryBaseColour = Tokens::mutedDim;
    bool selectionHiddenByFilters = false;

    std::vector<std::string> currentCategories;
    juce::TextButton clearFiltersButton;
    void updateCategoryButtons();

    // Shared by both the sidebar buttons and the native menu bar (Standalone/
    // macOS only -- see constructor), so there's one implementation of each
    // action instead of two.
    void openFolderScanner();
    void showDuplicatesReport();
    void performSortLibrary();
    // Actually starts the background sort (reorganizeSamplesAsync) -- split
    // from performSortLibrary() so the latter can show a confirmation dialog
    // first without duplicating the post-confirmation logic. See
    // docs/SORT_LIBRARY_BACKGROUND.md. copyInsteadOfMove is the user's
    // explicit choice from that dialog (Copy is the recommended default;
    // Move requires an extra not-reversible confirmation -- see
    // performSortLibrary()).
    void startSortLibrary(bool copyInsteadOfMove);
    void doStartSortLibrary(bool copyInsteadOfMove);
    void performRemoveMissingFiles();
    void showSimilarSamplesReport();
    void showReferenceSearchDialog();
    void showReviewQueue(bool unknownOnly = false);
    void showUnknownQueue();
    // Opens a read-only label-free evidence packet for review.  Imported
    // suggestions never mutate the engine, taxonomy, cache, or source files.
    void showEvidencePacketDialog();
    // F-04: one-click support bundle (versions, thresholds, receipt, splits,
    // log tail) via a save dialog. Export-only; never imports or mutates.
    void exportDiagnosticsBundle();

    MainMenuModel menuModel;
    bool nativeMenuBarActive = false;

    // Last engine sample-list version we've already pulled/rendered, so the poll
    // timer can skip the expensive copy+resync when nothing has changed.
    uint64_t lastSeenSamplesVersion = 0;
    size_t lastKnownSampleCount = 0;
    // A restored cache can already be populated while the engine's version
    // counter is still zero. Force one UI sync so cached rows/categories are
    // visible even when no new-sample FIFO event is emitted.
    bool hasCompletedInitialSampleSync = false;
    bool scanProgressVisualActive = false;
    // F-03 rescan-diff: previous tick's scan activity for completion-edge
    // detection, plus the last completed run's receipt line for the status
    // label ("Ready — +A ~C · F failed · S skipped").
    bool wasScanInProgress = false;
    juce::String lastScanReceiptText;

    void updateSelectionDetails(const SampleItem& item);
    void updateSelectionFilterCue();
    void saveSidebarMetadata();
    void updateCanvasFilters();

    // Category pills used to divide the filter bar's width evenly across
    // however many categories the current library happens to have, so a
    // real library with a dozen-plus categories squeezed every pill below
    // its label's readable width (every button showing just "..."). A
    // fixed pill width in a horizontally scrolling strip keeps labels
    // legible regardless of category count -- same fix shape as
    // sidebarViewport above.
    juce::Viewport filterBarViewport;
    juce::Component filterBarContent;
    static constexpr int filterPillWidth = 72;
    juce::OwnedArray<juce::TextButton> filterButtons;

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR(SmartSampleManagerAudioProcessorEditor)
};
