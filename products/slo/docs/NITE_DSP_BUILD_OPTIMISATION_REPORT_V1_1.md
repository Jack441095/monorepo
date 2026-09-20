# NITE DSP BUILD OPTIMISATION REPORT V1.1

Date: 2026-08-24  
Scope: JUCE / CMake / Apple Silicon build infrastructure only  
Project: SLO / SmartSampleManager  
Branch: engineering/build-system-optimisation

## Executive summary

The six agreed follow-up actions are complete. The build now has a clear fast
development path, a full qualification path, repeatable measurement tooling,
optional Ninja and ccache profiles, and release-artifact validation.

The largest practical improvement is separating development packaging from
qualification/release packaging. Daily plugin builds no longer run the
expensive Homebrew dependency bundling, `install_name_tool`, and ad-hoc signing
pass. Qualification and release-candidate profiles retain that work.

The deeper JUCE plugin-wrapper restructuring was deliberately not attempted.
The current architecture already consolidates common JUCE implementation code
for tests and ordinary consumers while keeping JUCE's AU/VST3/Standalone
wrapper ownership intact. Removing that final wrapper compilation owner would
require a custom JUCE wrapper architecture and would carry a disproportionate
risk of returning to duplicate symbols or changing plugin initialisation.

No DSP algorithms, audio processing, ML models, classifier behaviour, or
product features were changed.

## What changed

### 1. Development packaging is now separate from release packaging

`SSM_BUNDLE_APPLE_DEPS` is now explicit:

- `ssm-dev`, `ssm-dev-ninja`, and ccache development profiles: `OFF`;
- `ssm-qualification` and `ssm-release-candidate`: `ON`.

Development builds still copy required model/resources into the bundles, but
skip the expensive external dependency rewrite and signing step. The
qualification/release profiles continue to produce self-contained, signed
Apple bundles.

A new aggregate target makes the intended development check concise:

    cmake --build --preset ssm-dev-ninja-ccache \
        --target ssm_plugins --parallel 8

### 2. Ninja profiles were added

New presets:

- `ssm-dev-ninja`
- `ssm-dev-ninja-ccache`

They use Ninja while reusing the canonical dependency source directories. The
Ninja build metadata is isolated from the Unix Makefiles metadata, avoiding
generator collisions while preventing duplicate downloads.

### 3. ccache support was added and measured

`SSM_USE_CCACHE=ON` selects `/opt/homebrew/bin/ccache` as the C and C++
compiler launcher. The configured preset is:

    cmake --preset ssm-dev-ccache

The recommended daily profile is:

    cmake --preset ssm-dev-ninja-ccache

ccache is useful for repeated translation-unit edits and branch switching. It
is not claimed as a clean-build accelerator: the clean ccache run was slightly
slower because the cache was cold and launcher overhead was added.

### 4. Repeatable measurement tooling was added

`scripts/measure_build.py` records:

- configure and build wall time;
- child user/system CPU time;
- peak resident memory;
- compile, link, and Make/Ninja-reported target counts;
- success/failure;
- optional source touch and JSON output.

Raw records are stored under `docs/build_measurements/` for this run.

### 5. Release validation tooling was installed and run

The host now has native Apple Silicon installations of Ninja, ccache, and
pluginval. Qualification validation covered the complete native test set,
licensing integration, plugin formats, bundle contents, architecture,
dependency closure, identity, codesigning, and a standalone launch smoke test.

### 6. JUCE wrapper restructuring was deferred intentionally

The current shared `ssm_juce` static library remains the safe optimisation
boundary for common JUCE modules. Plugin-client wrapper code remains owned by
the JUCE plugin target. This is the right stopping point for V1.1 until a
second product or a measured multi-product JUCE build justifies a dedicated
wrapper layer.

## Build architecture

Before the V1 work, JUCE module implementation sources propagated through
interface targets into many test and application consumers. Shared engine
translation units were also repeated across executable source lists. Apple
plugin builds additionally bundled and signed dependencies during ordinary
development builds.

The current graph is:

    JUCE module targets
        -> explicit common JUCE module source set
        -> ssm_juce STATIC
        -> tests / benchmarks / ordinary consumers

    engine sources
        -> ssm_engine_core_prod OBJECT
        -> production-semantics consumers

    engine sources
        -> ssm_engine_core_test OBJECT
        -> test consumers

    juce_add_plugin(SmartSampleManager)
        -> plugin-client wrapper and plugin-specific JUCE code
        -> AU / VST3 / Standalone targets
        -> ssm_juce and runtime libraries where appropriate

    ssm_plugins
        -> AU + VST3 + Standalone

    ssm_qual_full
        -> all qualification tests + benchmarks + plugin formats

The two engine OBJECT variants are intentional: the production variant
preserves production cache-path semantics, while the test variant retains the
test guard used by the other native tests. The plugin wrapper boundary remains
separate to avoid cross-target JUCE definitions and duplicate implementation
symbols.

## Measurements

All controlled measurements below used the Apple Silicon host, parallel level
8, and the generated JSON records in `docs/build_measurements/`.

| Run | Wall | User CPU | System CPU | Peak RSS | Compile | Link | Result |
|---|---:|---:|---:|---:|---:|---:|---|
| Ninja, no ccache, clean fast regression | 277.3 s | 588.8 s | 77.6 s | 1.70 GB | 64 | 9 | pass |
| Ninja + ccache, clean fast regression | 316.1 s | 637.2 s | 100.1 s | 1.68 GB | 64 | 9 | pass |
| Ninja, no ccache, one test TU + relink | 11.45 s | 7.32 s | 0.94 s | 336 MB | 1 | 1 | pass |
| Ninja + ccache, same one-TU edit + relink | 1.81 s | 1.49 s | 0.45 s | 265 MB | 1 | 1 | pass |
| Ninja + ccache, warm no-op | 0.34 s | 0.16 s | 0.12 s | 10 MB | 0 | 0 | pass |
| Dev plugin aggregate, dependency bundling OFF | 36.81 s | 19.53 s | 5.27 s | 383 MB | 1 | 4 | pass |
| Full Release qualification | 668.7 s | 1473.4 s | 193.8 s | 1.22 GB | 126 | 38 | pass |

The ccache incremental comparison reduced wall time by approximately 84% for
the measured one-translation-unit edit. The clean ccache run was approximately
14% slower than the clean no-cache run, so ccache should be enabled for daily
iteration rather than presented as a clean-build optimisation.

The development plugin result is not an apples-to-apples replacement for the
historical 592.3-second all-plugin run because that historical run included
the full Apple dependency bundling/signing pass and had a different build-tree
state. It does demonstrate the intended development workflow: a wrapper edit
relinks the plugin formats without invoking the packaging pass.

The full qualification build completed in 668.7 seconds and included the
release dependency bundling/signing path. It produced 46 targets successfully.

## Validation results

### Native tests

All 28 qualification native tests passed, including engine, cache, audio
feature, classification, similarity, UI-facing, safety, and persisted-cache
coverage.

### Licensing integration

The local licensing server integration passed activation, Ed25519 signature
verification, persisted reload, revalidation, tampered-signature rejection,
and deactivation. The temporary development signing material used to exercise
the isolated server was removed, and the repository's production public-key
source was restored before the final build-tree rebuild.

### Plugins and bundles

- VST3: pluginval strictness level 5 — pass.
- AU: pluginval strictness level 5 — pass.
- AU: Apple `auval -v aufx AtSm NDSP` — `AU VALIDATION SUCCEEDED`.
- VST3, AU, Standalone: release manifest checks — pass.
- VST3, AU, Standalone: Homebrew dependency closure checks — pass.
- VST3, AU, Standalone: all bundled Mach-O files contain `arm64` — pass.
- VST3, AU, Standalone: identity manifest and deep strict codesign checks — pass.
- Standalone Release executable: launched successfully and remained alive for
  a 10-second smoke run with isolated HOME/cache directories.

The ONNX Runtime messages about some nodes being assigned to CPU are runtime
provider diagnostics, not validation failures.

## Recommended developer workflow

From `products/slo/SmartSampleManager`:

### “I changed one C++ file”

    cmake --preset ssm-dev-ninja-ccache
    cmake --build --preset ssm-dev-ninja-ccache \
        --target TestTaxonomy --parallel 8

Use the smallest relevant test target while iterating. ccache should make
repeated edits and branch switches substantially cheaper.

### “I changed engine/cache/classification code”

    cmake --build --preset ssm-dev-ninja-ccache \
        --target ssm_qual_fast_regression --parallel 8

### “I need to check all plugin formats during development”

    cmake --build --preset ssm-dev-ninja-ccache \
        --target ssm_plugins --parallel 8

This intentionally leaves the bundles in the build tree and skips expensive
release dependency bundling/signing.

### “I need confidence before merging”

    cmake --preset ssm-qualification
    cmake --build --preset ssm-qualification \
        --target ssm_qual_full --parallel 8

This includes all tests, benchmarks, AU, VST3, Standalone, dependency
bundling, and signing.

### “I am preparing a release candidate”

    cmake --preset ssm-release-candidate
    cmake --build --preset ssm-release-candidate \
        --target ssm_qual_full --parallel 8

This restores test LTO in addition to the shipping plugin LTO and keeps the
release packaging path enabled.

### “I need a benchmark record”

    python3 scripts/measure_build.py \
        --preset ssm-dev-ninja-ccache \
        --target TestXmpWriter \
        --touch Source/test_xmp_writer_main.cpp \
        --json ../docs/build_measurements/my-run.json

For a clean comparison, use `--clean-first`. Do not compare runs while another
large build is consuming the same CPU, memory, or external disk.

## Risks and trade-offs

- `ssm_juce` has an explicit reviewed module list. Adding a JUCE module requires
  updating that list and validating all consumers.
- The plugin wrapper still has a separate JUCE implementation owner. This is a
  deliberate safety boundary, not an accidental duplication.
- Debug development and Release qualification intentionally differ in
  optimisation and packaging behaviour.
- ccache consumes disk and is sensitive to compiler flags, headers, SDK,
  architecture, and branch changes. It should be capped and periodically
  cleaned.
- Ninja and Makefiles use separate build metadata. A developer should use the
  matching preset consistently instead of mixing generators in one tree.
- Release dependency bundling remains expensive. It is now kept off the daily
  path, but its separate optimisation is a future release-engineering task.

## Future improvements

1. Profile and reduce the `install_name_tool`/dependency-bundling pass without
   weakening bundle closure or codesign guarantees.
2. Add pluginval and the bundle guards as mandatory CI release gates on a clean
   Apple Silicon runner.
3. Replace deprecated FetchContent population calls after validating pinned,
   relocatable dependency acquisition.
4. Run a narrow unity-build experiment only for small utility/test groups and
   retain it only if incremental invalidation remains acceptable.
5. Revisit a shared JUCE plugin-wrapper layer when a second NITE DSP product
   provides a real multi-product measurement case.

## Success criteria

V1.1 meets the programme objectives:

- JUCE common implementation work is consolidated behind `ssm_juce` for
  ordinary consumers;
- daily builds avoid unnecessary Apple packaging work;
- Ninja and ccache provide a measured fast iteration path;
- development, qualification, and release-candidate profiles are explicit;
- qualification remains reliable across all native tests and plugin formats;
- VST3, AU, standalone, manifest, architecture, dependency, identity, and
  codesign checks pass;
- release packaging remains enabled in qualification/release profiles;
- no DSP, ML, classifier, audio, or product behaviour was changed.
