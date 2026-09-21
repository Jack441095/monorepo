# KENN Phase 4 AutoMix Testing-Assets Receipt

**Run date:** 2026-09-20
**Status:** technical evidence recorded; rights and perceptual gates remain open

The supplied corpus includes the existing full-duration AutoMix validation
summary at:

`/Volumes/Jack_Gandy_1TB_SSD/Nite-DSP/Nite-DSP-Operations/testing-assets/testing_track_stems/_automix_out/VALIDATION_SUMMARY.json`

That summary reports seven completed AutoMix renders with `status: ok`. The
source stem sets cover 15, 18, 19, 22, 44, and 62 WAV stems (the 15/18/19
sets are the WAV variants of the `dream_of_you`, `reggueton_pop`, and
`stranger` projects). This is useful low-, mid-, and high-density evidence,
but it is not an exact 1/8/16/32/64-stem matrix.

| Project | Stems | Render (min) | LUFS | True peak (dBFS) | Correlation | Tech score |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `ae_mere_humsafar` | 22 | 2.9 | -14.02 | -1.05 | 0.948 | 30 |
| `al_james` | 62 | 4.7 | -14.00 | -1.92 | 0.781 | 20 |
| `amyhelmandthehandsomestrangers_rescueme` | 18 | 12.8 | -14.01 | -1.61 | 0.995 | 20 |
| `angeloboltini_fragments` | 62 | 4.7 | -14.01 | -1.38 | 0.895 | 25 |
| `atlantisbound_itwasmyfaultforwaiting` | 44 | 3.5 | -14.00 | -1.30 | 0.936 | 30 |
| `dream_of_you` | 15 | 1.2 | -14.00 | -1.15 | 0.866 | 15 |
| `reggueton_pop` | 18 | 3.2 | -14.00 | -1.26 | 0.996 | 5 |

## Interpretation

- The existing summary is strong objective pipeline evidence: all seven
  renders completed, loudness is clustered around -14 LUFS, and true peaks
  remain below -1 dBFS.
- The corpus provides real multitrack workload diversity, but it does not
  prove the requested exact stem-count matrix. A follow-up should create or
  obtain rights-cleared 64-stem input and rerun the complete AutoMix request
  for each count. A deterministic no-copy selection manifest now prepares
  1/8/16/32-stem subsets from `al_james`:
  `results/phase4_testing_assets_stem_matrix.json`. Selection is not render
  evidence until the complete AutoMix request is run for each subset; the
  manifest currently verifies all 32 selected source-file hashes.
- The summary is an existing asset receipt; this turn did not rerender the
  seven long projects. Perceptual listening, host validation, and memory
  behavior under the exact matrix remain open.
- `manifest.json` marks the source license as `TODO-vendor-pack`. These files
  are therefore internal engineering evidence only and must not be copied to
  a release archive or used for a rights-cleared benchmark claim.

## Exact-count render evidence

The deterministic `al_james` subsets were run through the preserved full
AutoMix entry point using symlinks to the external WAVs (no audio copied into
the repository). All four complete requests passed the safety gate, while the
advisory technical score remained below the configured 65-point threshold:

| Stems | LUFS | True peak (dBTP) | Correlation | Technical score | Safety |
| ---: | ---: | ---: | ---: | ---: | --- |
| 1 | -14.69 | -1.30 | 1.000 | 55 | pass; advisory fail |
| 8 | -13.97 | -1.27 | 0.833 | 20 | pass; advisory fail |
| 16 | -14.03 | -1.15 | 0.847 | 25 | pass; advisory fail |
| 32 | -14.02 | -1.94 | 0.366 | 30 | pass; advisory fail |

The machine-readable output hashes and gate details are in
`results/phase4_testing_assets_automix_matrix_renders.json`. The 64-stem case
is still unavailable because the largest supplied WAV set contains 62 stems.
The low scores and uncompleted perceptual review mean these renders do not
clear an AutoMix quality or release gate.

## Qualification decision

The AutoMix evidence supports continuing the C++ investigation and keeps the
native spectral path useful as an opt-in parity candidate. It does not clear
the release gate: the full-mix native/reference comparison on the same
testing-assets mixdowns averaged `0.98962x`, and the exact stem-count,
perceptual, rights, Windows-host, and signing gates are still outstanding.
