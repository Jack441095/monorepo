# SmartSampleManager — Commercial Scope Freeze

Phase 1, Section 1 of `prompts/Website_commercial_samplemanager.txt`. Defines exactly what is and is not part of the SmartSampleManager commercialisation effort, at the source-file level. Supersedes nothing in `docs/SAMPLE_MANAGER_SCOPE_AUDIT.md` (repo-root Phase 0 doc) — this is the finer-grained, project-local version.

## IN SCOPE

```text
SmartSampleManager/Source/                     all C++ source (engine, licensing, UI, taxonomy, XMP writer)
SmartSampleManager/Source/Licensing/           licensing client (LicenseManager.cpp/.h, LicenseTypes.h,
                                                LicensePublicKey.h)
SmartSampleManager/Models/                     panns_cnn10_embedding.onnx + provenance docs
SmartSampleManager/Resources/                  app icon and bundled resources
SmartSampleManager/CMakeLists.txt              build configuration
SmartSampleManager/Source/test_*.cpp           regression test suite (9 targets)
SmartSampleManager/licensing_server/           dev/test licensing backend — in scope as the basis for a
                                                future production backend, NOT as production infrastructure
                                                itself (see docs/LICENSING_PRODUCTION_GAP.md)
SmartSampleManager/model_export/               ONNX export tooling for the shipped model
Audio_Too/.github/workflows/smart-sample-manager.yml   CI
SmartSampleManager/docs/                       this audit's deliverables

FUTURE (not yet built, in scope when built):
    SmartSampleManager installer (macOS/Windows)
    SmartSampleManager production commercial backend (payments, entitlements, accounts)
    SmartSampleManager website integration
```

## OUT OF SCOPE — do not modify, package, market, or expose

```text
Audio_Too/studio/kenn/                              KENN
Audio_Too/studio/vst3_plugins/KENNMixAssistant/     KENN Mix Assistant plugin
Audio_Too/thursday/                                 Thursday
Audio_Too/studio/audiogen/                          AutoMix / AudioGen
Audio_Too/studio/vst3_plugins/MidiGenerator/        MIDI Generator plugin
Audio_Too/studio/stem_separation/                   stem separation
Audio_Too/studio/vst3_plugins/AudioToo_Reverb/      other AudioToo plugin
Audio_Too/studio/vst3_plugins/AudioToo_Limiter/     other AudioToo plugin
Audio_Too/studio/audio_analysis/                    shared DSP kernels (used by Reverb/Limiter, not by
                                                     SmartSampleManager — no dependency exists to protect)
Audio_Too/business/agents/                          Marketing/Admin/Research/MetaAgent/CodingAgent
Audio_Too/business/app/ (all routes except the      general website/business backend — the
    smart_sample_manager_bridge.py status check)     smart_sample_manager_bridge.py file itself is a thin
                                                     status-check touchpoint and may be extended later for
                                                     real entitlement checks, but the rest of business/app/
                                                     is out of scope
Audio_Too/sample_pack_testing/                      unrelated
Coding_LLM/, Fast_Onion_Browser/, studio/kenn/       (repo root) — unrelated top-level projects
prompts/sampler_master_prompt.txt                   unbuilt, name-adjacent "resampling instrument" concept —
                                                     not source code, not this product
```

## Boundary notes

- `SmartSampleManager` does not `#include` or link against any file under `vst3_plugins/common/` or `audio_analysis/` — verified by grep in Phase 0. There is no dependency relationship to protect there; it is purely absent.
- The umbrella `Audio_Too/studio/vst3_plugins/CMakeLists.txt` lists SmartSampleManager as one `add_subdirectory()` among sibling plugin targets. This file is shared infrastructure — it may be read, but any release-pipeline change should build the SmartSampleManager subdirectory directly rather than editing the umbrella file, per §F of the Phase 0 audit.
- `Audio_Too/pyproject.toml`, the repo-wide `.venv`, `Dockerfile`, and `docker-compose.yml` are shared across every project in the monorepo. They are read-only context for this audit, not something to fork or modify for SmartSampleManager alone.

## Change-safety gate (carried forward from Phase 0)

Every change proposed during this phase must be one of: `SAMPLE MANAGER CORE CHANGE`, `SAMPLE MANAGER COMMERCIAL INFRASTRUCTURE`, `BUILD/RELEASE`, `WEBSITE`, `SECURITY`, `TESTING`. If it doesn't fit, it doesn't belong in this phase.
