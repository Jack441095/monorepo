#!/usr/bin/env python3
"""Tests for the name evidence extractor and the audio cross-check."""
import os, sys
SD = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, SD)
import name_evidence as ne, name_audio_crosscheck as xc
FAILED = []
def check(n, c, d=""):
    print(f"  {'PASS' if c else 'FAIL'}  {n}" + (f"  -- {d}" if d else ""))
    if not c: FAILED.append(n)

def main():
    print("name evidence:\n")
    print("1. producer shorthand maps to the right candidate")
    for fn, want in (("SNR_01.wav","Snare"),("snr_hit.wav","Snare"),
                     ("Snare_Top.wav","Snare"),("BD_909.wav","Kick"),
                     ("kik_03.wav","Kick"),("Kick_Deep.wav","Kick"),
                     ("HH_closed.wav","Hi-Hat"),("CHH_01.wav","Hi-Hat"),
                     ("OHH_open.wav","Hi-Hat"),("CLP_02.wav","Clap"),
                     ("clap_big.wav","Clap")):
        e = ne.extract(fn)
        check(f"{fn:18} -> {want}", want in e.candidate_classes,
              str(e.candidate_classes))

    print("\n2. bass shorthand reaches the Bass family")
    for fn in ("808_sub_C.wav","reese_growl.wav","sub_bass_low.wav","BS_deep.wav"):
        e = ne.extract(fn)
        check(f"{fn:18} -> Bass family", "Bass" in e.candidate_families,
              str(e.candidate_families))

    print("\n3. high-risk tokens are marked and cannot claim a class")
    for fn in ("Leek Snap.wav","big hit 3.wav","tops_128.wav","chord_stab.wav",
               "texture_bed.wav"):
        e = ne.extract(fn)
        check(f"{fn:18} risk=high", e.risk_level == "high", e.risk_level)
        check(f"{fn:18} claims no exact class", not e.candidate_classes,
              str(e.candidate_classes))

    print("\n4. everything requires audio confirmation")
    check("even a 100%-precision token needs audio",
          ne.extract("BD_01.wav").requires_audio_confirmation)

    print("\n5. the sd/snap identity hazards are gone from the shipped detector")
    import importlib, name_detect as nd; importlib.reload(nd)
    check("sd no longer claims Snare", nd.detect("SD_Kick_heavy.wav")[0] != "Snare",
          str(nd.detect("SD_Kick_heavy.wav")[0]))
    check("snap no longer claims Clap", nd.detect("Leek Snap.wav")[0] != "Clap",
          str(nd.detect("Leek Snap.wav")[0]))

    print("\n6. cross-check confirms and contradicts correctly")
    good808 = {"sub_energy_ratio":0.6,"decay_seconds":1.8,"harmonic_density":4.0,
               "pitch_drop_cents":320}
    bad808 = {"sub_energy_ratio":0.02,"decay_seconds":0.05,"harmonic_density":40.0,
              "pitch_drop_cents":0}
    check("808 profile confirms an 808-like sound",
          xc.crosscheck("808", good808).verdict == "confirmed")
    check("808 profile contradicts a bright short sound",
          xc.crosscheck("808", bad808).verdict == "contradicted")
    check("unknown class is untestable, not silently confirmed",
          xc.crosscheck("Banjo", good808).verdict == "untestable")
    check("no evidence is untestable, not silently confirmed",
          xc.crosscheck("808", None).verdict == "untestable")

    print("\n7. a high-risk token can never auto-rename alone")
    e = ne.extract("Leek Snap.wav")
    out = xc.combine(e, "Clap", 0.99, good808)
    check("snap + confident audio does NOT auto-rename",
          out["action_hint"] != "auto_rename_eligible", out["action_hint"])

    print("\n8. contradictory audio routes to review")
    e2 = ne.extract("snare_hit_01.wav")
    quiet = {"transient_strength":0.1,"noise_tonal_ratio":0.0,
             "decay_seconds":9.0,"pitch_confidence":0.99,"mid_energy_ratio":0.0}
    out2 = xc.combine(e2, "Snare", 0.9, quiet)
    check("filename+audio agree but physics contradicts -> review",
          out2["action_hint"] == "review", out2["action_hint"])
    check("and confidence is reduced, not raised", out2["confidence_delta"] < 0)

    print("\n9. determinism and robustness")
    check("same input gives the same evidence",
          ne.extract("SNR_01.wav").as_dict() == ne.extract("SNR_01.wav").as_dict())
    for weird in ("", ".wav", "___.wav", "808" * 50 + ".wav", "ünïcødé snr.wav"):
        try:
            ne.extract(weird); okr = True
        except Exception:
            okr = False
        check(f"survives {weird[:22]!r}", okr)

    print()
    if FAILED:
        print(f"{len(FAILED)} FAILED: {FAILED}"); return 1
    print("all name evidence tests passed"); return 0

if __name__ == "__main__":
    raise SystemExit(main())
