#include <cmath>
#include <cstdlib>
#include <iostream>
#include <limits>

#include "AcousticClassifier.h"
#include "SampleManagerEngine.h"
#include "TestCacheDbIsolation.h"

// Regression test for the UMAP eligibility predicate (see
// collectUmapEligibleSamples() in SampleManagerEngine.cpp).
//
// runFullUMAP() used two different predicates to answer the same question: it
// sized its fixed-length flatEmbeddings buffer with hasUsableEmbedding() (so
// isProcessed-without-an-embedding items were skipped) but wrote coordinates
// back with `!s.isProcessed` (so those same items were counted afterwards).
// That index desync read past the end of the projection buffer and stamped
// coordinates computed for one sample onto a different one. This test pins the
// single shared predicate the fix introduced, so a future reintroduction of
// the mismatch fails immediately without needing to run umappp itself.

namespace {

int failures = 0;

void expectTrue(bool condition, const char* label)
{
    if (!condition) {
        std::cerr << "FAIL: " << label << std::endl;
        ++failures;
    }
}

// Builds a full 512-D embedding that hasSafeEmbeddingBuffer() accepts:
// nonzero component (the zero vector is rejected), all finite, norm not
// arithmetic-overflow-scale.
std::vector<float> makeValidEmbedding()
{
    std::vector<float> embedding(static_cast<size_t>(AcousticClassifier::pannsDim), 0.0f);
    embedding[0] = 1.0f;
    return embedding;
}

bool testEligibilityPredicate()
{
    std::vector<SampleItem> samples;
    samples.resize(8);

    auto valid = makeValidEmbedding();

    // [0] Fully eligible: processed with a Valid, safe embedding.
    samples[0].isProcessed = true;
    samples[0].embeddingStatus = EmbeddingStatus::Valid;
    samples[0].embedding = valid;

    // [1] Processed but retryable failure -- embedding cleared.
    samples[1].isProcessed = true;
    samples[1].embeddingStatus = EmbeddingStatus::FailedRetryable;
    samples[1].embedding = valid;

    // [2] Processed but permanent failure -- embedding cleared.
    samples[2].isProcessed = true;
    samples[2].embeddingStatus = EmbeddingStatus::FailedPermanent;
    samples[2].embedding = valid;

    // [3] Processed and Valid but the embedding buffer is empty.
    samples[3].isProcessed = true;
    samples[3].embeddingStatus = EmbeddingStatus::Valid;

    // [4] Processed and Valid but the buffer is the wrong length.
    samples[4].isProcessed = true;
    samples[4].embeddingStatus = EmbeddingStatus::Valid;
    samples[4].embedding.assign(16, 0.5f);

    // [5] Processed and Valid but non-finite values in the buffer.
    samples[5].isProcessed = true;
    samples[5].embeddingStatus = EmbeddingStatus::Valid;
    samples[5].embedding = valid;
    samples[5].embedding[static_cast<size_t>(7)] = std::numeric_limits<float>::quiet_NaN();

    // [6] Not processed at all, never analysed.
    samples[6].embeddingStatus = EmbeddingStatus::NotAnalysed;

    // [7] Processed and Valid with a full-length safe buffer at the other end
    // of the vector -- must round-trip the stable-order guarantee.
    samples[7].isProcessed = true;
    samples[7].embeddingStatus = EmbeddingStatus::Valid;
    samples[7].embedding = valid;

    auto eligible = collectUmapEligibleSamples(samples);

    expectTrue(eligible.size() == 2, "exactly the two valid samples must be eligible");
    if (eligible.size() != 2) {
        std::cerr << "       got " << eligible.size() << " eligible samples" << std::endl;
        return false;
    }

    expectTrue(eligible[0]->name.empty() && eligible[0]->filePath.empty()
                   && eligible[0]->embedding[0] == 1.0f,
               "first eligible sample must be samples[0]");
    expectTrue(eligible[0] == &samples[0],
               "eligible sample 0 must be a pointer into the source vector");
    expectTrue(eligible[1] == &samples[7],
               "eligible sample 1 must be samples[7], preserving source order");

    // None of the ineligible variants may slip through, whatever the buffer
    // length and status combination.
    for (int i = 1; i <= 6; ++i) {
        for (auto* s : eligible) {
            expectTrue(s != &samples[i],
                       "an ineligible sample must never appear in the eligible set");
        }
    }

    std::cout << "SUCCESS: UMAP eligibility predicate verified" << std::endl;
    return true;
}

bool testMutatedEmbeddingRejected()
{
    // Guard against hasSafeEmbeddingBuffer() weakening: a validate-then-
    // mutate cycle (e.g. a stale shared buffer) must still exclude the item.
    std::vector<SampleItem> samples;
    samples.resize(1);
    samples[0].isProcessed = true;
    samples[0].embeddingStatus = EmbeddingStatus::Valid;
    samples[0].embedding = makeValidEmbedding();

    samples[0].embedding.assign(samples[0].embedding.size(), 0.0f);
    auto eligible = collectUmapEligibleSamples(samples);

    expectTrue(eligible.empty(), "all-zero embedding must be excluded");
    if (!eligible.empty()) return false;

    std::cout << "SUCCESS: zeroed embedding excluded from UMAP eligibility" << std::endl;
    return true;
}

} // namespace

int main()
{
    ScopedIsolatedCacheDb _isolatedCacheDb;

    if (!testEligibilityPredicate()) return 1;
    if (!testMutatedEmbeddingRejected()) return 1;

    if (failures != 0) {
        std::cerr << failures << " UMAP eligibility check(s) failed" << std::endl;
        return 1;
    }

    std::cout << "ALL UMAP ELIGIBILITY TESTS PASSED SUCCESSFULLY!" << std::endl;
    return 0;
}