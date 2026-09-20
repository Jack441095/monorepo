#include <cstdlib>
#include <iostream>

#include "AbletonTaxonomy.h"

// Pure-logic regression test for AbletonTaxonomy's classify() and
// detectLoopVsOneShot() -- no audio decoding, ONNX, or JUCE dependency
// needed, since the module itself has none. Synthetic AudioFeatures values
// stand in for what analyzeAudioBuffer() would have produced.

namespace {

int failures = 0;

void expectEqual(const std::string& actual, const std::string& expected, const std::string& label)
{
    if (actual != expected) {
        std::cerr << "FAIL: " << label << " -- expected \"" << expected << "\", got \"" << actual << "\"" << std::endl;
        ++failures;
    }
}

void expectTrue(bool condition, const std::string& label)
{
    if (!condition) {
        std::cerr << "FAIL: " << label << std::endl;
        ++failures;
    }
}

} // namespace

int main()
{
    using namespace AbletonTaxonomy;

    // A short, fast-decaying, low-frequency-dominant hit maps cleanly to Kick / One-Shot.
    {
        ClassificationInput in;
        in.existingInstrumentType = "Kick";
        in.durationSeconds = 0.3f;
        in.decayTimeSeconds = 0.15f;
        in.lowEnergyRatio = 0.9f;
        in.zcr = 0.05f;
        Classification result = classify(in);
        expectEqual(result.category, "Drums", "Kick category");
        expectEqual(result.subcategory, "Kick", "Kick subcategory (short, fast decay -> one-shot)");
        expectTrue(result.confidence > 0.5f, "Kick confidence should be reasonably high");
    }

    // Same instrumentType bucket, but long-duration + sustained decay should
    // flip the subcategory to the loop variant via detectLoopVsOneShot.
    {
        ClassificationInput in;
        in.existingInstrumentType = "Bass";
        in.durationSeconds = 4.0f;
        // decay/duration = 0.975 > 0.9 threshold. Threshold raised 0.6->0.9
        // alongside the decayTimeSeconds envelope-follower fix (see
        // docs/classification/DECAY_TIME_ENVELOPE_FIX_V1_REPORT.md) -- real
        // audio's decay ratio is far noisier than this synthetic 0.6-era
        // value assumed, so this fixture is now clearly, not marginally,
        // above threshold to keep testing the same "obviously sustained"
        // design intent rather than a boundary case.
        in.decayTimeSeconds = 3.9f;
        in.lowEnergyRatio = 0.8f;
        Classification result = classify(in);
        expectEqual(result.category, "Bass", "Long sustained Bass category");
        expectEqual(result.subcategory, "Bass Loop", "Long sustained Bass should classify as Bass Loop");
        bool hasLoopTag = false;
        for (const auto& tag : result.secondaryTags) if (tag == "Loop") hasLoopTag = true;
        expectTrue(hasLoopTag, "Bass Loop should carry a Loop secondary tag");
    }

    // A short one-shot Bass hit should NOT be tagged as a loop.
    {
        ClassificationInput in;
        in.existingInstrumentType = "Bass";
        in.durationSeconds = 0.6f;
        in.decayTimeSeconds = 0.2f;
        Classification result = classify(in);
        expectEqual(result.subcategory, "Bass One-Shot", "Short Bass hit should classify as Bass One-Shot");
    }

    // The "Loop" bucket (classifyAudioFeatures' own catch-all) splits into
    // Ambience/Atmosphere for noise-like content vs. Instruments/Music Loop
    // for tonal content, based on zcr/lowEnergyRatio.
    {
        ClassificationInput in;
        in.existingInstrumentType = "Loop";
        in.zcr = 0.4f;            // noise-like
        in.lowEnergyRatio = 0.2f; // not low-end dominant
        Classification result = classify(in);
        expectEqual(result.category, "Ambience", "Noise-like Loop should map to Ambience");
        expectEqual(result.subcategory, "Atmosphere", "Noise-like Loop subcategory");
    }
    {
        ClassificationInput in;
        in.existingInstrumentType = "Loop";
        in.zcr = 0.1f;
        in.lowEnergyRatio = 0.7f;
        Classification result = classify(in);
        expectEqual(result.category, "Instruments", "Tonal Loop should map to Instruments");
        expectEqual(result.subcategory, "Music Loop", "Tonal Loop subcategory");
    }

    // Unrecognized/"Other" instrumentType must not invent a confident guess.
    {
        ClassificationInput in;
        in.existingInstrumentType = "Other";
        Classification result = classify(in);
        expectEqual(result.category, "", "Other instrumentType should leave category empty");
        expectTrue(result.confidence == 0.0f, "Other instrumentType should have zero confidence");
    }

    // Hi-Hat subcategory canonicalization and winningEvidence preservation.
    {
        ClassificationInput in;
        in.existingInstrumentType = "Hi-Hat";
        in.durationSeconds = 0.2f;
        in.decayTimeSeconds = 0.05f;
        in.winningEvidence = "FILENAME";
        Classification result = classify(in);
        expectEqual(result.category, "Drums", "Hi-Hat category");
        expectEqual(result.subcategory, "Hi-Hat", "Hi-Hat subcategory");
        expectEqual(result.winningEvidence, "FILENAME", "Hi-Hat winningEvidence");
    }

    // detectLoopVsOneShot directly: a long, sustained-decay signal should read as a loop.
    // Threshold raised 0.6->0.9 (see docs/classification/DECAY_TIME_ENVELOPE_FIX_V1_REPORT.md);
    // 2.9/3.0 = 0.967, clearly above it.
    {
        LoopDetectionResult r = detectLoopVsOneShot(3.0f, 2.9f);
        expectTrue(r.isLoop, "Long sustained signal should be detected as a loop");
    }
    // A short, fast-decaying signal should read as a one-shot with reasonable confidence.
    {
        LoopDetectionResult r = detectLoopVsOneShot(0.4f, 0.1f);
        expectTrue(!r.isLoop, "Short fast-decay signal should be detected as a one-shot");
        expectTrue(r.confidence >= 0.5f, "Clear one-shot case should have reasonably high confidence");
    }
    // An ambiguous case (long duration, but fast decay -- e.g. a cymbal
    // tail) should still default to one-shot, but honestly at low confidence.
    {
        LoopDetectionResult r = detectLoopVsOneShot(3.0f, 0.2f);
        expectTrue(!r.isLoop, "Ambiguous long/fast-decay case should default to one-shot");
        expectTrue(r.confidence < 0.4f, "Ambiguous case must not claim high confidence");
    }

    // Vocal instrumentType mapping to Vocals category and Vocal Phrase / Vocal Loop subcategories
    {
        ClassificationInput in;
        in.existingInstrumentType = "Vocal";
        in.durationSeconds = 0.5f;
        in.decayTimeSeconds = 0.25f;
        Classification result = classify(in);
        expectEqual(result.category, "Vocals", "Vocal category");
        expectEqual(result.subcategory, "Vocal Phrase", "Vocal Phrase subcategory for short vocal sample");
        expectTrue(result.confidence >= 0.5f, "Vocal confidence should be reasonably high");
    }

    // --- measured 3-arg rule (duration + sustained-energy ratio) -----------
    // 96.4% held-out on 649 by-ear labels vs 90.8% for duration alone.
    {
        // A genuine loop: long AND energy persists to the end.
        LoopDetectionResult r = detectLoopVsOneShot(4.0f, 0.5f, 0.87f);
        if (!r.isLoop) { std::cerr << "FAIL: long + sustained energy should be a loop" << std::endl; ++failures; }
        else std::cout << "  ok: long + sustained energy -> Loop" << std::endl;
    }
    {
        // The case the old heuristic could not handle: a crash rings past the
        // duration threshold but its energy is gone by the final third.
        LoopDetectionResult r = detectLoopVsOneShot(3.2f, 2.0f, 0.00f);
        if (r.isLoop) { std::cerr << "FAIL: long crash with decayed tail must not be a Loop" << std::endl; ++failures; }
        else std::cout << "  ok: long crash (energy decayed) -> One-Shot" << std::endl;
    }
    {
        // Too short to tile, regardless of sustain.
        LoopDetectionResult r = detectLoopVsOneShot(0.4f, 0.1f, 1.0f);
        if (r.isLoop) { std::cerr << "FAIL: short sample must not be a Loop" << std::endl; ++failures; }
        else std::cout << "  ok: short sample -> One-Shot" << std::endl;
    }

    // --- Foley as a SOURCE attribute, not a class -------------------------
    {
        struct { const char* name; bool expect; const char* why; } cases[] = {
            {"JVIEWS_hihat_alternative_clock_shop_113.wav", true,  "hi-hat MADE from clock recordings is foley-sourced"},
            {"EOD_Foley 1.wav",                             true,  "explicit foley wording"},
            {"Kitchen_Cutlery_03.wav",                      true,  "physical object nouns"},
            {"KSHMR_Closed_Hat_10_Dirty.wav",               false, "'dirty' means distorted, not dirt"},
            {"KSHMR_Snare_Enhancer_20_Knock.wav",           false, "'knock' describes snare punch"},
            {"Snare - Metal Spread 1.wav",                  false, "'metal' is often a genre descriptor"},
            {"KSHMR_Punchy_Kick_21_F#.wav",                 false, "ordinary drum sample"},
        };
        for (const auto& c : cases) {
            const bool got = isFoleySourced(c.name);
            if (got != c.expect) {
                std::cerr << "FAIL: isFoleySourced(\"" << c.name << "\") expected "
                          << c.expect << " -- " << c.why << std::endl;
                ++failures;
            } else {
                std::cout << "  ok: foley-sourced=" << (got ? "yes" : "no ")
                          << "  " << c.why << std::endl;
            }
        }
    }

    // ---------------------------------------------------------------
    // V4 Final Closeout: Vocal Loop <-> Vocal Phrase filename-evidence
    // fix (AbletonTaxonomy::detectFilenameSubcategoryEvidence + the
    // classify() Vocal-scoped override). See
    // docs/SLO_VOCAL_FILENAME_EVIDENCE_REPORT.md for the forensics and
    // rule derivation. Tokens below simulate SampleManagerEngine's
    // tokenizeString() output for each conceptual filename (lowercase,
    // split on '_'/'-'/' '/digits) so this exercises the actual
    // production evidence function, not a re-implementation of it.
    // ---------------------------------------------------------------

    auto classifyVocalWithTokens = [](const std::vector<std::string>& nameTokens,
                                       float durationSeconds, float decayTimeSeconds) -> Classification {
        ClassificationInput in;
        in.existingInstrumentType = "Vocal";
        in.durationSeconds = durationSeconds;
        in.decayTimeSeconds = decayTimeSeconds;
        in.filenameEvidence = detectFilenameSubcategoryEvidence(nameTokens, {});
        return classify(in);
    };

    // POSITIVE: explicit "loop" token should win Vocal Loop even when the
    // DSP duration/decay signal alone would have said one-shot/phrase
    // (short duration, fast decay -- exactly the V4-H-diagnosed failure
    // mode: a real vocal loop file that happens to be a short clip).
    {
        // vocal_loop_01.wav -> tokens: vocal, loop (digits stripped by tokenizeString)
        Classification r = classifyVocalWithTokens({"vocal", "loop"}, 0.4f, 0.15f);
        expectEqual(r.category, "Vocals", "vocal_loop_01.wav category");
        expectEqual(r.subcategory, "Vocal Loop", "vocal_loop_01.wav should be Vocal Loop despite short DSP duration");
    }
    {
        // vox_loop_174.wav -> tokens: vox, loop
        Classification r = classifyVocalWithTokens({"vox", "loop"}, 0.5f, 0.2f);
        expectEqual(r.subcategory, "Vocal Loop", "vox_loop_174.wav should be Vocal Loop");
    }
    {
        // female_vocal_loop.wav -> tokens: female, vocal, loop
        Classification r = classifyVocalWithTokens({"female", "vocal", "loop"}, 0.6f, 0.2f);
        expectEqual(r.subcategory, "Vocal Loop", "female_vocal_loop.wav should be Vocal Loop");
    }
    {
        // acapella_loop.wav -> tokens: acapella, loop
        Classification r = classifyVocalWithTokens({"acapella", "loop"}, 0.5f, 0.15f);
        expectEqual(r.subcategory, "Vocal Loop", "acapella_loop.wav should be Vocal Loop");
    }
    {
        // choir_loop.wav -> tokens: choir, loop
        Classification r = classifyVocalWithTokens({"choir", "loop"}, 0.5f, 0.15f);
        expectEqual(r.subcategory, "Vocal Loop", "choir_loop.wav should be Vocal Loop");
    }
    {
        // lead_vocal_loop.wav -> tokens: lead, vocal, loop (category-detection
        // precedence, unaffected by this fix, is exercised upstream in
        // SampleManagerEngine; here we only prove the subcategory choice
        // once existingInstrumentType is already "Vocal").
        Classification r = classifyVocalWithTokens({"lead", "vocal", "loop"}, 0.4f, 0.1f);
        expectEqual(r.subcategory, "Vocal Loop", "lead_vocal_loop.wav should be Vocal Loop");
    }
    {
        // vocal_lead_loop.wav -> tokens: vocal, lead, loop
        Classification r = classifyVocalWithTokens({"vocal", "lead", "loop"}, 0.4f, 0.1f);
        expectEqual(r.subcategory, "Vocal Loop", "vocal_lead_loop.wav should be Vocal Loop");
    }

    // NEGATIVE: "phrase" (and "chop"/"oneshot") token must not be beaten by
    // a coincidentally loop-shaped DSP signal, and must not regress the
    // pre-existing default behavior.
    {
        // vocal_phrase.wav -> tokens: vocal, phrase; give it a loop-shaped
        // DSP signal (long + sustained) to prove the filename evidence, not
        // the DSP fallback, is what's deciding this.
        Classification r = classifyVocalWithTokens({"vocal", "phrase"}, 4.0f, 3.5f);
        expectEqual(r.subcategory, "Vocal Phrase", "vocal_phrase.wav should stay Vocal Phrase even with loop-shaped DSP signal");
    }
    {
        // spoken_phrase.wav -> tokens: spoken, phrase
        Classification r = classifyVocalWithTokens({"spoken", "phrase"}, 0.5f, 0.2f);
        expectEqual(r.subcategory, "Vocal Phrase", "spoken_phrase.wav should be Vocal Phrase");
    }
    {
        // vox_phrase.wav -> tokens: vox, phrase
        Classification r = classifyVocalWithTokens({"vox", "phrase"}, 0.5f, 0.2f);
        expectEqual(r.subcategory, "Vocal Phrase", "vox_phrase.wav should be Vocal Phrase");
    }
    {
        // vocal_chop.wav -> tokens: vocal, chop
        Classification r = classifyVocalWithTokens({"vocal", "chop"}, 0.3f, 0.1f);
        expectEqual(r.subcategory, "Vocal Phrase", "vocal_chop.wav should be Vocal Phrase (no separate Vocal One-Shot subcategory)");
    }
    {
        // vocal_one_shot.wav -> tokens: vocal, one, shot (no exact "oneshot"
        // token; "one"/"shot" are deliberately NOT treated as evidence --
        // this must fall through to the DSP heuristic, which for a short
        // fast-decaying clip already correctly defaults to Vocal Phrase).
        Classification r = classifyVocalWithTokens({"vocal", "one", "shot"}, 0.3f, 0.1f);
        expectEqual(r.subcategory, "Vocal Phrase", "vocal_one_shot.wav should be Vocal Phrase via DSP fallback");
    }

    // AMBIGUOUS: both tokens present -- must fall through to the existing
    // DSP-only heuristic rather than guessing, i.e. behavior here must be
    // byte-identical to pre-fix behavior for this specific input.
    {
        // vocal_phrase_loop.wav -> tokens: vocal, phrase, loop; DSP signal
        // is clearly loop-shaped, so the (unchanged) DSP heuristic should
        // say Vocal Loop here, driven by DSP -- not by the ambiguous tokens.
        // Ratio 3.9/4.0=0.975, clearly above the 0.6->0.9 threshold raise
        // (see docs/classification/DECAY_TIME_ENVELOPE_FIX_V1_REPORT.md).
        Classification r = classifyVocalWithTokens({"vocal", "phrase", "loop"}, 4.0f, 3.9f);
        expectEqual(r.subcategory, "Vocal Loop", "vocal_phrase_loop.wav (ambiguous tokens) should fall through to DSP heuristic");
    }

    // ---------------------------------------------------------------
    // Real-corpus forensics finding: the V4-H qualification corpus's actual
    // vendor filenames (KSHMR packs) essentially never spell out the words
    // "loop"/"phrase" -- instead, Vocal Loop ground truth is 53/53 (100%)
    // suffixed with a BPM+key pair (e.g. "..._128_D.wav") and Vocal Phrase
    // ground truth is 0/100 (0%) so suffixed. These tests exercise that
    // real-corpus-representative pattern directly, using
    // rawNameSegments (the digit-preserving split), separately from the
    // word-token tests above.
    // ---------------------------------------------------------------

    auto classifyVocalWithRawSegments = [](const std::vector<std::string>& rawSegments,
                                            float durationSeconds, float decayTimeSeconds) -> Classification {
        ClassificationInput in;
        in.existingInstrumentType = "Vocal";
        in.durationSeconds = durationSeconds;
        in.decayTimeSeconds = decayTimeSeconds;
        in.filenameEvidence = detectFilenameSubcategoryEvidence({}, {}, rawSegments);
        return classify(in);
    };

    {
        // KSHMR_Vocal_Energy_Booster_01_Ahh_128_D.wav (real ground-truth
        // Vocal Loop filename, no "loop" word) -- give it a short/one-shot-
        // shaped DSP signal to prove the BPM+key evidence, not DSP, decides.
        Classification r = classifyVocalWithRawSegments(
            {"kshmr", "vocal", "energy", "booster", "01", "ahh", "128", "d"}, 0.4f, 0.1f);
        expectEqual(r.subcategory, "Vocal Loop", "KSHMR Vocal_Energy_Booster (BPM+key suffix, no 'loop' word) should be Vocal Loop");
    }
    {
        // KSHMR_Vocal_Melody_01_88_C#m.wav (real ground-truth Vocal Loop filename)
        Classification r = classifyVocalWithRawSegments(
            {"kshmr", "vocal", "melody", "01", "88", "c#m"}, 0.4f, 0.1f);
        expectEqual(r.subcategory, "Vocal Loop", "KSHMR Vocal_Melody (BPM+key suffix) should be Vocal Loop");
    }
    {
        // Cross-vendor Loaded Samples convention: vocal loops often carry a
        // tempo marker but no key (for example "Vocal_72_BPM"). This should
        // be a Vocal-only loop hint, not a key inference and not a global
        // loop override for other instrument families.
        FilenameSubcategoryEvidence ev = detectFilenameSubcategoryEvidence(
            {}, {}, {"vocal", "72", "bpm"});
        expectTrue(ev.hasTempoMarker, "tempo-only BPM marker should be detected");
        Classification r = classifyVocalWithRawSegments(
            {"vocal", "72", "bpm"}, 0.5f, 0.1f);
        expectEqual(r.subcategory, "Vocal Loop", "tempo-only vocal filename should be Vocal Loop");
        expectTrue(r.confidence < 0.6f,
                   "tempo-only vocal loop evidence should remain below the stronger filename confidence tier");
    }
    {
        // Real vendor spelling wraps the suffix in brackets: "[72 BPM]".
        // Boundary punctuation must not hide the same tempo-only evidence.
        FilenameSubcategoryEvidence ev = detectFilenameSubcategoryEvidence(
            {}, {}, {"rollin", "deep", "with", "the", "click", "[72", "bpm]"});
        expectTrue(ev.hasTempoMarker,
                   "bracketed BPM marker should be detected after boundary normalization");
    }
    {
        // Brackets/parentheses around a tempo+key suffix are also common in
        // commercial packs and must retain the stronger loop signal.
        FilenameSubcategoryEvidence ev = detectFilenameSubcategoryEvidence(
            {}, {}, {"stem", "[73", "bpm]", "(f#)"});
        expectTrue(ev.hasTempoKeySuffix,
                   "bracketed BPM+key suffix should be detected after boundary normalization");
    }
    {
        // KSHMR_Numbers_123_Cmon_115.wav (real ground-truth Vocal Phrase --
        // has a bare number "115" but NO adjacent key token, so must NOT
        // trigger the BPM+key rule) -- give it a long/loop-shaped DSP
        // signal to prove filename evidence (absence of it) isn't
        // incorrectly firing here either; DSP fallback still applies.
        Classification r = classifyVocalWithRawSegments(
            {"kshmr", "numbers", "123", "cmon", "115"}, 0.5f, 0.15f);
        expectEqual(r.subcategory, "Vocal Phrase", "KSHMR Numbers phrase (bare number, no key) should stay Vocal Phrase");
    }
    {
        // A bare index number ("01") must not be misread as a BPM.
        FilenameSubcategoryEvidence ev = detectFilenameSubcategoryEvidence({}, {}, {"vocal", "loop", "01"});
        expectTrue(!ev.hasTempoKeySuffix, "bare index number adjacent to nothing key-like must not set hasTempoKeySuffix");
    }
    {
        // BPM number with no key neighbor at all must not trigger.
        FilenameSubcategoryEvidence ev = detectFilenameSubcategoryEvidence({}, {}, {"vocal", "phrase", "128"});
        expectTrue(!ev.hasTempoKeySuffix, "BPM number with no adjacent key token must not set hasTempoKeySuffix");
    }
    {
        // A number near the word BPM is a tempo marker, but an unlabelled
        // number remains ordinary variation/index metadata.
        FilenameSubcategoryEvidence ev = detectFilenameSubcategoryEvidence({}, {}, {"vocal", "01", "bpm"});
        expectTrue(!ev.hasTempoMarker, "out-of-range BPM marker must not fire");
    }
    {
        // key_bpm order (reverse of the common bpm_key order) should also count.
        FilenameSubcategoryEvidence ev = detectFilenameSubcategoryEvidence({}, {}, {"vocal", "d", "128"});
        expectTrue(ev.hasTempoKeySuffix, "key-then-bpm order should also set hasTempoKeySuffix");
    }
    {
        // Non-Vocal instrumentType: BPM+key suffix must not leak into other
        // buckets' subcategory decisions either (fix stays Vocal-scoped).
        ClassificationInput in;
        in.existingInstrumentType = "Synth";
        in.durationSeconds = 0.4f;
        in.decayTimeSeconds = 0.1f;
        in.filenameEvidence = detectFilenameSubcategoryEvidence({}, {}, {"synth", "loop", "128", "d"});
        Classification r = classify(in);
        expectEqual(r.subcategory, "Synth", "BPM+key suffix must not affect non-Vocal instrumentTypes (fix is Vocal-scoped)");
    }

    // Sanity: detectFilenameSubcategoryEvidence in isolation.
    {
        FilenameSubcategoryEvidence ev = detectFilenameSubcategoryEvidence({"vocal", "loop"}, {});
        expectTrue(ev.hasLoopToken, "vocal+loop tokens should set hasLoopToken");
        expectTrue(!ev.hasOneShotToken, "vocal+loop tokens should not set hasOneShotToken");
    }
    {
        // Folder-only evidence (e.g. a file inside a "Vocal Loops/" folder)
        // should count too, same as the existing FOLDER evidence tier.
        FilenameSubcategoryEvidence ev = detectFilenameSubcategoryEvidence({"vocal", "01"}, {"vocal", "loops"});
        expectTrue(ev.hasLoopToken, "folder-only 'loops' token should set hasLoopToken");
    }

    // Non-Vocal instrumentTypes must be completely unaffected by this fix
    // (it is explicitly scoped to Vocal only) -- "loop" evidence must not
    // leak into Bass/Synth/Drums subcategory decisions.
    {
        // bass_loop.wav given a short, one-shot-shaped DSP signal: pre-fix
        // behavior (DSP-only) must be preserved -- Bass Loop evidence must
        // NOT override the DSP decision the way it now does for Vocal.
        ClassificationInput in;
        in.existingInstrumentType = "Bass";
        in.durationSeconds = 0.5f;
        in.decayTimeSeconds = 0.15f;
        in.filenameEvidence = detectFilenameSubcategoryEvidence({"bass", "loop"}, {});
        Classification r = classify(in);
        expectEqual(r.subcategory, "Bass One-Shot", "bass_loop.wav subcategory must still be driven by DSP only (fix is Vocal-scoped)");
    }
    {
        // drum_loop.wav and fx_loop.wav resolve to the "Loop" instrumentType
        // bucket upstream (no vocal token match), which has its own
        // Ambience/Music-Loop branch entirely untouched by this fix.
        ClassificationInput in;
        in.existingInstrumentType = "Loop";
        in.zcr = 0.1f;
        in.lowEnergyRatio = 0.7f;
        in.filenameEvidence = detectFilenameSubcategoryEvidence({"drum", "loop"}, {});
        Classification r = classify(in);
        expectEqual(r.category, "Instruments", "drum_loop.wav (Loop bucket) category unaffected by Vocal-scoped fix");
        expectEqual(r.subcategory, "Music Loop", "drum_loop.wav (Loop bucket) subcategory unaffected by Vocal-scoped fix");
    }
    {
        // synth_lead.wav / lead_synth.wav never reach classify() as
        // existingInstrumentType == "Vocal" at all (category detection
        // upstream, unaffected by this change, resolves "lead" to Synth
        // when no vocal token is present) -- confirm the Synth path here
        // is untouched and not accidentally reachable via this fix.
        ClassificationInput in;
        in.existingInstrumentType = "Synth";
        in.durationSeconds = 0.4f;
        in.decayTimeSeconds = 0.1f;
        in.filenameEvidence = detectFilenameSubcategoryEvidence({"synth", "lead"}, {});
        Classification r = classify(in);
        expectEqual(r.category, "Instruments", "synth_lead.wav should classify as Instruments, not Vocals");
        expectEqual(r.subcategory, "Synth", "synth_lead.wav should classify as Synth one-shot");
    }

    // The product taxonomy has 17 classes, while the frozen acoustic head has
    // 16 outputs and intentionally does not emit Atmosphere. Keep that model
    // boundary explicit: every acoustic output must map to a product label,
    // but Atmosphere must not be presented as an acoustic-model prediction.
    {
        const char* acousticClasses[] = {
            "Bass Loop", "Bass One-Shot", "Clap", "FX", "Foley", "Hi-Hat",
            "Impact", "Kick", "Music Loop", "Percussion", "Riser", "Snare",
            "Synth", "Synth Loop", "Vocal Loop", "Vocal Phrase"
        };
        for (const auto* acousticClass : acousticClasses) {
            std::string category;
            std::string subcategory;
            expectTrue(mapAcousticClassToTaxonomy(acousticClass, category, subcategory)
                           && !category.empty() && !subcategory.empty(),
                       std::string("frozen acoustic class must map: ") + acousticClass);
        }

        std::string category;
        std::string subcategory;
        expectTrue(!mapAcousticClassToTaxonomy("Atmosphere", category, subcategory),
                   "Atmosphere must remain outside the 16-class acoustic head");
    }

    if (failures == 0) {
        std::cout << "ALL TAXONOMY TESTS PASSED SUCCESSFULLY!" << std::endl;
        return 0;
    }
    std::cerr << failures << " taxonomy test(s) FAILED." << std::endl;
    return 1;
}
