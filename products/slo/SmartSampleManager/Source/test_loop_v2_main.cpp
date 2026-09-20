#include <algorithm>
#include <cmath>
#include <iostream>
#include "AbletonTaxonomy.h"

// P2-2 LOOP V2SPIKE contract: with the flag OFF, classify() reproduces V1
// exactly (filename alone decides one-sided Vocal evidence). With the flag
// ON, confident DSP disagreement overrules the filename at discounted
// confidence with a "Contested" tag; agreement and weak-DSP cases are
// identical to V1. Pure logic, synthetic inputs, no audio/engine.

static int fails = 0;
static void check(const char* name, bool cond) {
    std::cout << (cond ? "  PASS  " : "  FAIL  ") << name << "\n";
    if (!cond) ++fails;
}

static bool hasTag(const AbletonTaxonomy::Classification& c, const std::string& tag) {
    return std::find(c.secondaryTags.begin(), c.secondaryTags.end(), tag) != c.secondaryTags.end();
}

static AbletonTaxonomy::ClassificationInput vocalPhraseNamed(float duration, float energyRatio) {
    AbletonTaxonomy::ClassificationInput in;
    in.existingInstrumentType = "Vocal";
    in.winningEvidence = "FILENAME";
    in.filenameEvidence.hasOneShotToken = true; // e.g. "..._phrase_..."
    in.durationSeconds = duration;
    in.energyDecayRatio = energyRatio;
    return in;
}

static AbletonTaxonomy::ClassificationInput vocalLoopNamed(float duration, float energyRatio) {
    auto in = vocalPhraseNamed(duration, energyRatio);
    in.filenameEvidence.hasOneShotToken = false;
    in.filenameEvidence.hasLoopToken = true; // e.g. "..._loop_..."
    return in;
}

int main() {
    using namespace AbletonTaxonomy;

    setLoopV2Enabled(false);
    check("flag defaults OFF", !loopV2Enabled());

    // 1. Flag OFF: one-sided filename decides alone (V1 behavior under test).
    Classification v1Phrase;
    {
        Classification c = classify(vocalPhraseNamed(8.0f, 0.9f));
        v1Phrase = c;
        check("off: phrase token wins", c.subcategory == "Vocal Phrase" && !hasTag(c, "Contested"));
    }

    setLoopV2Enabled(true);

    // 2. Flag ON: sustained 8s audio overrules the phrase token.
    {
        Classification c = classify(vocalPhraseNamed(8.0f, 0.9f));
        check("on: DSP loop wins", c.subcategory == "Vocal Loop" && hasTag(c, "Contested"));
        check("on: disagreement discounted", c.confidence < v1Phrase.confidence);
    }

    // 3. Flag ON, opposite direction: short audio overrules the loop token.
    {
        Classification c = classify(vocalLoopNamed(0.5f, 1.0f));
        check("on: DSP one-shot wins", c.subcategory == "Vocal Phrase" && hasTag(c, "Contested"));
    }

    // 4. Agreement: identical to V1, no Contested tag.
    {
        Classification c = classify(vocalLoopNamed(8.0f, 0.9f));
        check("agreement untouched", c.subcategory == "Vocal Loop" && !hasTag(c, "Contested"));
    }

    // 5. Weak DSP (0.70 long-decayed path < 0.80 floor): filename stands.
    // 3s + fully decayed: long enough to be in the tail case but below the
    // 4s "veryLong" escape hatch, so the vote lands at exactly 0.70.
    {
        Classification c = classify(vocalLoopNamed(3.0f, 0.0f));
        check("weak DSP defers", c.subcategory == "Vocal Loop" && !hasTag(c, "Contested"));
    }

    // 6. Ambiguous filename (no tokens either side): DSP path, flag-irrelevant.
    {
        ClassificationInput in = vocalPhraseNamed(8.0f, 0.9f);
        in.filenameEvidence.hasOneShotToken = false;
        Classification on = classify(in);
        setLoopV2Enabled(false);
        Classification off = classify(in);
        setLoopV2Enabled(true);
        check("ambiguous identical on/off",
              on.subcategory == off.subcategory               && std::abs(on.confidence - off.confidence) < 1e-6f
              && !hasTag(on, "Contested"));
    }

    setLoopV2Enabled(false);
    check("flag restored OFF", !loopV2Enabled());

    std::cout << (fails == 0 ? "ALL LOOP V2 CHECKS PASSED" : "LOOP V2 CHECKS FAILED") << std::endl;
    return fails == 0 ? 0 : 1;
}
