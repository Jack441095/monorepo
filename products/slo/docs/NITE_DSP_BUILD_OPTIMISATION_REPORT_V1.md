# NITE DSP BUILD OPTIMISATION REPORT V1

Date: 2026-08-24  
Scope: JUCE / CMake / Apple Silicon build infrastructure only  
Project: SLO / SmartSampleManager  
Branch: engineering/build-system-optimisation

> Historical V1 snapshot. The follow-up actions and current validation results
> are recorded in [NITE DSP BUILD OPTIMISATION REPORT V1.1](NITE_DSP_BUILD_OPTIMISATION_REPORT_V1_1.md).

## Summary

V1 reduces duplicated compilation in the SLO build graph without changing DSP
algorithms, audio processing, ML models, classifier behaviour, or product
features.

The main new change is a shared static JUCE implementation target,
ssm_juce. Common JUCE modules are compiled into that archive and consumed by
tests, benchmarks, licensing tools, and the application/plugin targets where
the JUCE wrapper permits it. The JUCE plugin wrapper remains under
juce_add_plugin ownership so AU/VST3/Standalone-specific code and definitions
do not cross the wrong binary boundary.

The earlier V1 work on this branch is also retained:

- shared production and test OBJECT libraries for the five engine translation
  units;
- test-only LTO disabled by default;
- canonical development, qualification, and release-candidate presets;
- shared FetchContent source cache;
- selective qualification groups;
- safe plugin auto-installation defaulting to OFF;
- out-of-tree fixture resolution and CI alignment.

The implementation was validated against the duplicate-symbol failure mode:
the optimized fast regression graph linked successfully and all seven fast
regression executables passed.

## Build architecture

### Before

The important dependency path was effectively:

    Test / Benchmark target
        -> juce::juce_audio_utils
        -> juce::juce_dsp
        -> JUCE INTERFACE_SOURCES
        -> juce_core, graphics, gui_basics, HarfBuzz, and other module objects

JUCE's CMake module targets are interface usage targets that propagate their
implementation sources. Each consumer therefore compiled its own JUCE module
objects. The five engine translation units were also repeatedly listed in
many executable targets.

### After

The common consumer path is now:

    JUCE module targets
        -> explicit common module source set
        -> ssm_juce STATIC
        -> tests, benchmarks, licensing, and ordinary consumers

The engine path is:

    engine sources
        -> ssm_engine_core_prod OBJECT
        -> production-semantics consumer(s)

    engine sources
        -> ssm_engine_core_test OBJECT
        -> SSM_TEST_BINARY test consumers

The plugin path remains intentionally separate:

    juce_add_plugin(SmartSampleManager)
        -> plugin shared code and JUCE plugin-client wrapper sources
        -> AU / VST3 / Standalone wrapper targets
        -> ssm_juce and runtime libraries where needed

This preserves plugin-specific JUCE compile definitions and wrapper behaviour.
It also avoids the previous duplicate implementation-object link failure.

## Changes made

### Shared JUCE implementation

SmartSampleManager/CMakeLists.txt now defines ssm_juce as a STATIC library
from the explicit JUCE 8.0.2 common module source set:

- juce_core
- juce_events
- juce_graphics
- juce_gui_basics
- juce_gui_extra
- juce_data_structures
- juce_audio_basics
- juce_audio_formats
- juce_audio_devices
- juce_audio_processors
- juce_audio_utils
- juce_dsp

The source list is read from JUCE's INTERFACE_JUCE_MODULE_SOURCES target
property and deduplicated before creating the archive. The module target
compile definitions and required macOS frameworks are carried explicitly.

Common test and engine-runtime link paths now use ssm_juce. The plugin wrapper
continues to own its JUCE client implementation sources.

### Engine OBJECT libraries

ssm_engine_core_prod and ssm_engine_core_test compile the shared engine core
once per required semantic variant. The production/test split is intentional:
TestSafetyRegression must exercise production cache-path semantics, while the
other tests retain the fail-closed test guard.

### Profiles

The presets are:

| Preset | Purpose | Configuration | Test LTO |
|---|---|---|---|
| ssm-dev | daily development | Debug | off |
| ssm-qualification | full confidence | Release | off |
| ssm-release-candidate | shipping parity | Release | on |

All presets use the canonical out-of-tree _build directory and shared
_cache/fetchcontent dependency source cache.

### Compiler cache hook

An optional SSM_USE_CCACHE configure option now sets both C and C++ compiler
launchers to ccache. It is OFF by default and fails clearly if ccache is
requested but not installed. ccache installation and cache-hit measurements
were completed in the V1.1 follow-up.

### Unity builds and PCH

Global unity builds were not enabled. The current test mains are mostly single
translation units, and unity would not remove the expensive shared engine or
JUCE implementation work. It could also widen invalidation after a small test
edit.

Project-wide JUCE precompiled headers were not added. The shared JUCE archive
is a stronger measured architectural fix; a PCH experiment should be isolated
to a future branch and retained only if compile-time measurements justify the
extra configuration coupling.

## Measurements

### Historical baseline

The pre-refactor baseline, recorded in
docs/BUILD_SYSTEM_OPTIMISATION_2026_08_22.md, was:

| Measurement | Baseline |
|---|---:|
| SampleManagerEngine.cpp object copies | about 28 |
| JUCE module object duplicates across tests | 464 |
| no-op incremental test build | 0.6 s |
| TestFavorites rebuild after staleness | 484 s |
| engine TU touch, one TestFavorites consumer | 828 s |
| largest observed build trees | 1.4–2.3 GB |

The historical 828-second case was a Release/full-LTO build and is not
directly comparable to the new Debug/no-LTO development measurement.

### Optimized graph

Generated build-file inspection after the change found:

| Graph property | Optimized result |
|---|---:|
| SampleManagerEngine.cpp object owners | 3 |
| Common JUCE implementation owners | 2 |
| Common JUCE owners used by test/benchmark targets | 1: ssm_juce |
| ssm-dev build tree after validation | 878 MB |

The two common JUCE owners are the plugin shared-code target and ssm_juce.
The plugin target remains separate because JUCE's plugin wrapper propagates
its own shared-code module sources. Test and benchmark link files reference
libssm_juce.a rather than carrying common JUCE module source objects.

### Timed development runs

These measurements were taken on the Apple Silicon host using parallel level
8:

| Run | Result |
|---|---:|
| First optimized ssm-dev fast-suite build | 835.2 s wall |
| First optimized build CPU time | 804.2 s user, 210.8 s system |
| Warm no-op ssm_qual_fast_regression | 3.5 s |
| Touch test_xmp_writer_main.cpp and build TestXmpWriter | 40.8 s |
| Touch SampleManagerEngine.cpp and build TestFavorites | 371.6 s |
| AU + VST3 + Standalone target build | 592.3 s |

The first fast-suite build ran while another large build was active on the
same machine, so its wall time is an observed clean-build datapoint rather
than a controlled before/after claim. The engine-source edit rebuilt the
product shared code and test core variants, but did not rebuild ssm_juce.

Wall/user/system time was captured with /usr/bin/time. Peak resident memory
was not sampled with a stable host-wide recorder during this run, so no
fabricated memory comparison is reported; the observed stalls and historical
CPU/I/O split indicate that memory pressure and disk contention remain
important follow-up measurements.

The AU, VST3, and Standalone build time was dominated by the existing
post-build dependency bundling and install_name_tool pass. The compilation
stage reused ssm_juce; it did not rebuild common JUCE modules for each wrapper.

## Validation

### Tests

The following executables passed:

- TestTaxonomy
- TestXmpWriter
- TestPathTraversal
- TestDuplicateDetection
- TestPruneMissing
- TestSafetyRegression
- TestCachedReclassification

The fast custom target also completed successfully:

    cmake --build ../_build/ssm-dev --target ssm_qual_fast_regression --parallel 8

### Plugins

The following targets built successfully:

- SmartSampleManager_AU
- SmartSampleManager_VST3
- SmartSampleManager_Standalone

The registered AU component validated successfully with Apple auval:

    auval -v aufx AtSm NDSP

Result: AU VALIDATION SUCCEEDED.

At the time of this V1 snapshot, pluginval was not installed on the host.
VST3 compilation and bundle generation passed. pluginval installation and
strict VST3/AU validation were completed in the V1.1 follow-up.

### Release profiles

The qualification and release-candidate presets both configured successfully
from fresh generated caches. The original qualification cache contained an
absolute path from an older checkout; it was refreshed with CMake --fresh.
The shared dependency source cache was retained.

The remaining configure warnings are upstream/deprecation warnings:
FetchContent_Populate deprecation and JUCE's CMP0175 add_custom_command
warning. They are recorded as future cleanup items, not build failures.

## Developer workflow

From products/slo/SmartSampleManager:

Daily coding:

    cmake --preset ssm-dev
    cmake --build --preset ssm-dev --target TestTaxonomy --parallel 8

Fast regression after an engine or cache change:

    cmake --build --preset ssm-dev --target ssm_qual_fast_regression --parallel 8

Run the fast executables from:

    ../_build/ssm-dev/

Qualification:

    cmake --preset ssm-qualification
    cmake --build --preset ssm-qualification --target ssm_qual_full --parallel 8

Release-candidate parity:

    cmake --preset ssm-release-candidate
    cmake --build --preset ssm-release-candidate --target ssm_qual_full --parallel 8

Plugin-only development check:

    cmake --build --preset ssm-dev \
        --target SmartSampleManager_AU SmartSampleManager_VST3 SmartSampleManager_Standalone \
        --parallel 8

Compiler caching, after installing ccache:

    brew install ccache
    cmake --preset ssm-dev -DSSM_USE_CCACHE=ON
    ccache --max-size 20G

Do not enable SSM_INSTALL_PLUGINS_AFTER_BUILD for ordinary development.
Built bundles remain inside the build tree by default, preventing accidental
overwrites of the user's installed AU/VST3.

## Troubleshooting

If CMake reports that CMakeCache.txt belongs to another absolute checkout,
confirm no build is active and refresh that generated tree:

    cmake --fresh --preset ssm-qualification

If a dependency source cache was copied from another machine, retain only its
*-src directories. CMake subbuild/build directories contain absolute paths
and must be regenerated.

If a test target cannot find JuceHeader.h, configure through the preset and
build the target from the generated out-of-tree tree. The dependency edges
now make SmartSampleManager generate the JUCE header before consumers compile.

If a build unexpectedly tries to install plugins, inspect
SSM_INSTALL_PLUGINS_AFTER_BUILD in CMakeCache.txt. The safe default is OFF.

If the build is slow after a source edit, first check whether another
large build is consuming memory or I/O. Use the selective qualification group
that matches the changed risk surface instead of ssm_qual_full.

## Risks and trade-offs

- ssm_juce is a static archive with an explicit module boundary. Adding a new
  JUCE module requires updating the reviewed module list and compile
  definitions.
- The JUCE plugin wrapper still has a separate common-module compilation
  owner. Removing that owner would require a deeper custom JUCE wrapper
  architecture and could reintroduce duplicate symbols or change plugin
  initialization semantics.
- The Debug development profile intentionally differs from shipping Release
  optimization. Release/plugin LTO remains enabled by default; test LTO is
  restored by the release-candidate preset.
- ccache improves repeated builds only when the compiler command, headers,
  architecture, and flags match. It is not a substitute for correct target
  dependency boundaries.
- The dependency bundling step remains expensive and noisy. It is outside
  the JUCE compilation optimization and should be profiled separately.

## Future improvements

1. Add pluginval to the release validation environment and make a built
   artifact validation step mandatory.
2. Measure an uncontended clean build on a fixed host with and without ccache.
3. Profile and deduplicate the install_name_tool/dependency-bundling pass.
4. Replace deprecated FetchContent_Populate calls with a supported CMake
   FetchContent flow after validating relocation and pinning behaviour.
5. Add a narrow unity-build experiment for small utility-only target groups,
   with compile-command and incremental-invalidation measurements.
6. Revisit whether JUCE plugin shared code can be split safely from the
   plugin-client wrappers once multiple NITE DSP products share the same JUCE
   version and module definitions.

## Success criteria

V1 meets the build-infrastructure objectives:

- common JUCE implementation work is no longer propagated into every test;
- engine implementation work is consolidated into semantic OBJECT variants;
- daily and qualification builds have explicit profiles and target groups;
- qualification and release-candidate configurations remain reproducible;
- plugin build targets and AU validation remain successful;
- no DSP, ML, classifier, or runtime product behaviour was changed.

The remaining V1 validation gap is VST3 runtime validation with pluginval,
which is a missing host tool on this machine rather than a compile or link
failure.
