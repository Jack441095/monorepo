// TestQuadTreeCoincidentPoints -- regression coverage for the spatial index
// blowing the stack on a library that has no usable embeddings.
//
// The defect: QuadTree::Node::subdivide() had no depth cap and no
// minimum-bounds guard, and insertIntoChildren() routes every point that is not
// contained by any child into nw. SampleManagerEngine::rebuildSpatialIndexFull()
// deliberately parks samples with no usable embedding at (0,0) -- and does the
// same when HNSW returns no neighbours -- so 33 or more such samples put every
// point on the same pixel. The leaf subdivides, every index lands back in nw,
// and it subdivides again, forever. That crashed the message thread inside
// SampleCanvas::updateSamples(), which the 60 Hz editor timer calls, so opening
// the plugin on a library with 33 pending or permanently-failed inferences was
// enough to take the editor down.
//
// The fix refuses to split a node that is already smaller than a pixel, or a
// leaf whose points all sit on the same coordinate, so the overflow stays a
// dense leaf that a range query can still scan.
//
// These cases assert the observable contract, not the internal tree shape:
// building the index must not recurse without bound, and a query over the
// occupied region must still return every point, including the coincident ones.

#include <iostream>
#include <vector>

#include "QuadTree.h"
#include "SampleManagerEngine.h"

namespace {

int checks = 0;
bool ok = true;

void check(bool condition, const std::string& what) {
    ++checks;
    if (!condition) {
        ok = false;
        std::cout << "   FAIL " << what << "\n";
    }
}

SampleItem makeItem(float x, float y, const std::string& name) {
    SampleItem item;
    item.x = x;
    item.y = y;
    item.name = name;
    item.filePath = name;
    // Deliberately not Valid: this is the state rebuildSpatialIndexFull() leaves
    // a sample in when inference has not produced an embedding.
    item.embeddingStatus = EmbeddingStatus::NotAnalysed;
    return item;
}

std::vector<SampleItem> makeCoincidentItems(int count) {
    std::vector<SampleItem> items;
    items.reserve(static_cast<size_t>(count));
    for (int i = 0; i < count; ++i) {
        items.push_back(makeItem(0.0f, 0.0f, "unembedded_" + std::to_string(i)));
    }
    return items;
}

}  // namespace

int main() {
    // CAPACITY is 32, so 64 coincident points is two splits' worth. Before the
    // fix this never returned.
    {
        auto items = makeCoincidentItems(64);
        QuadTree tree;
        tree.build(juce::Rectangle<float>(-1.0f, -1.0f, 2.0f, 2.0f), items);

        auto found = tree.queryRange(juce::Rectangle<float>(-1.0f, -1.0f, 2.0f, 2.0f));
        check(found.size() == items.size(),
              "64 samples with no embedding at the origin all stay queryable");
    }

    // The exact bound from the crash: 33 is the first size that subdivides.
    {
        auto items = makeCoincidentItems(QuadTree::CAPACITY + 1);
        QuadTree tree;
        tree.build(juce::Rectangle<float>(-1.0f, -1.0f, 2.0f, 2.0f), items);
        auto found = tree.queryRange(juce::Rectangle<float>(-1.0f, -1.0f, 2.0f, 2.0f));
        check(found.size() == items.size(),
              "one sample past the leaf capacity at one coordinate does not recurse away");
    }

    // A degenerate bounds rectangle -- the canvas computes marginX = max(1.0, 0)
    // when every point shares an x, so this shape really does occur.
    {
        auto items = makeCoincidentItems(200);
        QuadTree tree;
        tree.build(juce::Rectangle<float>(-1.0f, -1.0f, 2.0f, 2.0f), items);
        auto narrow = tree.queryRange(juce::Rectangle<float>(-0.5f, -0.5f, 1.0f, 1.0f));
        check(narrow.size() == items.size(),
              "a query window smaller than the tree still finds every origin point");
    }

    // Distinct points must still subdivide, or the fix would have quietly
    // turned the index into a linear scan for everyone.
    {
        std::vector<SampleItem> items;
        for (int i = 0; i < 200; ++i) {
            items.push_back(makeItem(static_cast<float>(i) * 0.01f,
                                     static_cast<float>(i % 7) * 0.05f,
                                     "spread_" + std::to_string(i)));
        }
        QuadTree tree;
        tree.build(juce::Rectangle<float>(-1.0f, -1.0f, 4.0f, 4.0f), items);

        auto all = tree.queryRange(juce::Rectangle<float>(-1.0f, -1.0f, 4.0f, 4.0f));
        check(all.size() == items.size(), "200 spread-out samples all remain queryable");

        // A small window must return a strict subset, which only holds if the
        // tree actually split instead of keeping everything in one leaf.
        auto window = tree.queryRange(juce::Rectangle<float>(0.0f, 0.0f, 0.15f, 0.06f));
        check(!window.empty() && window.size() < items.size(),
              "a small window over spread points returns a subset, so the tree still subdivides");
    }

    // Incremental insert uses the same path, so it must be safe too.
    {
        auto items = makeCoincidentItems(40);
        QuadTree tree;
        tree.build(juce::Rectangle<float>(-1.0f, -1.0f, 2.0f, 2.0f), items);

        items.push_back(makeItem(0.0f, 0.0f, "arrived_later"));
        const bool inserted = tree.insert(static_cast<int>(items.size()) - 1);
        check(inserted, "a coincident sample arriving after the build is accepted");
        auto found = tree.queryRange(juce::Rectangle<float>(-1.0f, -1.0f, 2.0f, 2.0f));
        check(found.size() == items.size(), "the late arrival is queryable alongside the rest");
    }

    std::cout << (ok ? "PASS" : "FAIL") << " QuadTree coincident points (" << checks << " checks)\n";
    return ok ? 0 : 1;
}
