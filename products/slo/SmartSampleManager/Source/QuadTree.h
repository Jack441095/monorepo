#pragma once

#include <JuceHeader.h>
#include <vector>
#include <memory>
#include "SampleManagerEngine.h"

// Stores indices into an externally-owned SampleItem vector rather than raw
// SampleItem* pointers. This keeps the tree valid even when the owning vector
// is reassigned/reallocated (as SampleCanvas::updateSamples does on every poll) —
// only the *vector object's* address needs to stay stable (it does, as a member),
// not the addresses of individual elements inside it.
class QuadTree {
public:
    static constexpr int CAPACITY = 32;

    struct Node {
        juce::Rectangle<float> bounds;
        std::vector<int> indices;
        std::unique_ptr<Node> nw, ne, sw, se;
        bool isLeaf = true;
        const std::vector<SampleItem>* items = nullptr;

        Node(const juce::Rectangle<float>& b, const std::vector<SampleItem>* itemsPtr)
            : bounds(b), items(itemsPtr) {}

        void subdivide() {
            float x = bounds.getX();
            float y = bounds.getY();
            float w = bounds.getWidth() * 0.5f;
            float h = bounds.getHeight() * 0.5f;

            nw = std::make_unique<Node>(juce::Rectangle<float>(x, y, w, h), items);
            ne = std::make_unique<Node>(juce::Rectangle<float>(x + w, y, w, h), items);
            sw = std::make_unique<Node>(juce::Rectangle<float>(x, y + h, w, h), items);
            se = std::make_unique<Node>(juce::Rectangle<float>(x + w, y + h, w, h), items);
            isLeaf = false;

            // Move indices to children
            for (int idx : indices) {
                insertIntoChildren(idx);
            }
            indices.clear();
        }

        bool insertIntoChildren(int idx) {
            float px = (*items)[idx].x;
            float py = (*items)[idx].y;

            if (nw->bounds.contains(px, py)) return nw->insert(idx);
            if (ne->bounds.contains(px, py)) return ne->insert(idx);
            if (sw->bounds.contains(px, py)) return sw->insert(idx);
            if (se->bounds.contains(px, py)) return se->insert(idx);

            // Fallback for border cases
            return nw->insert(idx);
        }

        bool insert(int idx) {
            float px = (*items)[idx].x;
            float py = (*items)[idx].y;

            if (!bounds.contains(px, py)) {
                return false;
            }

            if (isLeaf) {
                indices.push_back(idx);
                if (indices.size() > static_cast<size_t>(CAPACITY)) {
                    subdivide();
                }
                return true;
            }

            return insertIntoChildren(idx);
        }

        void query(const juce::Rectangle<float>& range, std::vector<int>& results) const {
            if (!bounds.intersects(range)) {
                return;
            }

            if (isLeaf) {
                for (int idx : indices) {
                    const auto& it = (*items)[idx];
                    if (range.contains(it.x, it.y)) {
                        results.push_back(idx);
                    }
                }
                return;
            }

            nw->query(range, results);
            ne->query(range, results);
            sw->query(range, results);
            se->query(range, results);
        }
    };

    QuadTree() = default;

    void build(const juce::Rectangle<float>& boundary, const std::vector<SampleItem>& items) {
        itemsPtr = &items;
        root = std::make_unique<Node>(boundary, itemsPtr);
        for (int i = 0; i < static_cast<int>(items.size()); ++i) {
            root->insert(i);
        }
    }

    // Incrementally insert a single point (by index into the same items vector
    // that was passed to build()). Returns false if the point falls outside the
    // tree's current bounds — the caller should then fall back to a full rebuild.
    bool insert(int index) {
        if (root == nullptr) return false;
        return root->insert(index);
    }

    std::vector<int> queryRange(const juce::Rectangle<float>& range) const {
        std::vector<int> results;
        if (root != nullptr) {
            root->query(range, results);
        }
        return results;
    }

    // Buffer-reusing overload. The value-returning version above allocates a
    // fresh vector on every call, which matters because SampleCanvas queries
    // the tree on every paint() *and* every mouseMove() -- i.e. up to twice per
    // frame while the user is exploring the map. Passing a caller-owned buffer
    // that is only ever `clear()`ed (capacity retained) makes the steady-state
    // cost of viewport culling and hit-testing allocation-free.
    void queryRange(const juce::Rectangle<float>& range, std::vector<int>& results) const {
        results.clear();
        if (root != nullptr) {
            root->query(range, results);
        }
    }

    void clear() {
        root.reset();
        itemsPtr = nullptr;
    }

    bool isBuilt() const { return root != nullptr; }

private:
    std::unique_ptr<Node> root;
    const std::vector<SampleItem>* itemsPtr = nullptr;
};
