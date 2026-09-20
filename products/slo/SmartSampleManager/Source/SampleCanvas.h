#pragma once

#include <JuceHeader.h>
#include "SampleManagerEngine.h"
#include "QuadTree.h"
#include <string>
#include <map>
#include <unordered_map>
#include <vector>

// SLO Sample Map -- the sample-discovery canvas.
//
// MAP V4 rendering contract:
//
//  * Positions are the ML pipeline's UMAP coordinates, untouched. Nothing in
//    this component moves, jitters, clusters, snaps or otherwise reinterprets a
//    point's location -- spatial relationships stay truthful, and every visual
//    cue below is derived from real data or from pure view state (zoom/pan/
//    selection), never invented.
//  * Four point states carry the hierarchy: MUTED (filtered out -- recedes but
//    stays present so spatial context survives a filter), RESTING (quiet,
//    category-tinted), HOVERED (resolves an edge + tooltip), SELECTED (the
//    single strongest object on the canvas). Similarity emphasis is a separate,
//    additive channel layered on RESTING.
//  * State is encoded redundantly -- geometry (radius, detached ring), luminance
//    (near-white selected core) and colour -- so the map does not depend on
//    colour discrimination alone.
class SampleCanvas : public juce::Component,
                     private juce::Timer {
public:
    SampleCanvas();
    ~SampleCanvas() override = default;

    // Load new set of samples to display (full resync — replaces the whole list)
    void updateSamples(const std::vector<SampleItem>& newSamples);

    // Cheap incremental growth path: appends newly-arrived samples without
    // touching/copying any existing ones. Intended to be fed from the engine's
    // lock-free new-sample FIFO every frame (see PluginEditor::timerCallback).
    void appendNewSamples(const std::vector<SampleItem>& newOnes);

    // Callbacks
    void setSelectedCallback(std::function<void(const SampleItem&)> callback);
    void setDoubleClickedCallback(std::function<void(const SampleItem&)> callback);
    // Optional first-run action shown by the empty-state card. The editor owns
    // the actual workflow (normally the folder chooser); the map only exposes
    // the affordance and never starts scanning on its own.
    void setEmptyStateActionCallback(std::function<void()> callback);

    void setFilteredCategories(const std::vector<std::string>& activeCategories);
    // Explicit editor state; see the corresponding PrecisionBrowser overload.
    void setFilteredCategories(const std::vector<std::string>& activeCategories,
                               bool filterActive);

    // Free-text filter matched against name/key/BPM -- case-insensitive
    // substring match, empty string matches everything. Combined (AND) with
    // the category filter above. Cheap to call on every keystroke: paint()
    // and hit-testing only ever iterate the current viewport's points (via
    // the QuadTree spatial query), not the whole library, so this never
    // costs more than what per-frame rendering already pays regardless of
    // total library size.
    void setSearchQuery(const juce::String& query);

    // Keeps map state in step with browser, results and collection selection.
    // This deliberately updates only view state; selection ownership and all
    // engine data remain with the editor/engine contracts.
    void selectSampleByPath(const juce::String& filePath);

    // -- Discovery result overlay (Find Similar / Reference Search) ----------
    //
    // `orderedPaths` is the engine's similarity result, already ranked best-
    // first. The map draws those library samples with a discovery-blue
    // emphasis that decays with rank, so "how related" is legible without any
    // connection lines, without a network graph, and without inventing a
    // position for anything. Reference Search passes the same thing: the
    // external reference file has no UMAP coordinate, so it is deliberately
    // NOT plotted -- only its matching library neighbourhood lights up.
    void setSimilarSamples(const std::vector<std::string>& orderedPaths);
    void clearSimilarSamples();

    juce::Colour getColourForInstrumentType(const std::string& type) const;

    void paint(juce::Graphics& g) override;
    void resized() override;

    // Interaction handling
    void mouseDown(const juce::MouseEvent& event) override;
    void mouseUp(const juce::MouseEvent& event) override;
    void mouseDrag(const juce::MouseEvent& event) override;
    void mouseMove(const juce::MouseEvent& event) override;
    void mouseExit(const juce::MouseEvent& event) override;
    void mouseWheelMove(const juce::MouseEvent& event, const juce::MouseWheelDetails& wheel) override;
    void mouseMagnify(const juce::MouseEvent& event, float scaleFactor) override;

private:
    // Resting/active pair for one category string. Cached (see categoryStyles)
    // because resolving a category used to mean a std::string copy, an
    // in-place tolower() and up to seventeen substring searches -- per point,
    // per frame.
    struct CategoryStyle {
        juce::Colour resting;
        juce::Colour active;
    };

    // Helper to map 2D coordinates to pixel positions
    juce::Point<float> mapToPixelSpace(float x, float y) const;
    // Helper to map pixel positions back to 2D coordinates
    juce::Point<float> mapToCoordsSpace(float px, float py) const;

    float unitsToPixels() const;   // pixels per 1.0 embedding unit at the current zoom
    float pointRadius() const;     // resting point radius at the current zoom

    // Find index of dot under mouse cursor (-1 if none)
    int findDotAtPosition(juce::Point<float> pos) const;

    bool isCategoryActive(const std::string& type) const;
    bool matchesSearchQuery(const SampleItem& item) const;
    const CategoryStyle& styleFor(const std::string& type) const;
    // Per-sample memo of the above. styleFor() is a hashed string lookup; at
    // 5,000 visible points that measured ~0.27ms per frame on its own, which is
    // pure overhead when a point's category almost never changes. Resolving once
    // per sample and keeping the pointer (std::map references remain stable
    // when new categories are inserted) reduces the steady-state cost to a
    // dereference.
    const CategoryStyle& styleForIndex(int index) const;

    // Full bounding-box recompute + full QuadTree rebuild. Used whenever positions
    // may have moved (e.g. after a UMAP re-anchor) or the append-only fast path
    // in updateSamples() can't be trusted.
    void rebuildSpatialIndexFull();

    // Shared tail-insertion logic for updateSamples()'s append-only fast path and
    // appendNewSamples(): inserts samples[oldSize, samples.size()) into the
    // existing QuadTree if they fit within known bounds, else falls back to a
    // full rebuild.
    void insertNewPointsOrRebuild(size_t oldSize);

    // View helpers
    void fitToContent(bool animate);   // frame the whole library with margin
    void clampOffsets();               // keep the point cloud from being dragged off-screen
    void applyZoom(float factor, juce::Point<float> anchor, bool immediate);
    void beginAnimation();             // start the transition timer if it isn't already running
    void timerCallback() override;

    // Painting stages
    //
    // The canvas is drawn in two tiers. Everything that only depends on the
    // data and the view transform -- depth field, lattice, density field and
    // every non-interactive point -- is rasterised into `staticLayer` and
    // reused until the view or the data actually changes. Hover, selection,
    // labels and the tooltip are drawn over the top every frame.
    //
    // This matters because hover is by far the most frequent repaint trigger,
    // and it changes nothing about the point field. Measured on this machine
    // with 5,000 points, a full repaint costs ~85ms while the cached blit costs
    // ~1ms: JUCE's fillEllipse runs about 4us per call and setColour about 1us,
    // so redrawing thousands of points to move one highlight was the entire
    // cost of exploring the map.
    void invalidateStaticLayer();
    void rebuildStaticLayer(float scale);
    void rebuildDepthField(float scale);
    void paintDepthField(juce::Graphics& g, float scale);
    void paintGrid(juce::Graphics& g);
    void paintDensityField(juce::Graphics& g, const std::vector<int>& visible);
    juce::Rectangle<int> tooltipBoundsFor(int index, juce::String& nameOut, juce::String& metaOut) const;
    void paintTooltip(juce::Graphics& g, int index, float alpha);
    void paintPointLabel(juce::Graphics& g, int index, juce::Point<float> pos, float radius,
                         juce::Colour textColour, float alpha,
                         std::vector<juce::Rectangle<float>>& claimed);
    juce::String buildMetadataLine(int index) const;

    void rebuildSimilarRanks();        // resolve similar paths -> per-index rank
    float similarEmphasisFor(int index) const;

    std::vector<SampleItem> samples;
    std::vector<std::string> filteredCategories;
    bool categoryFilterActive = false;
    juce::String searchQueryLower;

    int selectedIdx = -1;
    // Selection identity must survive full sample-list replacements (for
    // example a UMAP re-anchor or library re-sort), where a row/index can move
    // to a different file. The editor and browser use the same path identity.
    std::string selectedFilePath;
    int hoveredIdx = -1;
    int hoverVisualIdx = -1;   // point currently drawn as hovered; retained through the fade-out

    // Coordinates bounding box for centering
    float minX = -1.0f, maxX = 1.0f;
    float minY = -1.0f, maxY = 1.0f;

    // Viewport transform. The `target*` values are what interaction sets; the
    // live values ease toward them so wheel zoom glides instead of stepping.
    float zoomScale = 1.0f,   targetZoom = 1.0f;
    float xOffset = 0.0f,     targetXOffset = 0.0f;
    float yOffset = 0.0f,     targetYOffset = 0.0f;

    // Interaction transition amounts, 0..1.
    float hoverAmount = 0.0f;
    float selectionAmount = 0.0f;
    double lastAnimationMs = 0.0;

    bool needsFit = true;         // frame the content once the component has a real size
    bool hasFittedOnce = false;   // first fit snaps; later auto-refits ease
    bool userHasNavigated = false; // once the user pans/zooms, the map stops reframing itself

    juce::Point<int> dragStartPos;
    juce::Point<int> pressOrigin;
    bool mouseIsDown = false;
    bool isPanning = false;
    bool pressHitAPoint = false;

    std::function<void(const SampleItem&)> onSelect;
    std::function<void(const SampleItem&)> onDoubleClick;
    std::function<void()> onEmptyStateAction;
    juce::Rectangle<int> emptyActionBounds;
    bool emptyActionHovered = false;

    QuadTree spatialIndex;

    // -- Reusable scratch state. Everything below is cleared (never freed) each
    // frame so steady-state painting and hit-testing do not allocate. --
    mutable std::vector<int> queryScratch;   // QuadTree results for paint()
    mutable std::vector<int> hitScratch;     // QuadTree results for hit testing
    std::vector<int> bucketMuted;            // filtered-out points, drawn first/lowest
    std::vector<int> bucketResting;          // everything else
    std::vector<int> bucketSimilar;          // similarity-emphasised points, drawn above resting
    std::vector<int> visibleForDensity;      // every non-muted visible point, feeds the density field
    std::vector<juce::Rectangle<float>> labelRects; // label collision guard at close zoom

    // A style reference is retained by pointsByStyle/stylePerSample while a
    // frame is built. std::map keeps those references stable when a scan adds
    // a new category; unordered_map rehashing would invalidate them.
    mutable std::map<std::string, CategoryStyle> categoryStyles;
    mutable std::vector<const CategoryStyle*> stylePerSample; // nullptr = not resolved yet

    // Cached, near-imperceptible depth field (radial lift at the centre,
    // sinking at the edges). Rasterised once per resize rather than as a
    // full-bounds gradient on every repaint.
    juce::Image depthField;
    float depthFieldScale = 0.0f;

    // See invalidateStaticLayer(). Held at device resolution so points and the
    // lattice stay crisp on Retina rather than being upscaled from logical size.
    juce::Image staticLayer;
    float staticLayerScale = 1.0f;
    bool  staticLayerDirty = true;

    // Resting points are drawn seats-first-then-cores-grouped-by-category
    // rather than colour/shape/colour/shape per point, because every setColour
    // is a real cost at these counts. This holds the grouping.
    std::vector<std::pair<const CategoryStyle*, std::vector<int>>> pointsByStyle;

    // Cluster density field. Accumulated from the *actual* on-screen positions
    // of visible points into a coarse cell grid, blurred, then drawn as one
    // upscaled image -- so it reports real local density and never implies a
    // cluster boundary or membership the embedding does not contain.
    juce::Image densityImage;
    std::vector<float> densityCells;
    std::vector<float> densityScratch;
    int densityCols = 0, densityRows = 0;

    // Similarity rank by sample index (-1 = not in the current result set,
    // 0 = best match). Rebuilt whenever the sample list or the result changes.
    std::vector<std::string> similarPaths;
    std::vector<int> similarRank;
    bool similarDirty = false;

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR(SampleCanvas)
};
