#include <iostream>
#include "MlOverrideGate.h"

// P2-1 FUSION V2SPIKE contract: the duration-overrules-filename rule fires
// if and only if the flag is ON plus every narrow precondition (confident
// non-OOD ML, FILENAME evidence, one-shot pre-ML label, ML-mapped loop,
// known-long duration). Flag OFF must reproduce V1 exactly. Pure logic:
// no JUCE, no ONNX, no engine.

static int fails = 0;
static void check(const char* name, bool cond) {
    std::cout << (cond ? "  PASS  " : "  FAIL  ") << name << "\n";
    if (!cond) ++fails;
}

static MlOverrideGate::Input longKickNamedFile() {
    MlOverrideGate::Input in;
    in.isOod = false;
    in.mlConfidence = 0.70f;
    in.winningEvidence = "FILENAME";
    in.preMlCategory = "Drums";
    in.preMlSubcategory = "Kick";
    in.preMlConfidence = 0.85f;
    in.mlSubcategory = "Music Loop"; // maps to ("Instruments","Music Loop")
    in.durationSeconds = 6.0;
    return in;
}

int main() {
    using namespace MlOverrideGate;

    setFusionV2Enabled(false);
    check("flag defaults OFF", !fusionV2Enabled());

    // 1. Flag OFF: V1 stands (FILENAME one-shot kept despite long audio).
    {
        Decision d = evaluate(longKickNamedFile());
        check("off: heuristic stands", d.tagSource == "heuristic"
              && d.subcategory == "Kick" && !d.overrideApplied && !d.fusionV2Applied);
    }

    setFusionV2Enabled(true);
    check("flag toggles ON", fusionV2Enabled());

    // 2. Flag ON, all preconditions: ML loop wins via V2.
    {
        Decision d = evaluate(longKickNamedFile());
        check("on: ML loop wins", d.tagSource == "ml_v3" && d.overrideApplied && d.fusionV2Applied);
        check("on: loop label lands", d.subcategory.find("Loop") != std::string::npos);
    }

    // 3. Short file: rule stays silent.
    {
        Input in = longKickNamedFile();
        in.durationSeconds = 2.0;
        Decision d = evaluate(in);
        check("short file stands", d.tagSource == "heuristic" && !d.fusionV2Applied);
    }

    // 4. Weak ML: confidence floor respected.
    {
        Input in = longKickNamedFile();
        in.mlConfidence = 0.30f;
        Decision d = evaluate(in);
        check("weak ML stands", d.tagSource == "heuristic" && !d.fusionV2Applied);
    }

    // 5. OOD: abstention path untouched by V2.
    {
        Input in = longKickNamedFile();
        in.isOod = true;
        Decision d = evaluate(in);
        check("OOD unaffected", !d.fusionV2Applied && d.tagSource != "ml_v3");
    }

    // 6. FOLDER evidence: V1 already overrides; V2 must not claim it.
    {
        Input in = longKickNamedFile();
        in.winningEvidence = "FOLDER";
        Decision d = evaluate(in);
        check("V1 owns FOLDER", d.overrideApplied && !d.fusionV2Applied);
    }

    // 7. ML one-shot (no loop): no trigger even when long.
    {
        Input in = longKickNamedFile();
        in.mlSubcategory = "Kick";
        Decision d = evaluate(in);
        check("ML one-shot silent", !d.fusionV2Applied);
    }

    // 8. Unknown duration: never fires.
    {
        Input in = longKickNamedFile();
        in.durationSeconds = 0.0;
        Decision d = evaluate(in);
        check("unknown duration silent", !d.fusionV2Applied && d.tagSource == "heuristic");
    }

    // 9. QC-01 adversarial: filename lies ("kick") but ML is weak — V2 stays silent.
    {
        Input in = longKickNamedFile();
        in.mlConfidence = 0.35f; // below minConfidenceForOverride (0.40)
        setFusionV2Enabled(true);
        Decision d = evaluate(in);
        check("adversarial weak-ML stands", d.tagSource == "heuristic" && !d.fusionV2Applied);
    }

    // 10. QC-01 adversarial: EMBEDDED_METADATA is never overruled by V2 (narrow to FILENAME).
    {
        Input in = longKickNamedFile();
        in.winningEvidence = "EMBEDDED_METADATA";
        setFusionV2Enabled(true);
        Decision d = evaluate(in);
        check("embedded metadata stands", !d.fusionV2Applied);
    }

    // 11. QC-01 wiring: promotion floors are the auditable gate values.
    check("promotion floors wired", kFusionV2AdversarialPromotionFloor == 0.40f
          && kFusionV2FusedPromotionFloor == 0.65f);

    setFusionV2Enabled(false); // global hygiene: leave the suite as found
    check("flag restored OFF", !fusionV2Enabled());

    std::cout << (fails == 0 ? "ALL FUSION V2 CHECKS PASSED" : "FUSION V2 CHECKS FAILED") << std::endl;
    return fails == 0 ? 0 : 1;
}
