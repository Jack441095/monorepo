#include "SampleCanvas.h"
#include "ClassificationPresentation.h"
#include "DesignTokens.h"
#include "SearchLexicon.h"
#include <algorithm>
#include <cmath>

namespace
{
    constexpr float kMinZoom = 0.10f;
    constexpr float kMaxZoom = 24.0f;

    // Base projection scale: pixels per embedding unit at zoomScale == 1.
    inline float baseScaleFor(int w, int h) noexcept
    {
        return static_cast<float>(std::min(w, h)) * 0.35f;
    }

    // Density field cell size in logical pixels. Coarse on purpose -- the field
    // is upscaled bilinearly, so the cell grid is a low-frequency estimator, not
    // something the user ever sees the edges of.
    constexpr int   kDensityCell        = 26;
    constexpr float kDensityMaxAlpha    = 0.155f;
    constexpr int   kDensityMinPoints   = 40;    // below this there is no cluster structure worth showing

    // Semantic zoom thresholds.
    constexpr float kLabelZoom          = 3.5f;  // below this, never draw per-point labels
    constexpr int   kLabelMaxPoints     = 32;    // and never when the viewport is still crowded

    // Tooltip metrics.
    constexpr int kTipPadX = 11, kTipPadY = 8, kTipAccentW = 3, kTipGap = 3;

    inline float smoothIn(float t) noexcept { return std::pow(juce::jlimit(0.0f, 1.0f, t), 0.62f); }
}

SampleCanvas::SampleCanvas()
{
    setMouseCursor(juce::MouseCursor::NormalCursor);
    setOpaque(true);
    // The editor routes browse shortcuts through its parent, but the map still
    // needs to visibly claim focus when a user clicks or tabs into it. This is
    // intentionally a component-level affordance rather than a new interaction
    // model: arrows/Space/Return continue to use the existing editor commands.
    setWantsKeyboardFocus(true);
    setMouseClickGrabsKeyboardFocus(true);
}

// ---------------------------------------------------------------------------
// Data
// ---------------------------------------------------------------------------

void SampleCanvas::rebuildSpatialIndexFull()
{
    minX = samples[0].x; maxX = samples[0].x;
    minY = samples[0].y; maxY = samples[0].y;

    for (const auto& s : samples) {
        minX = std::min(minX, s.x);
        maxX = std::max(maxX, s.x);
        minY = std::min(minY, s.y);
        maxY = std::max(maxY, s.y);
    }

    spatialIndex.clear();
    float marginX = std::max(1.0f, (maxX - minX) * 0.1f);
    float marginY = std::max(1.0f, (maxY - minY) * 0.1f);
    spatialIndex.build(juce::Rectangle<float>(minX - marginX, minY - marginY, (maxX - minX) + 2.0f * marginX, (maxY - minY) + 2.0f * marginY), samples);

    // While a scan is still filling the library the point cloud keeps growing,
    // so keep reframing it -- but only until the user takes the view over. After
    // the first pan or zoom the map is theirs and must never move on its own.
    if (!userHasNavigated) needsFit = true;
}

void SampleCanvas::insertNewPointsOrRebuild(size_t oldSize)
{
    // Check the newly-appended points still fall inside the previously known
    // bounds before trusting incremental insert; if not, fall back to a full
    // rebuild so the bounding box stays correct.
    bool allFit = true;
    for (size_t i = oldSize; i < samples.size(); ++i) {
        const auto& s = samples[i];
        if (s.x < minX || s.x > maxX || s.y < minY || s.y > maxY) {
            allFit = false;
            break;
        }
    }

    if (!allFit) {
        rebuildSpatialIndexFull();
    } else {
        for (size_t i = oldSize; i < samples.size(); ++i) {
            spatialIndex.insert(static_cast<int>(i));
        }
    }
}

void SampleCanvas::updateSamples(const std::vector<SampleItem>& newSamples)
{
    if (selectedIdx >= 0 && selectedIdx < static_cast<int>(samples.size()))
        selectedFilePath = samples[static_cast<size_t>(selectedIdx)].filePath;

    if (!selectedFilePath.empty())
    {
        const bool stillInLibrary = std::any_of(newSamples.begin(), newSamples.end(),
            [this](const SampleItem& item) { return item.filePath == selectedFilePath; });
        if (!stillInLibrary)
            selectedFilePath.clear();
    }

    // Heuristic: during an active scan, new samples are simply appended to the
    // tail and existing ones never move (positions only change on an explicit
    // UMAP re-anchor, which also rewrites earlier entries/paths). When that holds,
    // skip the full O(N) bounding-box scan + QuadTree rebuild and just insert the
    // new tail — this is what keeps a poll-driven resync cheap once a library is large.
    bool appendOnly = spatialIndex.isBuilt()
                        && !samples.empty()
                        && newSamples.size() > samples.size()
                        && samples.front().filePath == newSamples.front().filePath;

    size_t oldSize = samples.size();
    samples = newSamples;
    similarDirty = true;
    invalidateStaticLayer();
    // On a full resync any index may now hold a different sample (or the same
    // sample with edited tags), so the per-sample category memo is dropped. The
    // append-only path leaves the existing prefix untouched, so it keeps it.
    if (!appendOnly) stylePerSample.clear();

    if (samples.empty()) {
        selectedIdx = -1;
        selectedFilePath.clear();
        hoveredIdx = -1;
        hoverVisualIdx = -1;
        spatialIndex.clear();
        stylePerSample.clear();
        needsFit = true;
        repaint();
        return;
    }

    if (!appendOnly) {
        rebuildSpatialIndexFull();
    } else {
        insertNewPointsOrRebuild(oldSize);
    }

    selectedIdx = -1;
    if (!selectedFilePath.empty())
    {
        for (size_t i = 0; i < samples.size(); ++i)
        {
            if (samples[i].filePath == selectedFilePath)
            {
                selectedIdx = static_cast<int>(i);
                break;
            }
        }
    }

    repaint();
}

void SampleCanvas::appendNewSamples(const std::vector<SampleItem>& newOnes)
{
    // Cheap incremental path fed by the engine's lock-free new-sample FIFO
    // (see PluginEditor::timerCallback): unlike updateSamples(), this never
    // copies/replaces the whole sample list — it only ever grows it, so it's
    // safe to call every frame from a 60Hz timer even once the library is huge.
    if (newOnes.empty()) return;

    bool wasEmpty = samples.empty();
    size_t oldSize = samples.size();
    samples.insert(samples.end(), newOnes.begin(), newOnes.end());
    similarDirty = true;
    invalidateStaticLayer();

    if (wasEmpty) {
        rebuildSpatialIndexFull();
    } else {
        insertNewPointsOrRebuild(oldSize);
    }

    repaint();
}

void SampleCanvas::setSelectedCallback(std::function<void(const SampleItem&)> callback)
{
    onSelect = callback;
}

void SampleCanvas::setDoubleClickedCallback(std::function<void(const SampleItem&)> callback)
{
    onDoubleClick = callback;
}

void SampleCanvas::setEmptyStateActionCallback(std::function<void()> callback)
{
    onEmptyStateAction = std::move(callback);
}

void SampleCanvas::setFilteredCategories(const std::vector<std::string>& activeCategories)
{
    // Keep the simple component API intuitive: non-empty means narrowed;
    // empty means the default unfiltered view.
    setFilteredCategories(activeCategories, !activeCategories.empty());
}

void SampleCanvas::setFilteredCategories(const std::vector<std::string>& activeCategories,
                                         bool filterActive)
{
    filteredCategories = activeCategories;
    // Keep an explicit all-off state distinct from the default unfiltered
    // view. The editor passes filterActive=true when pills exist but none are
    // selected; an ordinary empty call still means "show all".
    categoryFilterActive = filterActive;
    invalidateStaticLayer();
    repaint();
}

void SampleCanvas::setSearchQuery(const juce::String& query)
{
    searchQueryLower = query.trim().toLowerCase();
    invalidateStaticLayer();
    repaint();
}

void SampleCanvas::selectSampleByPath(const juce::String& filePath)
{
    const auto target = filePath.toStdString();
    for (size_t i = 0; i < samples.size(); ++i)
    {
        if (samples[i].filePath == target)
        {
            if (selectedIdx != static_cast<int>(i)) {
                selectedIdx = static_cast<int>(i);
                selectionAmount = 0.0f;
                beginAnimation();
            }
            selectedFilePath = samples[i].filePath;
            repaint();
            return;
        }
    }
}

void SampleCanvas::setSimilarSamples(const std::vector<std::string>& orderedPaths)
{
    similarPaths = orderedPaths;
    similarDirty = true;
    invalidateStaticLayer();
    repaint();
}

void SampleCanvas::clearSimilarSamples()
{
    if (similarPaths.empty()) return;
    similarPaths.clear();
    similarRank.clear();
    similarDirty = false;
    invalidateStaticLayer();
    repaint();
}

void SampleCanvas::rebuildSimilarRanks()
{
    similarDirty = false;
    similarRank.assign(samples.size(), -1);
    if (similarPaths.empty()) return;

    std::unordered_map<std::string, int> rankByPath;
    rankByPath.reserve(similarPaths.size() * 2);
    for (size_t r = 0; r < similarPaths.size(); ++r)
        rankByPath.emplace(similarPaths[r], static_cast<int>(r));

    for (size_t i = 0; i < samples.size(); ++i) {
        auto it = rankByPath.find(samples[i].filePath);
        if (it != rankByPath.end())
            similarRank[i] = it->second;
    }
}

float SampleCanvas::similarEmphasisFor(int index) const
{
    if (index < 0 || index >= static_cast<int>(similarRank.size())) return 0.0f;
    const int rank = similarRank[static_cast<size_t>(index)];
    if (rank < 0) return 0.0f;
    const float span = static_cast<float>(std::max<size_t>(1, similarPaths.size() - 1));
    // Best match reads at full strength, the tail of the result still reads as
    // "related" rather than fading into the resting field.
    return juce::jlimit(0.38f, 1.0f, 1.0f - 0.62f * (static_cast<float>(rank) / span));
}

// ---------------------------------------------------------------------------
// View transform
// ---------------------------------------------------------------------------

float SampleCanvas::unitsToPixels() const
{
    return baseScaleFor(getWidth(), getHeight()) * zoomScale;
}

float SampleCanvas::pointRadius() const
{
    // Points grow sub-linearly with zoom: a library viewed whole stays a field
    // of small, countable marks; zoomed in, each point becomes an object with
    // room for an edge and a ring. Never an orb.
    return juce::jlimit(Tokens::mapPointRadiusMin, Tokens::mapPointRadiusMax,
                        Tokens::mapPointRadiusRef * std::pow(zoomScale, 0.28f));
}

juce::Point<float> SampleCanvas::mapToPixelSpace(float x, float y) const
{
    float cx = static_cast<float>(getLocalBounds().getCentreX()) + xOffset;
    float cy = static_cast<float>(getLocalBounds().getCentreY()) + yOffset;
    float s = unitsToPixels();
    return { cx + x * s, cy - y * s }; // standard inversion for Cartesian plane
}

juce::Point<float> SampleCanvas::mapToCoordsSpace(float px, float py) const
{
    float cx = static_cast<float>(getLocalBounds().getCentreX()) + xOffset;
    float cy = static_cast<float>(getLocalBounds().getCentreY()) + yOffset;
    float s = unitsToPixels();
    if (s <= 0.0f) return { 0.0f, 0.0f };
    return { (px - cx) / s, (cy - py) / s };
}

void SampleCanvas::fitToContent(bool animate)
{
    if (samples.empty() || getWidth() <= 0 || getHeight() <= 0) return;

    const float base = baseScaleFor(getWidth(), getHeight());
    if (base <= 0.0f) return;

    const float spanX = std::max(1.0e-3f, maxX - minX);
    const float spanY = std::max(1.0e-3f, maxY - minY);
    const float margin = 0.86f; // leave a real border so edge points aren't clipped by their own rings

    const float z = juce::jlimit(kMinZoom, kMaxZoom,
                                 std::min((static_cast<float>(getWidth())  * margin) / (spanX * base),
                                          (static_cast<float>(getHeight()) * margin) / (spanY * base)));
    const float s = base * z;

    targetZoom    = z;
    targetXOffset = -0.5f * (minX + maxX) * s;
    targetYOffset =  0.5f * (minY + maxY) * s;

    if (!animate) {
        zoomScale = targetZoom;
        xOffset   = targetXOffset;
        yOffset   = targetYOffset;
    } else {
        beginAnimation();
    }

    needsFit = false;
    hasFittedOnce = true;
    invalidateStaticLayer();
}

void SampleCanvas::clampOffsets()
{
    if (getWidth() <= 0 || getHeight() <= 0) return;

    // Keep at least `keep` pixels of the point cloud on screen in each axis, so
    // the map can never be flung into an empty void the user has to guess their
    // way back from. This is a soft bound, not a hard scroll region: there is
    // still plenty of overscroll for inspecting an edge cluster comfortably.
    const float keep = 72.0f;
    const float s  = baseScaleFor(getWidth(), getHeight()) * targetZoom;
    const float cx = static_cast<float>(getLocalBounds().getCentreX());
    const float cy = static_cast<float>(getLocalBounds().getCentreY());

    const float xLo = keep - cx - maxX * s;
    const float xHi = static_cast<float>(getWidth()) - keep - cx - minX * s;
    if (xLo <= xHi) targetXOffset = juce::jlimit(xLo, xHi, targetXOffset);

    const float yLo = keep - cy + minY * s;
    const float yHi = static_cast<float>(getHeight()) - keep - cy + maxY * s;
    if (yLo <= yHi) targetYOffset = juce::jlimit(yLo, yHi, targetYOffset);
}

void SampleCanvas::applyZoom(float factor, juce::Point<float> anchor, bool immediate)
{
    const float newZoom = juce::jlimit(kMinZoom, kMaxZoom, targetZoom * factor);
    if (std::abs(newZoom - targetZoom) < 1.0e-5f) return;

    userHasNavigated = true;
    needsFit = false;   // a deliberate gesture always wins over a pending auto-fit

    // Zoom about the cursor: the point under the pointer stays under the pointer.
    const float ratio = newZoom / targetZoom;
    const float ax = anchor.x - static_cast<float>(getLocalBounds().getCentreX()) - targetXOffset;
    const float ay = anchor.y - static_cast<float>(getLocalBounds().getCentreY()) - targetYOffset;

    targetXOffset -= ax * (ratio - 1.0f);
    targetYOffset -= ay * (ratio - 1.0f);
    targetZoom = newZoom;
    clampOffsets();

    if (immediate) {
        zoomScale = targetZoom;
        xOffset   = targetXOffset;
        yOffset   = targetYOffset;
        invalidateStaticLayer();
        repaint();
    } else {
        beginAnimation();
    }
}

void SampleCanvas::beginAnimation()
{
    if (!isTimerRunning()) {
        lastAnimationMs = juce::Time::getMillisecondCounterHiRes();
        startTimerHz(60);
    }
}

void SampleCanvas::timerCallback()
{
    const double now = juce::Time::getMillisecondCounterHiRes();
    const float dt = static_cast<float>(juce::jlimit(1.0, 64.0, now - lastAnimationMs));
    lastAnimationMs = now;

    // Frame-rate independent exponential ease. tau ~46ms settles in ~150ms,
    // which is the band the brief asks for: felt, never waited on.
    const float k = 1.0f - std::exp(-dt / Tokens::mapMotionTauMs);

    bool moving = false;
    auto approach = [&](float& v, float target, float eps) {
        const float d = target - v;
        if (std::abs(d) > eps) { v += d * k; moving = true; return true; }
        v = target;
        return false;
    };

    // Only a change to the view transform invalidates the cached point field.
    // Hover and selection transitions are drawn as overlays, so they cost a
    // blit and a handful of shapes no matter how large the library is.
    bool viewMoved = false;
    viewMoved |= approach(zoomScale, targetZoom,    1.0e-4f);
    viewMoved |= approach(xOffset,   targetXOffset, 0.05f);
    viewMoved |= approach(yOffset,   targetYOffset, 0.05f);

    approach(hoverAmount,     hoveredIdx  >= 0 ? 1.0f : 0.0f, 2.0e-3f);
    approach(selectionAmount, selectedIdx >= 0 ? 1.0f : 0.0f, 2.0e-3f);

    if (viewMoved) invalidateStaticLayer();

    if (hoveredIdx < 0 && hoverAmount <= 2.0e-3f)
        hoverVisualIdx = -1;

    repaint();

    if (!moving)
        stopTimer();
}

void SampleCanvas::resized()
{
    // Dropped rather than rebuilt here: the device scale isn't known until a
    // Graphics context arrives, so paintDepthField() rebuilds it on demand.
    depthField = juce::Image();
    depthFieldScale = 0.0f;

    const int cols = juce::jmax(4, getWidth()  / kDensityCell + 3);
    const int rows = juce::jmax(4, getHeight() / kDensityCell + 3);
    if (cols != densityCols || rows != densityRows) {
        densityCols = cols;
        densityRows = rows;
        densityCells.assign(static_cast<size_t>(cols) * static_cast<size_t>(rows), 0.0f);
        densityScratch.assign(densityCells.size(), 0.0f);
        densityImage = juce::Image(juce::NativeImageType().create(juce::Image::ARGB, cols, rows, true));
    }

    if (needsFit) fitToContent(false);
    clampOffsets();
    xOffset = targetXOffset;
    yOffset = targetYOffset;
    invalidateStaticLayer();
}

// ---------------------------------------------------------------------------
// Painting
// ---------------------------------------------------------------------------

void SampleCanvas::rebuildDepthField(float scale)
{
    const int w = getWidth(), h = getHeight();
    if (w <= 0 || h <= 0) { depthField = juce::Image(); depthFieldScale = 0.0f; return; }

    // Held at full device resolution rather than a small upscaled source. The
    // vignette is static in *screen* space -- it does not move with pan or
    // zoom -- so caching it at 1:1 turns it into a straight blit inside the
    // layer rebuild. Rasterising a small source and resampling it up cost
    // several milliseconds on every pan frame for a gradient that had not
    // changed at all.
    const int iw = juce::jmax(8, juce::roundToInt(static_cast<float>(w) * scale));
    const int ih = juce::jmax(8, juce::roundToInt(static_cast<float>(h) * scale));

    depthField = juce::Image(juce::NativeImageType().create(juce::Image::RGB, iw, ih, false));
    depthFieldScale = scale;

    juce::Graphics ig(depthField);
    juce::ColourGradient grad(Tokens::mapCentreLift,
                              static_cast<float>(iw) * 0.5f, static_cast<float>(ih) * 0.5f,
                              Tokens::mapEdgeSink, 0.0f, 0.0f, true);
    grad.addColour(0.58, Tokens::background);
    ig.setGradientFill(grad);
    ig.fillAll();
}

void SampleCanvas::paintDepthField(juce::Graphics& g, float scale)
{
    const int wantW = juce::jmax(8, juce::roundToInt(static_cast<float>(getWidth())  * scale));
    const int wantH = juce::jmax(8, juce::roundToInt(static_cast<float>(getHeight()) * scale));

    if (!depthField.isValid() || depthField.getWidth() != wantW || depthField.getHeight() != wantH)
        rebuildDepthField(scale);

    if (depthField.isValid()) {
        // `g` already carries the device scale, so scaling the image back down
        // by the same factor leaves an identity transform in device space --
        // i.e. a 1:1 blit, no resampling.
        g.drawImageTransformed(depthField, juce::AffineTransform::scale(1.0f / scale), false);
    } else {
        g.fillAll(Tokens::background);
    }
}

void SampleCanvas::paintGrid(juce::Graphics& g)
{
    // Deliberately NOT a chart grid. There are no axes: a UMAP projection has
    // no meaningful origin, so drawing x=0/y=0 implied a coordinate system that
    // does not exist. What remains is a whisper-level reference lattice whose
    // only job is to give pan and zoom something to move against.
    //
    // Three levels are drawn at once with the finest fading out and the coarsest
    // fading in, so the lattice subdivides continuously as you zoom instead of
    // popping between densities the way a fixed `step *= 5` rule does.
    const float unit = unitsToPixels();
    if (unit <= 1.0e-3f) return;

    constexpr float kTargetSpacing = 150.0f;
    const float lvl      = std::log(kTargetSpacing / unit) / std::log(4.0f);
    const float lvlFloor = std::floor(lvl);
    const float frac     = lvl - lvlFloor;

    const float base = unit * std::pow(4.0f, lvlFloor);
    if (base <= 2.0f) return;

    const float cx = static_cast<float>(getLocalBounds().getCentreX()) + xOffset;
    const float cy = static_cast<float>(getLocalBounds().getCentreY()) + yOffset;
    const float w = static_cast<float>(getWidth());
    const float h = static_cast<float>(getHeight());
    const float baseAlpha = Tokens::mapGrid.getFloatAlpha();

    const float steps[3]  = { base, base * 4.0f, base * 16.0f };
    const float alphas[3] = { baseAlpha * (1.0f - frac), baseAlpha, baseAlpha * frac };

    for (int level = 0; level < 3; ++level) {
        const float step = steps[level];
        if (alphas[level] < 0.002f || step < 12.0f || step > 4000.0f) continue;

        g.setColour(Tokens::mapGrid.withAlpha(alphas[level]));

        float startX = std::fmod(cx, step);
        if (startX < 0.0f) startX += step;
        for (float x = startX; x < w; x += step)
            g.drawVerticalLine(static_cast<int>(std::round(x)), 0.0f, h);

        float startY = std::fmod(cy, step);
        if (startY < 0.0f) startY += step;
        for (float y = startY; y < h; y += step)
            g.drawHorizontalLine(static_cast<int>(std::round(y)), 0.0f, w);
    }
}

void SampleCanvas::paintDensityField(juce::Graphics& g, const std::vector<int>& visible)
{
    if (densityCols <= 0 || densityRows <= 0 || !densityImage.isValid()) return;
    if (static_cast<int>(visible.size()) < kDensityMinPoints) return;

    // The field fades out as you zoom in: far out it answers "where are the
    // neighbourhoods"; close in the individual points answer that themselves and
    // any wash would only dilute them.
    const float zoomFade = juce::jlimit(0.0f, 1.0f, (4.0f - zoomScale) / 2.5f);
    if (zoomFade <= 0.01f) return;

    const size_t cellCount = densityCells.size();
    std::fill(densityCells.begin(), densityCells.end(), 0.0f);

    // Grid origin is one cell outside the component so the blurred field fades
    // out at the edges instead of being clipped flat.
    const float originX = -static_cast<float>(kDensityCell);
    const float originY = -static_cast<float>(kDensityCell);

    for (int i : visible) {
        const auto& pt = samples[static_cast<size_t>(i)];
        const auto p = mapToPixelSpace(pt.x, pt.y);
        const int cxi = static_cast<int>((p.x - originX) / kDensityCell);
        const int cyi = static_cast<int>((p.y - originY) / kDensityCell);
        if (cxi < 0 || cyi < 0 || cxi >= densityCols || cyi >= densityRows) continue;
        densityCells[static_cast<size_t>(cyi) * static_cast<size_t>(densityCols) + static_cast<size_t>(cxi)] += 1.0f;
    }

    // Two separable 1-2-1 passes. Cheap (a few thousand float ops) and enough to
    // turn a cell histogram into something that reads as a continuous field.
    for (int pass = 0; pass < 2; ++pass) {
        for (int y = 0; y < densityRows; ++y) {
            const size_t row = static_cast<size_t>(y) * static_cast<size_t>(densityCols);
            for (int x = 0; x < densityCols; ++x) {
                const float l = (x > 0) ? densityCells[row + static_cast<size_t>(x - 1)] : 0.0f;
                const float c = densityCells[row + static_cast<size_t>(x)];
                const float r = (x + 1 < densityCols) ? densityCells[row + static_cast<size_t>(x + 1)] : 0.0f;
                densityScratch[row + static_cast<size_t>(x)] = (l + 2.0f * c + r) * 0.25f;
            }
        }
        for (int x = 0; x < densityCols; ++x) {
            for (int y = 0; y < densityRows; ++y) {
                const size_t idx = static_cast<size_t>(y) * static_cast<size_t>(densityCols) + static_cast<size_t>(x);
                const float u = (y > 0) ? densityScratch[idx - static_cast<size_t>(densityCols)] : 0.0f;
                const float c = densityScratch[idx];
                const float d = (y + 1 < densityRows) ? densityScratch[idx + static_cast<size_t>(densityCols)] : 0.0f;
                densityCells[idx] = (u + 2.0f * c + d) * 0.25f;
            }
        }
    }

    float peak = 0.0f;
    for (size_t i = 0; i < cellCount; ++i) peak = std::max(peak, densityCells[i]);
    if (peak <= 1.0e-4f) return;

    const float maxAlpha = kDensityMaxAlpha * zoomFade;
    {
        juce::Image::BitmapData bd(densityImage, juce::Image::BitmapData::writeOnly);
        for (int y = 0; y < densityRows; ++y) {
            for (int x = 0; x < densityCols; ++x) {
                const float v = densityCells[static_cast<size_t>(y) * static_cast<size_t>(densityCols) + static_cast<size_t>(x)] / peak;
                const float a = std::pow(juce::jlimit(0.0f, 1.0f, v), 0.75f) * maxAlpha;
                bd.setPixelColour(x, y, Tokens::mapDensity.withAlpha(a));
            }
        }
    }

    g.setImageResamplingQuality(juce::Graphics::mediumResamplingQuality);
    g.drawImage(densityImage,
                juce::Rectangle<float>(originX, originY,
                                       static_cast<float>(densityCols * kDensityCell),
                                       static_cast<float>(densityRows * kDensityCell)),
                juce::RectanglePlacement::stretchToFit, false);
}

juce::String SampleCanvas::buildMetadataLine(int index) const
{
    const auto& s = samples[static_cast<size_t>(index)];
    juce::StringArray parts;

    const auto primaryLabel = ClassificationPresentation::primaryLabel(
        s.category, s.subcategory, s.instrumentType, s.tagSource);
    const juce::String cat(primaryLabel);
    if (cat.isNotEmpty() && !cat.equalsIgnoreCase("unknown")) parts.add(cat);

    if (!s.key.empty() && s.key != "Unknown") {
        const bool oneShot = s.subcategory.find("Loop") == std::string::npos
            && s.subcategory.find("loop") == std::string::npos;
        parts.add(formatKeyForSampleName(juce::String(s.key), oneShot));
    }
    if (s.bpm > 0.0f)             parts.add(juce::String(juce::roundToInt(s.bpm)) + " BPM");
    if (s.durationSeconds > 0.0f) parts.add(juce::String(s.durationSeconds, 1) + "s");

    if (parts.isEmpty()) return "Not yet analysed";
    return parts.joinIntoString("  " + juce::String(juce::CharPointer_UTF8("\xe2\x80\xa2")) + "  ");
}

// Geometry only, so paint() can reserve the tooltip's footprint before it
// places any point labels -- otherwise a label sits underneath the card and is
// half-hidden by it.
juce::Rectangle<int> SampleCanvas::tooltipBoundsFor(int index, juce::String& nameOut, juce::String& metaOut) const
{
    const auto& s = samples[static_cast<size_t>(index)];
    const auto pos = mapToPixelSpace(s.x, s.y);

    const juce::Font nameFont(juce::FontOptions().withHeight(Tokens::fontBody));
    const juce::Font metaFont(juce::FontOptions().withHeight(Tokens::fontLabel));

    nameOut = juce::String(s.name);
    metaOut = buildMetadataLine(index);

    const int rank = (index < static_cast<int>(similarRank.size())) ? similarRank[static_cast<size_t>(index)] : -1;
    if (rank >= 0)
        metaOut = "#" + juce::String(rank + 1) + " match  "
                    + juce::String(juce::CharPointer_UTF8("\xe2\x80\xa2")) + "  " + metaOut;

    const float nameW = juce::GlyphArrangement::getStringWidth(nameFont, nameOut);
    const float metaW = juce::GlyphArrangement::getStringWidth(metaFont, metaOut);

    const int boxW = juce::jlimit(150, 300, static_cast<int>(std::ceil(std::max(nameW, metaW))) + kTipPadX * 2 + kTipAccentW);
    const int nameH = static_cast<int>(std::ceil(Tokens::fontBody)) + 3;
    const int metaH = static_cast<int>(std::ceil(Tokens::fontLabel)) + 3;
    const int boxH = kTipPadY * 2 + nameH + kTipGap + metaH;

    // Prefer to sit to the right of the point and vertically centred on it, then
    // flip/clamp. Positions are pixel-snapped so the 1px border and the text
    // baseline land on device pixels instead of straddling them on Retina.
    const float r = pointRadius();
    int boxX = static_cast<int>(std::round(pos.x + r + 12.0f));
    int boxY = static_cast<int>(std::round(pos.y - static_cast<float>(boxH) * 0.5f));

    if (boxX + boxW > getWidth() - 6)  boxX = static_cast<int>(std::round(pos.x - r - 12.0f)) - boxW;
    boxX = juce::jlimit(6, juce::jmax(6, getWidth()  - boxW - 6), boxX);
    boxY = juce::jlimit(6, juce::jmax(6, getHeight() - boxH - 6), boxY);

    return { boxX, boxY, boxW, boxH };
}

void SampleCanvas::paintTooltip(juce::Graphics& g, int index, float alpha)
{
    if (index < 0 || index >= static_cast<int>(samples.size())) return;
    alpha = juce::jlimit(0.0f, 1.0f, alpha);
    if (alpha <= 0.01f) return;

    juce::String name, meta;
    const auto boxI = tooltipBoundsFor(index, name, meta);
    const int boxX = boxI.getX(), boxY = boxI.getY(), boxW = boxI.getWidth();
    const int nameH = static_cast<int>(std::ceil(Tokens::fontBody)) + 3;
    const int metaH = static_cast<int>(std::ceil(Tokens::fontLabel)) + 3;

    const juce::Font nameFont(juce::FontOptions().withHeight(Tokens::fontBody));
    const juce::Font metaFont(juce::FontOptions().withHeight(Tokens::fontLabel));

    const juce::Rectangle<float> box = boxI.toFloat();

    // Two-step contact shadow. Cheaper than juce::DropShadow (which rasterises
    // and caches an image) and enough to lift the card off a near-black canvas.
    g.setColour(juce::Colours::black.withAlpha(0.28f * alpha));
    g.fillRoundedRectangle(box.translated(0.0f, 2.0f).expanded(1.0f), Tokens::cornerRadiusLg + 1.0f);
    g.setColour(juce::Colours::black.withAlpha(0.18f * alpha));
    g.fillRoundedRectangle(box.translated(0.0f, 4.0f).expanded(2.0f), Tokens::cornerRadiusLg + 2.0f);

    g.setColour(Tokens::surfaceRaised.withMultipliedAlpha(alpha * 0.98f));
    g.fillRoundedRectangle(box, Tokens::cornerRadiusLg);
    g.setColour(Tokens::borderStrong.withMultipliedAlpha(alpha));
    g.drawRoundedRectangle(box.reduced(0.5f), Tokens::cornerRadiusLg, 1.0f);

    // Category identity as a thin edge rather than a coloured card: ties the
    // tooltip to the point it came from without shouting.
    const auto& style = styleForIndex(index);
    g.setColour(style.active.withMultipliedAlpha(alpha * 0.9f));
    g.fillRoundedRectangle(box.getX() + 3.0f, box.getY() + 6.0f,
                           static_cast<float>(kTipAccentW), box.getHeight() - 12.0f, 1.5f);

    juce::Rectangle<int> text(boxX + kTipPadX + kTipAccentW, boxY + kTipPadY,
                              boxW - kTipPadX * 2 - kTipAccentW, nameH + kTipGap + metaH);

    g.setFont(nameFont);
    g.setColour(Tokens::foreground.withMultipliedAlpha(alpha));
    g.drawText(name, text.removeFromTop(nameH), juce::Justification::centredLeft, true);

    text.removeFromTop(kTipGap);
    g.setFont(metaFont);
    g.setColour(Tokens::muted.withMultipliedAlpha(alpha));
    g.drawText(meta, text.removeFromTop(metaH), juce::Justification::centredLeft, true);
}

void SampleCanvas::paintPointLabel(juce::Graphics& g, int index, juce::Point<float> pos, float radius,
                                   juce::Colour textColour, float alpha,
                                   std::vector<juce::Rectangle<float>>& claimed)
{
    if (alpha <= 0.02f) return;

    const juce::Font font(juce::FontOptions().withHeight(Tokens::fontLabel));
    juce::String name = juce::String(samples[static_cast<size_t>(index)].name);

    const float w = juce::jmin(132.0f, juce::GlyphArrangement::getStringWidth(font, name) + 6.0f);
    const float h = Tokens::fontLabel + 4.0f;
    juce::Rectangle<float> r(std::round(pos.x - w * 0.5f), std::round(pos.y + radius + 5.0f), w, h);

    if (r.getRight() < 0.0f || r.getX() > static_cast<float>(getWidth())
        || r.getBottom() < 0.0f || r.getY() > static_cast<float>(getHeight()))
        return;

    for (const auto& taken : claimed)
        if (taken.expanded(2.0f).intersects(r)) return; // never let labels collide into noise

    claimed.push_back(r);

    // A hair of backing so a label stays readable where it crosses a dense
    // cluster, without becoming a second card competing with the tooltip.
    g.setColour(Tokens::background.withAlpha(0.72f * alpha));
    g.fillRoundedRectangle(r.expanded(2.0f, 0.0f), Tokens::cornerRadiusSm);

    g.setFont(font);
    g.setColour(textColour.withMultipliedAlpha(alpha));
    g.drawText(name, r.toNearestInt(), juce::Justification::centred, true);
}

void SampleCanvas::invalidateStaticLayer()
{
    staticLayerDirty = true;
}

void SampleCanvas::rebuildStaticLayer(float scale)
{
    juce::Graphics ig(staticLayer);
    ig.addTransform(juce::AffineTransform::scale(scale));

    paintDepthField(ig, scale);
    paintGrid(ig);

    bucketMuted.clear();
    bucketResting.clear();
    bucketSimilar.clear();
    visibleForDensity.clear();
    for (auto& entry : pointsByStyle) entry.second.clear();

    staticLayerDirty = false;

    if (samples.empty() || !spatialIndex.isBuilt())
        return;

    // ---- viewport cull -----------------------------------------------------
    // Expanded by the widest thing a single point can draw (the selection halo)
    // so a point just off-screen still contributes its ring rather than popping.
    const float r = pointRadius();
    const float unit = unitsToPixels();
    const float bleed = (unit > 0.0f) ? ((r * 4.0f + 6.0f) / unit) : 0.0f;

    const auto tl = mapToCoordsSpace(0.0f, 0.0f);
    const auto br = mapToCoordsSpace(static_cast<float>(getWidth()), static_cast<float>(getHeight()));
    const float vMinX = std::min(tl.x, br.x) - bleed;
    const float vMaxX = std::max(tl.x, br.x) + bleed;
    const float vMinY = std::min(tl.y, br.y) - bleed;
    const float vMaxY = std::max(tl.y, br.y) + bleed;

    spatialIndex.queryRange(juce::Rectangle<float>(vMinX, vMinY, vMaxX - vMinX, vMaxY - vMinY), queryScratch);

    // ---- bucket by visual state -------------------------------------------
    // One pass, into buffers that are only ever cleared, so a steady-state
    // rebuild performs no heap allocation once the buffers have grown.
    //
    // The selected and hovered points are deliberately left IN the resting
    // buckets: their overlay is drawn opaque and larger, so it covers the
    // resting mark completely, and keeping them here means changing the
    // selection or moving the pointer never invalidates this layer.
    const bool hasSimilar = !similarPaths.empty();

    for (int i : queryScratch) {
        const auto& pt = samples[static_cast<size_t>(i)];
        if (!pt.isProcessed) continue;

        const auto filterText = ClassificationPresentation::filterText(
            pt.category, pt.subcategory, pt.instrumentType, pt.tagSource);
        if (!isCategoryActive(filterText) || !matchesSearchQuery(pt)) {
            bucketMuted.push_back(i);
            continue;
        }

        visibleForDensity.push_back(i);

        if (hasSimilar && similarEmphasisFor(i) > 0.0f) bucketSimilar.push_back(i);
        else                                            bucketResting.push_back(i);
    }

    paintDensityField(ig, visibleForDensity);

    // ---- filtered-out points ------------------------------------------------
    // They recede instead of vanishing: a filter should narrow attention, not
    // destroy the spatial context that makes the map worth looking at.
    if (!bucketMuted.empty()) {
        const float mr = std::max(1.1f, r * 0.55f);
        ig.setColour(Tokens::mapMuted);
        for (int i : bucketMuted) {
            const auto p = mapToPixelSpace(samples[static_cast<size_t>(i)].x, samples[static_cast<size_t>(i)].y);
            ig.fillEllipse(p.x - mr, p.y - mr, mr * 2.0f, mr * 2.0f);
        }
    }

    // ---- resting + similar points -------------------------------------------
    // Each point is: a "seat" of near-background punched under it (so that two
    // adjacent points in a dense cluster still read as two points rather than a
    // smear), the category fill, and -- only once the point is big enough to
    // carry one -- a single-pixel edge in the saturated category colour. No
    // glow, no gradient, no orb.
    //
    // Drawn seats-first, then cores grouped by category, rather than
    // colour/shape/colour/shape per point: setColour measured at roughly 1us,
    // which at two calls per point was ~10ms per frame on its own at 5,000
    // points. Grouping reduces it to one call per category.
    const float seat = 0.9f;
    const bool  drawEdges = r >= 2.9f;
    const float sr = r + seat;

    if (!bucketResting.empty() || !bucketSimilar.empty()) {
        ig.setColour(Tokens::mapPointSeat);
        for (int i : bucketResting) {
            const auto p = mapToPixelSpace(samples[static_cast<size_t>(i)].x, samples[static_cast<size_t>(i)].y);
            ig.fillEllipse(p.x - sr, p.y - sr, sr * 2.0f, sr * 2.0f);
        }
        for (int i : bucketSimilar) {
            const auto p = mapToPixelSpace(samples[static_cast<size_t>(i)].x, samples[static_cast<size_t>(i)].y);
            ig.fillEllipse(p.x - sr, p.y - sr, sr * 2.0f, sr * 2.0f);
        }
    }

    // Group resting points by category style, then emit one colour change per
    // group. `pointsByStyle` keeps its vectors across frames; the linear search
    // is over the handful of distinct categories actually on screen.
    for (int i : bucketResting) {
        const auto* style = &styleForIndex(i);
        auto it = std::find_if(pointsByStyle.begin(), pointsByStyle.end(),
                               [style](const auto& e) { return e.first == style; });
        if (it == pointsByStyle.end()) {
            pointsByStyle.emplace_back(style, std::vector<int>{});
            it = std::prev(pointsByStyle.end());
            it->second.reserve(64);
        }
        it->second.push_back(i);
    }

    // When a filter is narrowing the set, the surviving points step up to their
    // full category colour. At rest the map is a quiet field; the moment the
    // user asks a question of it, the answer resolves.
    const bool filterActive = !searchQueryLower.isEmpty() || !bucketMuted.empty();

    for (const auto& group : pointsByStyle) {
        if (group.second.empty()) continue;

        ig.setColour(filterActive ? group.first->active : group.first->resting);
        for (int i : group.second) {
            const auto p = mapToPixelSpace(samples[static_cast<size_t>(i)].x, samples[static_cast<size_t>(i)].y);
            ig.fillEllipse(p.x - r, p.y - r, r * 2.0f, r * 2.0f);
        }

        if (drawEdges) {
            ig.setColour(group.first->active.withMultipliedAlpha(0.42f));
            for (int i : group.second) {
                const auto p = mapToPixelSpace(samples[static_cast<size_t>(i)].x, samples[static_cast<size_t>(i)].y);
                ig.drawEllipse(p.x - r + 0.5f, p.y - r + 0.5f, (r - 0.5f) * 2.0f, (r - 0.5f) * 2.0f, 1.0f);
            }
        }
    }

    // ---- similarity emphasis -------------------------------------------------
    // Find Similar / Reference Search: the result neighbourhood lights up in the
    // discovery blue, ranked by how similar the engine actually said it was. No
    // connection lines, no invented positions, no network graph. Small enough a
    // set that per-point colour changes are not worth grouping.
    for (int i : bucketSimilar) {
        const auto& pt = samples[static_cast<size_t>(i)];
        const auto& style = styleForIndex(i);
        const float e = similarEmphasisFor(i);
        const auto p = mapToPixelSpace(pt.x, pt.y);

        ig.setColour(style.active);
        ig.fillEllipse(p.x - r, p.y - r, r * 2.0f, r * 2.0f);

        ig.setColour(Tokens::mapSimilar.withMultipliedAlpha(e));
        const float rr = r + 2.4f;
        ig.drawEllipse(p.x - rr, p.y - rr, rr * 2.0f, rr * 2.0f, 1.0f + 0.4f * e);
    }
}

void SampleCanvas::paint(juce::Graphics& g)
{
    const auto bounds = getLocalBounds();
    if (bounds.isEmpty()) return;

    if (needsFit && !samples.empty()) fitToContent(hasFittedOnce);
    if (similarDirty) { rebuildSimilarRanks(); invalidateStaticLayer(); }

    // Rasterise the cached layer at device resolution so points, the lattice
    // and point edges land on real pixels instead of being upscaled from
    // logical size -- the difference between crisp and fuzzy on a Retina panel.
    float scale = g.getInternalContext().getPhysicalPixelScaleFactor();
    if (!std::isfinite(scale) || scale <= 0.0f) scale = 1.0f;

    const int pw = juce::jmax(1, juce::roundToInt(static_cast<float>(getWidth())  * scale));
    const int ph = juce::jmax(1, juce::roundToInt(static_cast<float>(getHeight()) * scale));

    if (!staticLayer.isValid() || staticLayer.getWidth() != pw || staticLayer.getHeight() != ph) {
        // NativeImageType, not the default software image: on macOS this is a
        // CoreGraphics-backed surface, so both drawing into the layer and
        // blitting it back out take the accelerated path.
        staticLayer = juce::Image(juce::NativeImageType().create(juce::Image::RGB, pw, ph, false));
        staticLayerScale = scale;
        staticLayerDirty = true;
    } else if (std::abs(scale - staticLayerScale) > 1.0e-3f) {
        staticLayerScale = scale;
        staticLayerDirty = true;
    }

    if (staticLayerDirty) rebuildStaticLayer(scale);

    g.drawImageTransformed(staticLayer, juce::AffineTransform::scale(1.0f / scale), false);

    // A quiet outer ring makes keyboard focus legible without competing with
    // selected points or the map's category colours. It is drawn after the
    // cached layer so it remains visible in empty, filtered, and populated
    // states alike.
    if (hasKeyboardFocus(true))
    {
        g.setColour(Tokens::focusRing.withAlpha(0.72f));
        g.drawRoundedRectangle(bounds.toFloat().reduced(1.0f), Tokens::cornerRadiusSm, 1.5f);
    }

    if (samples.empty())
    {
        const auto cardArea = bounds.reduced(24);
        const int cardWidth = juce::jmin(460, juce::jmax(240, cardArea.getWidth() - 16));
        const int cardHeight = juce::jmin(166, juce::jmax(138, cardArea.getHeight() - 24));
        const auto card = cardArea.withSizeKeepingCentre(cardWidth, cardHeight);

        g.setColour(Tokens::surface);
        g.fillRoundedRectangle(card.toFloat(), Tokens::cornerRadiusLg);
        g.setColour(Tokens::border);
        g.drawRoundedRectangle(card.toFloat().reduced(0.5f), Tokens::cornerRadiusLg, 1.0f);

        const auto centre = card.getCentre();
        g.setColour(Tokens::accentInteractive.withAlpha(0.8f));
        g.drawEllipse(static_cast<float>(centre.x - 16), static_cast<float>(centre.y - 44), 32.0f, 32.0f, 2.0f);
        g.drawLine(static_cast<float>(centre.x - 7), static_cast<float>(centre.y - 28),
                   static_cast<float>(centre.x + 7), static_cast<float>(centre.y - 28), 2.0f);

        g.setColour(Tokens::foreground);
        g.setFont(juce::Font(juce::FontOptions().withHeight(12.0f).withStyle("Bold")));
        g.drawFittedText("SAMPLE MAP READY", card.withTrimmedTop(54).withHeight(22),
                         juce::Justification::centred, 1);
        g.setColour(Tokens::muted);
        g.setFont(juce::Font(juce::FontOptions().withHeight(11.0f)));
        g.drawFittedText("Scan a folder or drop audio here to build your sound map.",
                         card.withTrimmedTop(80).withTrimmedBottom(48),
                         juce::Justification::centred, 2);

        emptyActionBounds = card.withSizeKeepingCentre(132, 24);
        emptyActionBounds.setY(card.getBottom() - emptyActionBounds.getHeight() - 12);
        g.setColour(emptyActionHovered ? Tokens::surfaceHover : Tokens::surfaceRaised);
        g.fillRoundedRectangle(emptyActionBounds.toFloat(), Tokens::cornerRadiusSm);
        g.setColour(emptyActionHovered ? Tokens::foreground : Tokens::accentInteractive);
        g.drawRoundedRectangle(emptyActionBounds.toFloat().reduced(0.5f), Tokens::cornerRadiusSm, 1.0f);
        g.setColour(Tokens::foreground);
        g.setFont(juce::Font(juce::FontOptions().withHeight(10.0f).withStyle("Bold")));
        g.drawFittedText("SCAN LIBRARY", emptyActionBounds, juce::Justification::centred, 1);
        return;
    }

    emptyActionBounds = {};
    emptyActionHovered = false;

    if (!spatialIndex.isBuilt())
        return;

    const float r = pointRadius();
    const bool hoverActive = hoverVisualIdx >= 0 && hoverAmount > 2.0e-3f
                               && hoverVisualIdx < static_cast<int>(samples.size());

    // ---- overlay: hovered point --------------------------------------------
    if (hoverActive && hoverVisualIdx != selectedIdx) {
        const auto& pt = samples[static_cast<size_t>(hoverVisualIdx)];
        const auto& style = styleForIndex(hoverVisualIdx);
        const auto p = mapToPixelSpace(pt.x, pt.y);
        const float hr = r * (1.0f + 0.42f * hoverAmount);

        g.setColour(Tokens::mapPointSeat);
        g.fillEllipse(p.x - hr - 0.9f, p.y - hr - 0.9f, (hr + 0.9f) * 2.0f, (hr + 0.9f) * 2.0f);
        g.setColour(style.active);
        g.fillEllipse(p.x - hr, p.y - hr, hr * 2.0f, hr * 2.0f);

        g.setColour(Tokens::foreground.withAlpha(0.80f * hoverAmount));
        const float ring = hr + 2.6f;
        g.drawEllipse(p.x - ring, p.y - ring, ring * 2.0f, ring * 2.0f, 1.2f);
    }

    // ---- overlay: selection -------------------------------------------------
    // Three redundant channels so this never depends on hue alone: the largest
    // geometry, the highest luminance on the canvas (a near-white core), and a
    // detached discovery-blue ring no other state uses.
    labelRects.clear();
    if (hoverActive) {
        juce::String tipName, tipMeta;
        labelRects.push_back(tooltipBoundsFor(hoverVisualIdx, tipName, tipMeta).toFloat());
    }

    if (selectedIdx >= 0 && selectedIdx < static_cast<int>(samples.size())) {
        const auto& pt = samples[static_cast<size_t>(selectedIdx)];
        const auto p = mapToPixelSpace(pt.x, pt.y);
        const float a = selectionAmount;
        const float selR = r * (1.0f + 0.30f * a);

        const float halo = selR * 3.1f;
        g.setColour(Tokens::mapSelectedHalo.withMultipliedAlpha(a));
        g.fillEllipse(p.x - halo, p.y - halo, halo * 2.0f, halo * 2.0f);

        const float gapR = selR * 1.45f + 1.0f;
        g.setColour(Tokens::mapPointSeat);
        g.fillEllipse(p.x - gapR, p.y - gapR, gapR * 2.0f, gapR * 2.0f);

        const float ring = selR * 1.95f + 0.8f;
        g.setColour(Tokens::mapSelected.withMultipliedAlpha(a));
        g.drawEllipse(p.x - ring, p.y - ring, ring * 2.0f, ring * 2.0f, 1.8f);

        g.setColour(Tokens::foreground.withMultipliedAlpha(0.35f + 0.65f * a));
        g.fillEllipse(p.x - selR, p.y - selR, selR * 2.0f, selR * 2.0f);

        // Name the selection in place when the tooltip isn't already doing it --
        // this is the visual thread between the map and the Inspector.
        if (!(hoverActive && hoverVisualIdx == selectedIdx))
            paintPointLabel(g, selectedIdx, p, ring, Tokens::foreground, a, labelRects);
    }

    // Keep filtered-out points as quiet spatial context, but explain the
    // zero-result state explicitly. Without this cue an all-off category set
    // or a typo in Search looks like a broken/empty map even though the library
    // is still present underneath the filter.
    bool hasMatchingSamples = !visibleForDensity.empty();
    const bool hasActiveViewFilter = categoryFilterActive || searchQueryLower.isNotEmpty();
    if (!hasMatchingSamples && hasActiveViewFilter)
    {
        // `visibleForDensity` is intentionally viewport-culled for large
        // libraries. Only when it is empty do we pay for this short-circuiting
        // global check, preventing a pan away from matching points from being
        // misreported as a library-wide zero-result state.
        for (const auto& sample : samples)
        {
            if (!sample.isProcessed) continue;
            const auto filterText = ClassificationPresentation::filterText(
                sample.category, sample.subcategory, sample.instrumentType, sample.tagSource);
            if (isCategoryActive(filterText) && matchesSearchQuery(sample))
            {
                hasMatchingSamples = true;
                break;
            }
        }
    }

    if (!hasMatchingSamples && hasActiveViewFilter)
    {
        const int cardWidth = juce::jmin(300, juce::jmax(220, bounds.getWidth() - 32));
        const int cardHeight = 62;
        auto card = bounds.withSizeKeepingCentre(cardWidth, cardHeight);
        card.setY(bounds.getY() + 18);

        g.setColour(Tokens::surface.withAlpha(0.96f));
        g.fillRoundedRectangle(card.toFloat(), Tokens::cornerRadius);
        g.setColour(Tokens::borderStrong);
        g.drawRoundedRectangle(card.toFloat().reduced(0.5f), Tokens::cornerRadius, 1.0f);

        g.setColour(Tokens::foreground);
        g.setFont(juce::Font(juce::FontOptions().withHeight(11.0f).withStyle("Bold")));
        g.drawFittedText("NO MATCHING SAMPLES", card.withTrimmedTop(8).withHeight(18),
                         juce::Justification::centred, 1);
        g.setColour(Tokens::muted);
        g.setFont(juce::Font(juce::FontOptions().withHeight(10.0f)));
        g.drawFittedText("Clear search or category filters", card.withTrimmedTop(30).withHeight(18),
                         juce::Justification::centred, 1);
    }

    // ---- overlay: semantic zoom labels --------------------------------------
    // Only once the user has zoomed in far enough that the viewport holds a
    // readable handful of points. Never hundreds of filenames at once.
    const int visibleCount = static_cast<int>(visibleForDensity.size());
    if (zoomScale >= kLabelZoom && visibleCount <= kLabelMaxPoints) {
        const float labelFade = juce::jlimit(0.0f, 1.0f, (zoomScale - kLabelZoom) / 1.2f) * 0.85f;
        for (int i : bucketResting)
            paintPointLabel(g, i, mapToPixelSpace(samples[static_cast<size_t>(i)].x, samples[static_cast<size_t>(i)].y),
                            r, Tokens::muted, labelFade, labelRects);
        for (int i : bucketSimilar)
            paintPointLabel(g, i, mapToPixelSpace(samples[static_cast<size_t>(i)].x, samples[static_cast<size_t>(i)].y),
                            r, Tokens::mapSelected, labelFade, labelRects);
    }

    // ---- overlay: tooltip ----------------------------------------------------
    if (hoverVisualIdx >= 0 && hoverVisualIdx < static_cast<int>(samples.size()))
        paintTooltip(g, hoverVisualIdx, smoothIn(hoverAmount));
}

// ---------------------------------------------------------------------------
// Interaction
// ---------------------------------------------------------------------------

void SampleCanvas::mouseDown(const juce::MouseEvent& event)
{
    if (samples.empty() && emptyActionBounds.contains(event.position.toInt()))
    {
        grabKeyboardFocus();
        if (onEmptyStateAction)
            onEmptyStateAction();
        return;
    }

    mouseIsDown = true;
    pressOrigin = event.position.toInt();
    dragStartPos = pressOrigin;
    isPanning = false;

    const int idx = findDotAtPosition(event.position);
    pressHitAPoint = idx >= 0;

    if (idx >= 0) {
        if (idx != selectedIdx) {
            selectedIdx = idx;
            selectionAmount = 0.0f;   // animate the new selection in
            beginAnimation();
        }
        selectedFilePath = samples[static_cast<size_t>(selectedIdx)].filePath;
        repaint();

        if (onSelect) onSelect(samples[static_cast<size_t>(selectedIdx)]);

        if (event.getNumberOfClicks() == 2 && onDoubleClick)
            onDoubleClick(samples[static_cast<size_t>(selectedIdx)]);
    } else {
        // Double-clicking empty canvas reframes the whole library. The map is a
        // workspace you can get lost in; this is the way back.
        if (event.getNumberOfClicks() == 2) {
            fitToContent(true);
        } else {
            setMouseCursor(juce::MouseCursor::DraggingHandCursor);
        }
    }
}

void SampleCanvas::mouseUp(const juce::MouseEvent& event)
{
    juce::ignoreUnused(event);
    mouseIsDown = false;
    isPanning = false;
    pressHitAPoint = false;
    setMouseCursor(hoveredIdx >= 0 ? juce::MouseCursor::PointingHandCursor
                                   : juce::MouseCursor::NormalCursor);
}

void SampleCanvas::mouseDrag(const juce::MouseEvent& event)
{
    if (!mouseIsDown) return;

    const auto p = event.position.toInt();

    // A few pixels of slack before a press becomes a pan, so a click with a
    // shaky hand selects cleanly instead of nudging the whole map.
    if (!isPanning && !pressHitAPoint && p.getDistanceFrom(pressOrigin) > 4) {
        isPanning = true;
        userHasNavigated = true;
    needsFit = false;   // a deliberate gesture always wins over a pending auto-fit
        setMouseCursor(juce::MouseCursor::DraggingHandCursor);
    }

    if (isPanning) {
        const auto delta = p - dragStartPos;
        // Pan is 1:1 and un-eased -- easing a direct manipulation would read as
        // lag, not polish.
        targetXOffset += static_cast<float>(delta.getX());
        targetYOffset += static_cast<float>(delta.getY());
        clampOffsets();
        xOffset = targetXOffset;
        yOffset = targetYOffset;
        dragStartPos = p;
        invalidateStaticLayer();
        repaint();
    } else if (pressHitAPoint && selectedIdx >= 0) {
        // Drag file OUT of plugin window to external DAW/Finder if mouse dragged far enough
        if (p.getDistanceFrom(pressOrigin) > 8) {
            // Missing-file guard (SLO_ABLETON_WORKFLOW_VALIDATION_V1.md) --
            // matches PrecisionBrowser.cpp's equivalent drag path, which
            // already had this check. Not a safety issue either way (a
            // missing file just fails the OS-level drag silently), but
            // without it a stale canvas entry drags nothing with no
            // feedback, where the browser view already fails visibly.
            const auto file = juce::File(samples[static_cast<size_t>(selectedIdx)].filePath);
            if (file.existsAsFile()) {
                juce::StringArray files;
                files.add(file.getFullPathName());

                if (auto* container = juce::DragAndDropContainer::findParentDragContainerFor(this)) {
                    container->performExternalDragDropOfFiles(files, false, this, [](){});
                }
            }
        }
    }
}

void SampleCanvas::mouseMove(const juce::MouseEvent& event)
{
    if (samples.empty())
    {
        const bool wasHovered = emptyActionHovered;
        emptyActionHovered = emptyActionBounds.contains(event.position.toInt());
        setMouseCursor(emptyActionHovered ? juce::MouseCursor::PointingHandCursor
                                           : juce::MouseCursor::NormalCursor);
        if (emptyActionHovered != wasHovered)
            repaint();
        return;
    }

    const int prevHover = hoveredIdx;
    hoveredIdx = findDotAtPosition(event.position);

    if (hoveredIdx == prevHover) return;

    if (hoveredIdx >= 0) {
        // Moving between two adjacent points re-runs the transition from a
        // partial value rather than snapping back to zero, so sweeping across a
        // cluster feels continuous instead of strobing.
        if (hoverVisualIdx != hoveredIdx) hoverAmount = juce::jmin(hoverAmount, 0.30f);
        hoverVisualIdx = hoveredIdx;
        setMouseCursor(juce::MouseCursor::PointingHandCursor);
    } else if (!isPanning) {
        setMouseCursor(juce::MouseCursor::NormalCursor);
    }

    beginAnimation();
    repaint();
}

void SampleCanvas::mouseExit(const juce::MouseEvent& event)
{
    juce::ignoreUnused(event);
    if (emptyActionHovered)
    {
        emptyActionHovered = false;
        repaint();
    }
    if (hoveredIdx < 0) return;
    hoveredIdx = -1;
    setMouseCursor(juce::MouseCursor::NormalCursor);
    beginAnimation();
    repaint();
}

void SampleCanvas::mouseWheelMove(const juce::MouseEvent& event, const juce::MouseWheelDetails& wheel)
{
    float delta = wheel.deltaY;
    if (wheel.isReversed) delta = -delta;
    if (std::abs(delta) < 1.0e-4f) return;

    // Multiplicative so each notch feels the same at every zoom level, and eased
    // so a fast trackpad flick glides to rest instead of stepping.
    applyZoom(std::exp(delta * 1.25f), event.position, false);
}

void SampleCanvas::mouseMagnify(const juce::MouseEvent& event, float scaleFactor)
{
    // Pinch is already a continuous gesture; easing it would only add lag.
    if (scaleFactor > 0.0f)
        applyZoom(scaleFactor, event.position, true);
}

int SampleCanvas::findDotAtPosition(juce::Point<float> pos) const
{
    // Hit radius tracks the drawn radius so that points stay easy to grab when
    // zoomed out (where they are small) without becoming sloppy when zoomed in.
    const float threshold = juce::jlimit(7.0f, 14.0f, pointRadius() * 2.6f);

    const auto coordPos = mapToCoordsSpace(pos.x, pos.y);
    const float unit = unitsToPixels();
    if (unit <= 0.0f) return -1;
    const float coordThreshold = threshold / unit;

    juce::Rectangle<float> range(coordPos.x - coordThreshold, coordPos.y - coordThreshold,
                                 coordThreshold * 2.0f, coordThreshold * 2.0f);
    spatialIndex.queryRange(range, hitScratch);

    int closestIdx = -1;
    float closestDist = threshold;

    for (int i : hitScratch) {
        const auto& pt = samples[static_cast<size_t>(i)];
        if (!pt.isProcessed) continue;
        const auto filterText = ClassificationPresentation::filterText(
            pt.category, pt.subcategory, pt.instrumentType, pt.tagSource);
        if (!isCategoryActive(filterText)) continue;
        if (!matchesSearchQuery(pt)) continue;

        const float dist = pos.getDistanceFrom(mapToPixelSpace(pt.x, pt.y));
        if (dist < closestDist) {
            closestDist = dist;
            closestIdx = i;
        }
    }

    return closestIdx;
}

// ---------------------------------------------------------------------------
// Category colour
// ---------------------------------------------------------------------------

const SampleCanvas::CategoryStyle& SampleCanvas::styleFor(const std::string& type) const
{
    auto cached = categoryStyles.find(type);
    if (cached != categoryStyles.end())
        return cached->second;

    std::string lowerType = type;
    std::transform(lowerType.begin(), lowerType.end(), lowerType.begin(),
                   [](unsigned char c) { return static_cast<char>(std::tolower(c)); });

    // Categories provide secondary discovery context. State (selection, hover,
    // similarity) is drawn with its own tokens, so category colour never has to
    // carry state -- which is what lets it stay this restrained.
    auto pick = [&lowerType](const char* needle) {
        return lowerType.find(needle) != std::string::npos;
    };

    juce::Colour active;
    bool matched = true;

    if      (pick("unknown") || pick("needs review")) active = Tokens::mapCategorySlate;
    else if (pick("kick"))                        active = Tokens::mapCategoryCool;
    else if (pick("snare"))                       active = Tokens::mapCategoryRose;
    else if (pick("hihat") || pick("hat"))        active = Tokens::mapCategoryGold;
    else if (pick("clap"))                        active = Tokens::mapCategoryWarm;
    else if (pick("perc"))                        active = Tokens::mapCategoryGreen;
    else if (pick("bass"))                        active = Tokens::mapCategoryViolet;
    else if (pick("synth"))                       active = Tokens::mapCategoryTeal;
    else if (pick("loop"))                        active = Tokens::mapCategoryRose;
    else if (pick("vocal") || pick("voc"))        active = Tokens::mapCategoryGold;
    // Video-game oriented categories
    else if (pick("laser"))                       active = Tokens::mapCategoryRose;
    else if (pick("explosion") || pick("blast"))  active = Tokens::mapCategoryWarm;
    else if (pick("powerup"))                     active = Tokens::mapCategoryViolet;
    else if (pick("jump"))                        active = Tokens::mapCategoryGreen;
    else if (pick("coin"))                        active = Tokens::mapCategoryGold;
    else if (pick("ui"))                          active = Tokens::mapCategoryCool;
    else if (pick("footstep") || pick("step"))    active = Tokens::mapCategorySlate;
    else if (pick("impact") || pick("hit"))       active = Tokens::mapCategoryWarm;
    else                                          matched = false;

    if (!matched) {
        // Unknown categories used to fall through to Colour::fromHSV(hash, 0.8, 0.9)
        // -- a fully saturated arbitrary hue. On a real library, where plenty of
        // instrumentType strings miss the list above, that single line was the
        // main source of the confetti look. The fallback now draws from the same
        // curated, luminance-matched palette, so an unrecognised category is
        // still distinguishable but can never be the loudest thing on the map.
        static const juce::Colour palette[] = {
            Tokens::mapCategoryCool,  Tokens::mapCategoryWarm,
            Tokens::mapCategoryGold,  Tokens::mapCategoryRose,
            Tokens::mapCategoryViolet, Tokens::mapCategoryGreen,
            Tokens::mapCategoryTeal,  Tokens::mapCategorySlate
        };
        uint32_t hash = 2166136261u;
        for (char c : lowerType) { hash ^= static_cast<uint32_t>(static_cast<unsigned char>(c)); hash *= 16777619u; }
        active = palette[hash % (sizeof(palette) / sizeof(palette[0]))];
    }

    // Resting points are desaturated and slightly dimmed; category identity
    // resolves on hover, selection and filtering. That is what keeps a thousand
    // points reading as one field of sounds rather than a bag of sweets.
    CategoryStyle style;
    style.active  = active;
    style.resting = active.withMultipliedSaturation(0.58f).withMultipliedBrightness(0.80f);

    return categoryStyles.emplace(type, style).first->second;
}

const SampleCanvas::CategoryStyle& SampleCanvas::styleForIndex(int index) const
{
    if (stylePerSample.size() < samples.size())
        stylePerSample.resize(samples.size(), nullptr);

    const auto*& cached = stylePerSample[static_cast<size_t>(index)];
    if (cached == nullptr) {
        const auto& sample = samples[static_cast<size_t>(index)];
        const auto label = ClassificationPresentation::primaryLabel(
            sample.category, sample.subcategory, sample.instrumentType, sample.tagSource);
        cached = &styleFor(label.empty() ? std::string("Unknown") : label);
    }
    return *cached;
}

juce::Colour SampleCanvas::getColourForInstrumentType(const std::string& type) const
{
    return styleFor(type).active;
}

bool SampleCanvas::isCategoryActive(const std::string& type) const
{
    if (!categoryFilterActive) return true;
    if (filteredCategories.empty()) return false;

    for (const auto& activeCat : filteredCategories)
        if (ClassificationPresentation::matchesCategoryFilter(type, activeCat))
            return true;

    return false;
}

bool SampleCanvas::matchesSearchQuery(const SampleItem& item) const
{
    if (searchQueryLower.isEmpty()) return true;

    juce::String searchable = juce::String(item.name) + " " + item.key + " "
        + item.instrumentType + " " + juce::String(item.bpm, 0) + " "
        + item.category + " " + item.subcategory + " "
        + juce::String(item.audioFeatures.physics.physicalClass) + " "
        + juce::String(item.audioFeatures.physics.physicalBadge);
    for (const auto& tag : item.secondaryTags)
        searchable += " " + juce::String(tag);

    return SloSearchLexicon::matches(searchable, searchQueryLower);
}
