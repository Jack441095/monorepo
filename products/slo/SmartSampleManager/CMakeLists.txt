cmake_minimum_required(VERSION 3.22)
project(SmartSampleManager VERSION 1.0.0 LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Optional compiler-result caching for local development and CI runners that
# retain a cache between jobs. Keep this opt-in: a missing cache tool should
# fail at configure time rather than silently changing the compiler command
# for every developer. The default build remains toolchain-only and fully
# reproducible.
option(SSM_USE_CCACHE
       "Use ccache as the C/C++ compiler launcher when it is installed" OFF)
if(SSM_USE_CCACHE)
    find_program(SSM_CCACHE_PROGRAM ccache
        HINTS /opt/homebrew/bin /usr/local/bin
        REQUIRED)
    set(CMAKE_C_COMPILER_LAUNCHER "${SSM_CCACHE_PROGRAM}" CACHE FILEPATH
        "C compiler launcher selected by SSM_USE_CCACHE")
    set(CMAKE_CXX_COMPILER_LAUNCHER "${SSM_CCACHE_PROGRAM}" CACHE FILEPATH
        "C++ compiler launcher selected by SSM_USE_CCACHE")
    message(STATUS "SmartSampleManager: ccache enabled via ${SSM_CCACHE_PROGRAM}")
endif()

# --- RECOVERY PHASE R1 -- early arm64/Homebrew-prefix architecture preflight
# (see docs/SLO_LOST_WORK_RECOVERY_MANIFEST.md, brief section 33). Real,
# previously-diagnosed defect: this machine has BOTH an x86_64 Homebrew
# install at /usr/local (Rosetta `cmake` itself lives there -- `which cmake`
# resolves to /usr/local/bin/cmake because /usr/local/bin precedes
# /opt/homebrew/bin on PATH) AND a native arm64 Homebrew install at
# /opt/homebrew, each with its own copies of TagLib/ONNX Runtime/libsodium
# (and ONNX Runtime's own transitive deps: abseil/protobuf/re2). Every
# find_path/find_library call below historically listed
# "/usr/local/... /opt/homebrew/..." in that order, so a clean arm64 configure
# would silently resolve to the WRONG (x86_64) copies -- CMake's find_*
# returns the first PATHS entry that matches, regardless of host/target
# architecture -- and the build would only fail ~14 minutes later at link
# time, with no earlier signal. scripts/check_homebrew_dependencies.py did
# not catch this either (it treats /usr/local/lib as legitimate without
# checking arch).
#
# Fix, in order:
#  1. This project ships arm64-only (see brief section 34 -- do NOT expand to
#     Universal 2 as part of this fix). Pin CMAKE_OSX_ARCHITECTURES to arm64
#     up front if the caller didn't already set it, so there's no ambiguity
#     about what we're even resolving dependencies for.
#  2. Below, every dependency PATHS list is reordered /opt/homebrew before
#     /usr/local (arm64-first) instead of the old x86_64-first order.
#  3. ssm_verify_dylib_arch() actually inspects the resolved binary's Mach-O
#     architecture (via `file`) right after each find_library() call and
#     FATAL_ERRORs immediately -- at configure time, not 14 minutes into a
#     build -- if a resolved library doesn't contain the arm64 slice.
if(APPLE AND NOT CMAKE_OSX_ARCHITECTURES)
    set(CMAKE_OSX_ARCHITECTURES "arm64" CACHE STRING "SLO ships arm64-only; see architecture preflight above" FORCE)
endif()

function(ssm_verify_dylib_arch libPath libLabel)
    if(NOT APPLE OR NOT CMAKE_OSX_ARCHITECTURES STREQUAL "arm64")
        return()
    endif()
    if(NOT libPath OR NOT EXISTS "${libPath}")
        return() # find_library already emits its own not-found error; nothing new to say here
    endif()
    execute_process(
        COMMAND file "${libPath}"
        OUTPUT_VARIABLE _ssmFileOutput
        OUTPUT_STRIP_TRAILING_WHITESPACE
    )
    string(TOLOWER "${_ssmFileOutput}" _ssmFileOutputLower)
    if(NOT _ssmFileOutputLower MATCHES "arm64")
        message(FATAL_ERROR
            "Architecture preflight FAILED for ${libLabel}: resolved to '${libPath}', "
            "which is not an arm64 binary (`file` reported: ${_ssmFileOutput}). This is "
            "almost always the x86_64 Homebrew prefix (/usr/local) shadowing the arm64 one "
            "(/opt/homebrew) -- see the architecture preflight comment near the top of "
            "this file. Re-run cmake with a clean build directory after confirming "
            "`brew --prefix ${libLabel}` (run under /opt/homebrew/bin/brew, not /usr/local/bin/brew) "
            "points at /opt/homebrew.")
    endif()
endfunction()

# Check if JUCE target exists, if not, fetch it
if(NOT TARGET juce::juce_audio_utils)
    include(FetchContent)
    FetchContent_Declare(
        JUCE
        GIT_REPOSITORY https://github.com/juce-framework/JUCE.git
        GIT_TAG 8.0.2
    )
    FetchContent_MakeAvailable(JUCE)
endif()

# Fetch umappp
include(FetchContent)
set(UMAPPP_FETCH_EXTERN ON CACHE BOOL "" FORCE)
FetchContent_Declare(
    umappp
    GIT_REPOSITORY https://github.com/libscran/umappp
    GIT_TAG v3.3.2
)
FetchContent_MakeAvailable(umappp)

# Fetch dr_wav (single-header WAV decoder). This repo has no CMakeLists.txt of its
# own, so we use FetchContent_Populate (not MakeAvailable) to just grab the source
# and add its directory to our include path, rather than add_subdirectory-ing it.
# Pinned to the wav-specific release tag (dr_libs tags per-format, not
# per-repo) rather than `master`, so every fresh checkout/CI run gets the
# same dr_wav.h instead of silently picking up whatever upstream has moved
# to since -- a reproducibility/supply-chain concern, not a license one.
FetchContent_Declare(
    dr_libs
    GIT_REPOSITORY https://github.com/mackron/dr_libs.git
    GIT_TAG wav-0.14.5
)
FetchContent_Populate(dr_libs)

# Fetch hnswlib (header-only approximate nearest-neighbor library), used for
# incremental UMAP out-of-sample placement of new samples. Also header-only with
# no build system dependency we need, so just populate the source like dr_libs.
FetchContent_Declare(
    hnswlib
    GIT_REPOSITORY https://github.com/nmslib/hnswlib.git
    GIT_TAG v0.8.0
)
FetchContent_Populate(hnswlib)

# Find TagLib -- arm64 Homebrew prefix (/opt/homebrew) listed first; see the
# architecture preflight comment near the top of this file.
find_path(TAGLIB_INCLUDE_DIR NAMES tag.h PATH_SUFFIXES taglib PATHS /opt/homebrew/include /usr/local/include NO_DEFAULT_PATH)
find_library(TAGLIB_LIBRARY NAMES tag PATHS /opt/homebrew/lib /usr/local/lib NO_DEFAULT_PATH)

# Find ONNX Runtime (look for C++ API header)
find_path(ONNXRUNTIME_INCLUDE_DIR NAMES onnxruntime_cxx_api.h PATH_SUFFIXES onnxruntime PATHS /opt/homebrew/include /usr/local/include NO_DEFAULT_PATH)
find_library(ONNXRUNTIME_LIBRARY NAMES onnxruntime PATHS /opt/homebrew/lib /usr/local/lib NO_DEFAULT_PATH)

if(NOT TAGLIB_INCLUDE_DIR OR NOT TAGLIB_LIBRARY)
    message(FATAL_ERROR "TagLib not found! Please run 'brew install taglib'")
endif()
ssm_verify_dylib_arch("${TAGLIB_LIBRARY}" "taglib")

# The sources include TagLib in the prefixed form -- <taglib/wavfile.h>,
# <taglib/id3v2tag.h>, <taglib/textidentificationframe.h> -- but the
# find_path() above uses PATH_SUFFIXES taglib, so it resolves to the directory
# CONTAINING tag.h, i.e. <prefix>/include/taglib. That satisfies <tag.h> but
# can never satisfy <taglib/...>; the PARENT directory has to be on the include
# path as well. Carry both, at this single point, so every target that lists
# ${TAGLIB_INCLUDE_DIR} gets a correct include path without 30 call sites
# having to know about it.
#
# Until now this was masked by two separate accidents rather than being right:
#   * The plugin target also lists ${SODIUM_INCLUDE_DIR}, which IS
#     <prefix>/include, so it happened to pick the parent up from libsodium.
#     The Test*/Benchmark* targets do not link libsodium and so had no such
#     luck.
#   * On a dev machine that also has the x86_64 Homebrew at /usr/local, the
#     headers resolve through /usr/local/include, which is in the compiler's
#     DEFAULT search path -- so the build succeeds locally while being wrong.
# Neither holds on a clean arm64-only CI runner, where this surfaced as
# "fatal error: 'taglib/wavfile.h' file not found" building TestSampleEngine
# after all three plugin formats had already linked successfully.
get_filename_component(TAGLIB_INCLUDE_PARENT_DIR "${TAGLIB_INCLUDE_DIR}" DIRECTORY)
set(TAGLIB_INCLUDE_DIR "${TAGLIB_INCLUDE_DIR}" "${TAGLIB_INCLUDE_PARENT_DIR}")

if(NOT ONNXRUNTIME_INCLUDE_DIR OR NOT ONNXRUNTIME_LIBRARY)
    message(FATAL_ERROR "ONNX Runtime not found! Please run 'brew install onnxruntime'")
endif()
ssm_verify_dylib_arch("${ONNXRUNTIME_LIBRARY}" "onnxruntime")

# Apple's Accelerate framework (vDSP) is used to vectorize DSP hot paths (windowing,
# mel filterbank dot products) on macOS builds. VectorMath.cpp has a portable
# scalar-loop fallback for non-Apple platforms (see #if defined(__APPLE__) there),
# so this dependency is Apple-only by design, not a temporary gap.
if(APPLE)
    find_library(ACCELERATE_FRAMEWORK Accelerate REQUIRED)
endif()

# sqlite3: on macOS this resolves implicitly (Xcode/Command Line Tools ship
# sqlite3.h in the default SDK sysroot, and the linker finds the system
# libsqlite3 via the dyld shared cache even though no .dylib is visible on
# disk) -- that's macOS-specific behavior with no equivalent on Windows,
# where there's no system-provided sqlite3 at all. Explicit lookup, with a
# clear error pointing at vcpkg, rather than a silent/cryptic link failure.
# NOT verified on an actual Windows build (no Windows machine available in
# this environment) -- this is a best-effort fix for a real gap, not a
# tested one.
if(NOT APPLE)
    find_path(SQLITE3_INCLUDE_DIR NAMES sqlite3.h)
    find_library(SQLITE3_LIBRARY NAMES sqlite3)
    if(NOT SQLITE3_INCLUDE_DIR OR NOT SQLITE3_LIBRARY)
        message(FATAL_ERROR "sqlite3 not found! On Windows, install via vcpkg: "
            "vcpkg install sqlite3, and configure with "
            "-DCMAKE_TOOLCHAIN_FILE=<vcpkg_root>/scripts/buildsystems/vcpkg.cmake")
    endif()
    set(SQLITE3_LINK_TARGET ${SQLITE3_LIBRARY})
else()
    set(SQLITE3_LINK_TARGET sqlite3)
endif()

# Find libsodium (Ed25519 sign/verify for the licensing client -- see
# Source/Licensing/). Only signature *verification* happens on the client;
# the signing key itself lives on the licensing server, not here.
find_path(SODIUM_INCLUDE_DIR NAMES sodium.h PATHS /opt/homebrew/include /usr/local/include NO_DEFAULT_PATH)
find_library(SODIUM_LIBRARY NAMES sodium PATHS /opt/homebrew/lib /usr/local/lib NO_DEFAULT_PATH)
if(NOT SODIUM_INCLUDE_DIR OR NOT SODIUM_LIBRARY)
    message(FATAL_ERROR "libsodium not found! Please run 'brew install libsodium'")
endif()
ssm_verify_dylib_arch("${SODIUM_LIBRARY}" "libsodium")

# Identity approved by Jack, Phase 5.5. Applies docs/NITE_DSP_PRODUCT_IDENTITY.md's Phase 3
# proposal exactly -- see docs/FINAL_PRODUCT_IDENTITY.md for the decision record. PLUGIN_CODE
# stays "AtSm" (unchanged, identifies the product not the company -- see that doc's rationale).
# COMPANY_WEBSITE/COMPANY_EMAIL added Phase 5.6, once the real domain/email were supplied
# (docs/DOMAIN_CONFIGURATION.md / docs/EMAIL_CONFIGURATION.md) -- both are cosmetic plugin
# metadata only, no host-compatibility risk (see the original proposal's RISK column).
# Plugin auto-installation is OPT-IN, and deliberately defaults to OFF.
#
# JUCE's COPY_PLUGIN_AFTER_BUILD adds a POST_BUILD step that copies the built
# AU/VST3 into the user's LIVE plugin folders:
#
#     ~/Library/Audio/Plug-Ins/Components/SLO.component
#     ~/Library/Audio/Plug-Ins/VST3/SLO.vst3
#
# This used to be unconditionally TRUE, which meant that ANY build of this
# project -- CI, a scratch out-of-tree build, an automated agent's build, a
# one-off `cmake --build` to check something compiles -- silently overwrote
# whatever the user actually had installed. Building in an isolated build
# directory was NOT sufficient protection, because this step writes outside
# the build tree by design.
#
# That is not hypothetical: on 2026-08-21 an out-of-tree qualification build
# overwrote the owner's installed AU and VST3 with incomplete intermediates.
# JUCE's copy runs BEFORE this file's later POST_BUILD steps (the model copy
# and scripts/bundle_apple_deps.py), so what landed in the live plugin folders
# had no Contents/Frameworks/, no ONNX model in Resources/, and load commands
# still pointing at absolute /opt/homebrew paths instead of @rpath. The
# installed plugins were left in a degraded state and the previous binaries,
# having been overwritten in place, were unrecoverable.
#
# Defaulting to OFF makes the safe path the one that requires no knowledge.
# Installing is still easy, but must now be asked for explicitly:
#
#     cmake -S . -B build -DSSM_INSTALL_PLUGINS_AFTER_BUILD=ON
#
# Do NOT change this default back to ON. See the configure-time status
# message below and the guard in scripts/verify_no_auto_install.py, which
# exists to stop exactly that regression.
option(SSM_INSTALL_PLUGINS_AFTER_BUILD
       "Copy built AU/VST3 into the user's plugin folders after building" OFF)

option(SSM_BUNDLE_APPLE_DEPS
       "Bundle Homebrew runtime dependencies and ad-hoc sign Apple bundles after building" OFF)
set(SSM_BUNDLE_REWRITE_JOBS 8 CACHE STRING
    "Parallel install_name_tool workers used by Apple dependency bundling")

if(SSM_INSTALL_PLUGINS_AFTER_BUILD)
    message(STATUS
        "SmartSampleManager: plugin auto-installation is ENABLED -- this build WILL overwrite "
        "the AU/VST3 in ~/Library/Audio/Plug-Ins/. Unset SSM_INSTALL_PLUGINS_AFTER_BUILD to disable.")
else()
    message(STATUS
        "SmartSampleManager: plugin auto-installation is DISABLED (default) -- built plugins stay "
        "inside the build directory. Pass -DSSM_INSTALL_PLUGINS_AFTER_BUILD=ON to install them.")
endif()

if(APPLE AND SSM_BUNDLE_APPLE_DEPS)
    message(STATUS
        "SmartSampleManager: Apple dependency bundling is ENABLED -- plugin builds will run "
        "bundle_apple_deps.py and ad-hoc signing.")
elseif(APPLE)
    message(STATUS
        "SmartSampleManager: Apple dependency bundling is DISABLED -- development plugin builds "
        "skip the expensive install_name_tool/signing pass.")
endif()

# --- BUILD-SYSTEM OPTIMISATION (2026-08-22): LTO tier policy ---------------
#
# juce::juce_recommended_lto_flags applies FULL -flto (not ThinLTO) on
# AppleClang for $<CONFIG:Release>, at both compile AND link time. Historically
# every target in this file -- including all ~25 Test*/Benchmark* executables,
# which per docs/RELEASE_MANIFEST.md are "CI/dev tooling only" and never ship --
# inherited those flags, making a Release test iteration pay full-LTO cost on
# ~15 JUCE module TUs + the engine TU per binary (measured: 828 s wall to
# rebuild ONE test target after an engine edit; I/O/memory-bound, not CPU).
#
# Tier policy:
#   FAST DEV          Debug tree, no LTO anywhere (CMake default).
#   QUALIFICATION     Release tree. Shipped plugin formats keep LTO (this is
#                     the configuration that reaches customers, so LTO-sensitive
#                     link problems still surface). Test*/Benchmark* binaries
#                     skip LTO by default -- they are never shipped, so LTO
#                     buys zero qualification confidence there.
#   RELEASE CANDIDATE Release tree with -DSSM_TEST_LTO=ON: restores historical
#                     behaviour where tests are optimised identically to the
#                     product, for final parity runs.
# The shipped plugin's flags are unchanged unless SSM_ENABLE_LTO=OFF is passed
# explicitly; RC qualification is NOT weakened.
option(SSM_ENABLE_LTO
       "Apply JUCE recommended LTO flags to the shipped plugin formats" ON)
option(SSM_TEST_LTO
       "Apply JUCE recommended LTO flags to Test*/Benchmark* executables too (release-candidate parity tier)" OFF)

# --- Dev-only sanitizers (SSM_SANITIZE) -------------------------------------
#
# Off by default: every existing preset is byte-for-byte unaffected. When ON,
# only this project's own targets (engine core, tests/benchmarks, plugin) are
# instrumented -- the in-tree JUCE tier and the imported ONNX Runtime are left
# uninstrumented. That keeps ASan focused on our code and avoids third-party
# noise (and avoids pointlessly re-baking the shared FetchContent deps).
#   -fno-sanitize-recover is deliberately NOT set: ASan aborts on a memory
#   error (hard failure), while UBSan reports to stderr and continues, so
#   pre-existing unrelated UB can't turn every run into a false test failure.
#   -fno-sanitize=alignment is set because header-only hnswlib (compiled into
#   our TUs) does a deliberate misaligned label store (hnswalg.h:1203); arm64
#   tolerates unaligned access, and the report is pure third-party noise that
#   would otherwise mask findings in our own code.
# Use with -DSSM_ENABLE_LTO=OFF / -DSSM_TEST_LTO=OFF (see the ssm-sanitize preset).
option(SSM_SANITIZE
       "Instrument the plugin/engine core/tests with AddressSanitizer + UndefinedBehaviorSanitizer (dev-only)" OFF)

if(SSM_SANITIZE)
    set(SSM_SANITIZE_COMPILE_FLAGS
        -fsanitize=address,undefined -fno-sanitize=alignment -fno-omit-frame-pointer)
    set(SSM_SANITIZE_LINK_FLAGS
        -fsanitize=address,undefined)
endif()

# Applied by every target-defining helper below (and to the plugin) so the set
# of instrumented targets can never drift from the set of consumer targets that
# must link the runtime. No-op when SSM_SANITIZE is OFF.
function(ssm_apply_sanitizer_flags target_name)
    if(SSM_SANITIZE)
        target_compile_options(${target_name} PRIVATE ${SSM_SANITIZE_COMPILE_FLAGS})
        target_link_options(${target_name} PRIVATE ${SSM_SANITIZE_LINK_FLAGS})
    endif()
endfunction()

# --- BUILD-SYSTEM OPTIMISATION (2026-08-24): tiered JUCE implementation ----
#
# JUCE's CMake module targets are intentionally INTERFACE libraries whose
# implementation sources propagate to every consumer. The first optimisation
# consolidated those sources into one static archive. This second pass keeps
# that safety boundary but splits it by dependency tier so headless engine/test
# targets do not compile or link JUCE graphics, GUI, processor-editor, and
# audio-utils implementation code.
#
# The module lists are explicit on purpose. They are the stable JUCE 8.0.2 set
# used by this project; adding a module requires review rather than silently
# changing a binary boundary. `INTERFACE_JUCE_MODULE_SOURCES` is a JUCE-
# supported target property, so this does not duplicate JUCE source globbing.
set(SSM_JUCE_CORE_MODULE_TARGETS
    juce::juce_core
    juce::juce_events
    juce::juce_data_structures
    # JuceHeader consumers instantiate JUCE Colour constants even in otherwise
    # headless translation units; graphics is the lowest safe boundary.
    juce::juce_graphics
)

set(SSM_JUCE_AUDIO_MODULE_TARGETS
    juce::juce_audio_basics
    juce::juce_audio_devices
    juce::juce_audio_formats
    juce::juce_dsp
)

set(SSM_JUCE_UI_MODULE_TARGETS
    juce::juce_gui_basics
    juce::juce_gui_extra
    juce::juce_audio_processors
    juce::juce_audio_utils
)

set(SSM_JUCE_MODULE_COMPILE_DEFINITIONS
    JUCE_GLOBAL_MODULE_SETTINGS_INCLUDED=1
    JUCE_MODULE_AVAILABLE_juce_audio_basics=1
    JUCE_MODULE_AVAILABLE_juce_audio_devices=1
    JUCE_MODULE_AVAILABLE_juce_audio_formats=1
    JUCE_MODULE_AVAILABLE_juce_audio_plugin_client=1
    JUCE_MODULE_AVAILABLE_juce_audio_processors=1
    JUCE_MODULE_AVAILABLE_juce_audio_utils=1
    JUCE_MODULE_AVAILABLE_juce_core=1
    JUCE_MODULE_AVAILABLE_juce_data_structures=1
    JUCE_MODULE_AVAILABLE_juce_dsp=1
    JUCE_MODULE_AVAILABLE_juce_events=1
    JUCE_MODULE_AVAILABLE_juce_graphics=1
    JUCE_MODULE_AVAILABLE_juce_gui_basics=1
    JUCE_MODULE_AVAILABLE_juce_gui_extra=1
)

function(ssm_collect_juce_sources output_name)
    set(collected_sources)
    foreach(_ssmJuceModule IN LISTS ARGN)
        get_target_property(_ssmJuceModuleSources
            ${_ssmJuceModule} INTERFACE_JUCE_MODULE_SOURCES)
        if(NOT _ssmJuceModuleSources OR _ssmJuceModuleSources STREQUAL "_ssmJuceModuleSources-NOTFOUND")
            message(FATAL_ERROR
                "${_ssmJuceModule} does not expose INTERFACE_JUCE_MODULE_SOURCES; "
                "the tiered JUCE implementation set is incomplete.")
        endif()
        list(APPEND collected_sources ${_ssmJuceModuleSources})
    endforeach()
    list(REMOVE_DUPLICATES collected_sources)
    set(${output_name} ${collected_sources} PARENT_SCOPE)
endfunction()

ssm_collect_juce_sources(SSM_JUCE_CORE_SOURCES ${SSM_JUCE_CORE_MODULE_TARGETS})
ssm_collect_juce_sources(SSM_JUCE_AUDIO_SOURCES ${SSM_JUCE_AUDIO_MODULE_TARGETS})
ssm_collect_juce_sources(SSM_JUCE_UI_SOURCES ${SSM_JUCE_UI_MODULE_TARGETS})
# JUCE's module properties may include transitive dependency sources. Remove
# lower-tier members explicitly so a source belongs to exactly one archive.
list(REMOVE_ITEM SSM_JUCE_AUDIO_SOURCES ${SSM_JUCE_CORE_SOURCES})
list(REMOVE_ITEM SSM_JUCE_UI_SOURCES ${SSM_JUCE_CORE_SOURCES} ${SSM_JUCE_AUDIO_SOURCES})

set(SSM_JUCE_COMMON_INCLUDE_DIRECTORIES
    ${JUCE_MODULES_DIR}
    "${CMAKE_CURRENT_BINARY_DIR}/SmartSampleManager_artefacts/JuceLibraryCode"
    "${JUCE_MODULES_DIR}/juce_audio_processors/format_types/VST3_SDK"
    "${JUCE_MODULES_DIR}/juce_audio_processors/format_types/LV2_SDK"
    "${JUCE_MODULES_DIR}/juce_audio_processors/format_types/LV2_SDK/lv2"
    "${JUCE_MODULES_DIR}/juce_audio_processors/format_types/LV2_SDK/serd"
    "${JUCE_MODULES_DIR}/juce_audio_processors/format_types/LV2_SDK/sord"
    "${JUCE_MODULES_DIR}/juce_audio_processors/format_types/LV2_SDK/sord/src"
    "${JUCE_MODULES_DIR}/juce_audio_processors/format_types/LV2_SDK/sratom"
    "${JUCE_MODULES_DIR}/juce_audio_processors/format_types/LV2_SDK/lilv"
    "${JUCE_MODULES_DIR}/juce_audio_processors/format_types/LV2_SDK/lilv/src"
)

function(ssm_configure_juce_static target_name source_list)
    add_library(${target_name} STATIC ${${source_list}})
    set_target_properties(${target_name} PROPERTIES POSITION_INDEPENDENT_CODE ON)
    target_include_directories(${target_name} PUBLIC ${SSM_JUCE_COMMON_INCLUDE_DIRECTORIES})
    target_compile_definitions(${target_name} PUBLIC
        ${SSM_JUCE_MODULE_COMPILE_DEFINITIONS}
        $<$<CONFIG:Debug>:DEBUG=1>
        $<$<CONFIG:Debug>:_DEBUG=1>
        $<$<NOT:$<CONFIG:Debug>>:NDEBUG=1>
        $<$<NOT:$<CONFIG:Debug>>:_NDEBUG=1>
    )
    target_link_libraries(${target_name} PRIVATE
        juce::juce_recommended_config_flags
        juce::juce_recommended_warning_flags
    )
    if(APPLE)
        target_link_libraries(${target_name} PUBLIC
            "-framework CoreAudioKit"
            "-framework DiscRecording"
            "-framework WebKit"
            "-weak_framework Metal"
            "-weak_framework MetalKit"
            "-framework CoreAudio"
            "-framework CoreMIDI"
            "-framework AudioToolbox"
            "-framework Cocoa"
            "-framework Foundation"
            "-framework IOKit"
            "-framework Security"
            "-framework QuartzCore"
            "-framework Accelerate"
        )
    endif()
endfunction()

ssm_configure_juce_static(ssm_juce_core SSM_JUCE_CORE_SOURCES)
ssm_configure_juce_static(ssm_juce_audio SSM_JUCE_AUDIO_SOURCES)
ssm_configure_juce_static(ssm_juce_ui SSM_JUCE_UI_SOURCES)

target_link_libraries(ssm_juce_audio PUBLIC ssm_juce_core)
target_link_libraries(ssm_juce_ui PUBLIC ssm_juce_audio)

# Compatibility interface for any future ordinary consumer that genuinely
# needs the full JUCE surface. Existing targets below deliberately select the
# narrowest tier instead of using this aggregate.
add_library(ssm_juce INTERFACE)
target_link_libraries(ssm_juce INTERFACE ssm_juce_ui)

juce_add_plugin(SmartSampleManager
    COMPANY_NAME "NITE DSP"
    COMPANY_COPYRIGHT "Copyright (c) 2026 NITE DSP. All rights reserved."
    COMPANY_WEBSITE "https://nitedsp.co.uk"
    COMPANY_EMAIL "nitedsp@outlook.com"
    BUNDLE_ID "com.nitedsp.smartsamplemanager"
    IS_SYNTH FALSE
    NEEDS_MIDI_INPUT FALSE
    NEEDS_MIDI_OUTPUT FALSE
    IS_MIDI_EFFECT FALSE
    EDITOR_WANTS_KEYBOARD_FOCUS TRUE
    COPY_PLUGIN_AFTER_BUILD ${SSM_INSTALL_PLUGINS_AFTER_BUILD}
    PLUGIN_MANUFACTURER_CODE NDSP
    PLUGIN_CODE AtSm
    FORMATS VST3 AU Standalone
    PRODUCT_NAME "SLO"
    ICON_BIG "${CMAKE_CURRENT_SOURCE_DIR}/Resources/AppIcon-1024.png"
)

# JUCE's convenience macro adds juce::juce_audio_plugin_client to the shared
# code target. That target is an INTERFACE source carrier, so the link entry
# makes JUCE's core/audio/UI implementation sources compile into
# SmartSampleManager_ artefacts/SharedCode as well as into the tier archives
# above. The format wrapper targets still link their own
# juce_audio_plugin_client_<format> implementation, which is the only JUCE
# code that must remain format-specific.
#
# Keep the module-availability definitions on the shared target because JUCE's
# wrapper setup re-exports these definitions to the generated format targets.
target_compile_definitions(SmartSampleManager PUBLIC
    ${SSM_JUCE_MODULE_COMPILE_DEFINITIONS}
)
get_target_property(SSM_PLUGIN_LINK_LIBRARIES SmartSampleManager LINK_LIBRARIES)
list(REMOVE_ITEM SSM_PLUGIN_LINK_LIBRARIES juce::juce_audio_plugin_client)
set_target_properties(SmartSampleManager PROPERTIES
    LINK_LIBRARIES "${SSM_PLUGIN_LINK_LIBRARIES}"
)

juce_generate_juce_header(SmartSampleManager)

# Copy the embedding model (Models/panns_cnn10_embedding.onnx + its external
# weights file) into each plugin format's bundle Resources/ folder after
# build. VST3/AU/Standalone are all macOS bundles sharing the same
# Contents/MacOS + Contents/Resources layout, so this one step covers all
# three -- see SampleManagerEngine::init()'s model search logic, which looks
# in exactly this location. Without this, the model would never actually be
# found by anything other than a source-tree dev build.
foreach(ssm_format_target SmartSampleManager_Standalone SmartSampleManager_VST3 SmartSampleManager_AU)
    add_custom_command(TARGET ${ssm_format_target} POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E make_directory "$<TARGET_BUNDLE_CONTENT_DIR:${ssm_format_target}>/Resources"
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
            "${CMAKE_CURRENT_SOURCE_DIR}/Models/panns_cnn10_embedding.onnx"
            "${CMAKE_CURRENT_SOURCE_DIR}/Models/panns_cnn10_embedding.onnx.data"
            "${CMAKE_CURRENT_SOURCE_DIR}/THIRD_PARTY_NOTICES.txt"
            "$<TARGET_BUNDLE_CONTENT_DIR:${ssm_format_target}>/Resources/"
    )
endforeach()

# JUCE can leave a stale ad-hoc signature on AU bundles when the post-build
# resource copy above adds the model/notice files after the wrapper has been
# linked. In that state VST3 may still verify while AU reports that its signed
# resource set is missing, which causes hosts to reject the component before
# the editor can even open. Development builds are intentionally ad-hoc
# signed here after *all* resource mutations; a release Developer ID signing
# pass must still run afterwards (see scripts/codesign_and_package.py).
if(APPLE AND NOT SSM_BUNDLE_APPLE_DEPS)
    foreach(ssm_format_target SmartSampleManager_Standalone SmartSampleManager_VST3 SmartSampleManager_AU)
        add_custom_command(TARGET ${ssm_format_target} POST_BUILD
            COMMAND codesign --force --deep --sign -
                "$<TARGET_BUNDLE_CONTENT_DIR:${ssm_format_target}>/.."
            COMMENT "Ad-hoc signing ${ssm_format_target} after resource copy"
            VERBATIM
        )
    endforeach()
endif()

# Bundle the Homebrew-resolved runtime dependencies (TagLib, ONNX Runtime,
# libsodium) AND their transitive Homebrew dependencies into each format's
# own Contents/Frameworks/ and rewrite every load command to @rpath/
# @loader_path, so a customer machine without Homebrew can still run the
# app -- see docs/RUNTIME_DEPENDENCY_STRATEGY.md.
# Apple-only (install_name_tool/otool are Apple binary-utility tools; this
# whole problem is macOS-specific -- Windows dependency distribution is a
# separate, not-yet-verified concern, see docs/WINDOWS_READINESS.md).
#
# Phase 5.5: replaced the previous cmake/BundleAppleDeps.cmake, which only
# handled the three top-level libs and never inspected what THEY link
# against -- scripts/check_homebrew_dependencies.py caught libonnxruntime's
# own transitive Homebrew dependencies (abseil/protobuf/re2, ~90 dylibs)
# shipping unbundled. scripts/bundle_apple_deps.py walks the full
# transitive dependency graph instead of just the top level.
if(APPLE AND SSM_BUNDLE_APPLE_DEPS)
    foreach(ssm_format_target SmartSampleManager_Standalone SmartSampleManager_VST3 SmartSampleManager_AU)
        add_custom_command(TARGET ${ssm_format_target} POST_BUILD
            COMMAND python3 "${CMAKE_CURRENT_SOURCE_DIR}/scripts/bundle_apple_deps.py"
                "--bundle-content-dir" "$<TARGET_BUNDLE_CONTENT_DIR:${ssm_format_target}>"
                "--exe-path" "$<TARGET_FILE:${ssm_format_target}>"
                "--libs" "${TAGLIB_LIBRARY},${ONNXRUNTIME_LIBRARY},${SODIUM_LIBRARY}"
                # NOTE: SSM_BUNDLE_REWRITE_JOBS is defined above but deliberately not
                # passed here -- the recovered build-fix commit's CMakeLists.txt
                # assumed an accompanying scripts/bundle_apple_deps.py that added
                # --rewrite-jobs support; that script change was excluded from this
                # cherry-pick as out of scope (see SLO master plan Phase 0.1/New
                # Findings -- it was mixed in with unrelated licensing_server changes).
                # The currently-shipped script only accepts --bundle-content-dir,
                # --exe-path, --libs. Re-add this flag if/when that script is
                # reviewed and updated to support it.
        )
    endforeach()
endif()


# Sources
target_sources(SmartSampleManager PRIVATE
    Source/PluginProcessor.cpp
    Source/PluginEditor.cpp
    Source/SLOLookAndFeel.h
    Source/SampleManagerEngine.cpp
    Source/AbletonTaxonomy.cpp
    Source/AbletonXmpWriter.cpp
    Source/SampleCanvas.cpp
    Source/VectorMath.cpp
    Source/Licensing/LicenseManager.cpp
    Source/AppSettings.cpp
    Source/AppLogger.cpp
    Source/MainMenuModel.cpp
    Source/PreferencesWindow.cpp
    Source/ResultsPanel.cpp
    Source/PrecisionBrowser.cpp
    Source/SmartCollectionsPanel.cpp
    Source/SortPreviewPanel.cpp
)

# Include paths
target_include_directories(SmartSampleManager PRIVATE
    Source
    ${TAGLIB_INCLUDE_DIR}
    ${ONNXRUNTIME_INCLUDE_DIR}
    ${dr_libs_SOURCE_DIR}
    ${hnswlib_SOURCE_DIR}
    ${SODIUM_INCLUDE_DIR}
    ${SQLITE3_INCLUDE_DIR}
)

# Link libraries
target_link_libraries(SmartSampleManager PRIVATE
    ssm_juce_ui
    libscran::umappp
    ${TAGLIB_LIBRARY}
    ${ONNXRUNTIME_LIBRARY}
    ${SODIUM_LIBRARY}
    ${SQLITE3_LINK_TARGET}
)
if(APPLE)
    target_link_libraries(SmartSampleManager PRIVATE ${ACCELERATE_FRAMEWORK})
endif()

# Recommended Flags
target_link_libraries(SmartSampleManager PUBLIC
    juce::juce_recommended_config_flags
    juce::juce_recommended_warning_flags
)
# LTO is tier-gated (see the SSM_ENABLE_LTO option above). Default ON keeps
# historical release behaviour byte-for-byte; only an explicit opt-out drops it.
if(SSM_ENABLE_LTO)
    target_link_libraries(SmartSampleManager PUBLIC juce::juce_recommended_lto_flags)
endif()

# Dev-only ASan/UBSan instrumentation of the shipped plugin target itself
# (no-op unless SSM_SANITIZE is ON). The plugin's release flags above are
# untouched by default.
ssm_apply_sanitizer_flags(SmartSampleManager)

# --- BUILD-SYSTEM OPTIMISATION (2026-08-22): shared engine core -------------
#
# The five TUs below used to be copy-pasted into the source list of ~22
# Test*/Benchmark* executables, so SampleManagerEngine.cpp (~4.9k lines) was
# compiled 28x per configuration per tree (28 .o copies counted in build-test).
# flags.make comparison across those targets proved every consumer compiled
# them with IDENTICAL defines/options, differing only in SSM_TEST_BINARY=1.
# They are now compiled exactly twice per configuration:
#
#   ssm_engine_core_prod  -- no SSM_TEST_BINARY. Used by TestSafetyRegression,
#                            which must exercise getCacheDbFile() exactly as a
#                            non-test binary would (its guard must not abort).
#   ssm_engine_core_test  -- PRIVATE SSM_TEST_BINARY=1, preserving the
#                            openCacheDb() fail-closed production-path guard
#                            for every other test binary.
#
# OBJECT libraries (not STATIC) are deliberate: object files are placed
# directly on each consumer's link line exactly as when the sources were
# listed per-target, so archive-member extraction semantics cannot change
# (no risk of unreferenced static initialisers being dropped). The plugin
# target itself is untouched -- it compiles these TUs once already and its
# JucePlugin_* usage requirements stay private to it.

set(SSM_ENGINE_CORE_SOURCES
    Source/SampleManagerEngine.cpp
    Source/AbletonTaxonomy.cpp
    Source/AbletonXmpWriter.cpp
    Source/VectorMath.cpp
    Source/AppLogger.cpp
)

# Runtime/link dependencies belong to the final executable, not the shared
# OBJECT core. JUCE module targets carry their implementation objects; linking
# them PUBLIC from an OBJECT library makes those objects appear both on the
# consumer's direct link line and through the core target, producing duplicate
# symbols. The core itself only needs the include paths and compile definitions
# below; its consumers own the single JUCE/runtime implementation path.
set(SSM_ENGINE_RUNTIME_LIBRARIES
    ssm_juce_audio
    libscran::umappp
    ${TAGLIB_LIBRARY}
    ${ONNXRUNTIME_LIBRARY}
    ${SQLITE3_LINK_TARGET}
    juce::juce_recommended_config_flags
    juce::juce_recommended_warning_flags
)
if(APPLE)
    list(APPEND SSM_ENGINE_RUNTIME_LIBRARIES ${ACCELERATE_FRAMEWORK})
endif()

# The UMAPPP target previously supplied these transitively through the core's
# PUBLIC link interface. Preserve its header-only dependency include graph as
# usage requirements without importing any implementation objects.
get_target_property(SSM_UMAPPP_INTERFACE_INCLUDE_DIRECTORIES
    libscran::umappp INTERFACE_INCLUDE_DIRECTORIES)

function(ssm_add_engine_core name)
    add_library(${name} OBJECT ${SSM_ENGINE_CORE_SOURCES})
    # PUBLIC include dirs + definitions replace the identical per-target lists
    # every engine-consuming target used to restate by hand. NOTE: this set is
    # intentionally WITHOUT ${SODIUM_INCLUDE_DIR} -- the historical per-test
    # include sets never listed it and nothing in these TUs or test mains
    # includes <sodium.h> directly.
    target_include_directories(${name} PUBLIC
        Source
        ${TAGLIB_INCLUDE_DIR}
        ${ONNXRUNTIME_INCLUDE_DIR}
        ${dr_libs_SOURCE_DIR}
        ${hnswlib_SOURCE_DIR}
        ${SQLITE3_INCLUDE_DIR}
        ${JUCE_MODULES_DIR}
        ${SSM_UMAPPP_INTERFACE_INCLUDE_DIRECTORIES}
        ${umappp_SOURCE_DIR}/include
        ${aarand_SOURCE_DIR}/include
        ${irlba_SOURCE_DIR}/include
        ${Eigen3_SOURCE_DIR}
        ${subpar_SOURCE_DIR}/include
        ${sanisizer_SOURCE_DIR}/include
        ${knncolle_SOURCE_DIR}/include
        "${CMAKE_CURRENT_BINARY_DIR}/SmartSampleManager_artefacts/JuceLibraryCode"
    )
    target_compile_definitions(${name} PUBLIC
        SMART_SAMPLE_MANAGER_SOURCE_DIR="${CMAKE_CURRENT_SOURCE_DIR}"
        ${SSM_JUCE_MODULE_COMPILE_DEFINITIONS}
        $<$<CONFIG:Debug>:DEBUG=1>
        $<$<CONFIG:Debug>:_DEBUG=1>
        $<$<NOT:$<CONFIG:Debug>>:NDEBUG=1>
        $<$<NOT:$<CONFIG:Debug>>:_NDEBUG=1>
    )
    # JuceHeader.h is generated into the plugin artefacts dir only once the
    # plugin target builds; consumers of these cores inherit the ordering via
    # normal target_link_libraries dependency edges (replaces the old
    # per-target add_dependencies loop).
    add_dependencies(${name} SmartSampleManager)
    ssm_apply_sanitizer_flags(${name})
endfunction()

ssm_add_engine_core(ssm_engine_core_prod)

ssm_add_engine_core(ssm_engine_core_test)
# The single deliberate delta between the two core variants.
target_compile_definitions(ssm_engine_core_test PRIVATE SSM_TEST_BINARY=1)
# Release-candidate parity tier: optimise test-side core TUs like the product.
if(SSM_TEST_LTO)
    target_link_libraries(ssm_engine_core_test PUBLIC juce::juce_recommended_lto_flags)
endif()

# Declarative helper replacing ~20 hand-restated target blocks. Each engine
# regression/benchmark executable is: its own main TU (+ optional extra
# sources) linked against the shared test core. Target names are unchanged
# from the pre-refactor file, so scripts/CI referencing them keep working.
function(ssm_add_engine_test name mainSource)
    cmake_parse_arguments(PARSE_ARGV 2 SSMET "" "" "EXTRA_SOURCES")
    add_executable(${name}
        ${mainSource}
        ${SSMET_EXTRA_SOURCES}
    )
    target_include_directories(${name} PRIVATE Source)
    target_link_libraries(${name} PRIVATE
        ssm_engine_core_test
        ${SSM_ENGINE_RUNTIME_LIBRARIES}
    )
    if(SSM_TEST_LTO)
        target_link_libraries(${name} PRIVATE juce::juce_recommended_lto_flags)
    endif()
    ssm_apply_sanitizer_flags(${name})
endfunction()

# Same shape as ssm_add_engine_test, but links the PRODUCTION core (no
# SSM_TEST_BINARY). Reserved for TestSafetyRegression, which must observe
# getCacheDbFile()'s path resolution exactly as a non-test binary would.
function(ssm_add_engine_core_prod_consumer name mainSource)
    add_executable(${name} ${mainSource})
    target_include_directories(${name} PRIVATE Source)
    target_link_libraries(${name} PRIVATE
        ssm_engine_core_prod
        ${SSM_ENGINE_RUNTIME_LIBRARIES}
    )
    if(SSM_TEST_LTO)
        target_link_libraries(${name} PRIVATE juce::juce_recommended_lto_flags)
    endif()
    ssm_apply_sanitizer_flags(${name})
endfunction()

# Test Executable
ssm_add_engine_test(TestSampleEngine Source/test_main.cpp)
# Lets test_main.cpp locate its fixture files (Models/panns_cnn10_embedding.onnx, test_kick.wav)
# relative to the source tree instead of a hardcoded developer machine path.
# (SMART_SAMPLE_MANAGER_SOURCE_DIR now arrives via ssm_engine_core_test PUBLIC.)

# Classification Benchmark Executable
ssm_add_engine_test(ClassificationBenchmark
    tools/classification_benchmark/classification_benchmark_main.cpp)

# Path Traversal Regression Test -- proves reorganizeSamples() can't be
# steered outside the library root via malicious WAV metadata (untrusted
# imported-file input). See sanitizePathComponent() in SampleManagerEngine.cpp.
ssm_add_engine_test(TestPathTraversal Source/test_path_traversal_main.cpp)

# Duplicate Detection Regression Test -- proves findDuplicateGroups() groups
# renamed copies of identical audio, excludes genuinely different files, and
# stays correct across a retag (content_hash must be metadata-independent).
ssm_add_engine_test(TestDuplicateDetection Source/test_duplicate_detection_main.cpp)

# Prune-Missing-Files Regression Test -- proves pruneMissingFiles() removes
# exactly the samples whose files were deleted externally, never touches
# disk itself, preserves catalogue records on disconnected external drives,
# and is a correct no-op when nothing's missing.
ssm_add_engine_test(TestPruneMissing Source/test_prune_missing_main.cpp)

# F-04 Diagnostics Bundle Contract Test -- proves buildDiagnosticsBundle()
# emits parseable JSON with every required section (versions, OOD
# thresholds, library + scan receipt incl. non-audio skip counting,
# evidence splits, log tail) after a real 2-file + 1-skipped scan.
ssm_add_engine_test(TestDiagnosticsBundle Source/test_diagnostics_bundle_main.cpp)

# P2-1 Fusion V2 gate-logic test -- pure MlOverrideGate::evaluate() cases:
# flag OFF reproduces V1 exactly; flag ON fires only on the full narrow
# precondition set. No audio, no ONNX, no engine instance.
ssm_add_engine_test(TestFusionV2 Source/test_fusion_v2_main.cpp)

# P2-2 Loop V2 contested-evidence test -- pure AbletonTaxonomy::classify()
# cases: flag OFF reproduces V1; flag ON lets confident DSP overrule a
# one-sided filename at discounted confidence with a Contested tag.
ssm_add_engine_test(TestLoopV2 Source/test_loop_v2_main.cpp)

# UMAP Eligibility Regression Test -- pins collectUmapEligibleSamples(), the
# single shared predicate behind runFullUMAP(). The projection used one
# predicate (hasUsableEmbedding) to size its flat buffer and a different one
# (!isProcessed) to write coordinates back, desyncing the index and corrupting
# coords/OOB-reading -- this test forces any recurrence to fail without
# running umappp itself.
ssm_add_engine_test(TestUmapEligibility Source/test_umap_eligible_main.cpp)

# Resilience Regression Test -- Phase 2 hardening: proves a missing/invalid
# ONNX model never produces a fake pseudo-embedding (honest FailedRetryable/
# FailedPermanent status instead), and that a corrupted SQLite cache DB is
# detected and quarantined-and-rebuilt rather than crashing or serving
# corrupt data. See docs/ONNX_FAILURE_HANDLING.md, docs/DATABASE_HARDENING.md.
ssm_add_engine_test(TestResilience Source/test_resilience_main.cpp)


# Cache Integrity + User-State-Preservation Regression Test -- hardening brief
# section 7/8/9: proves a healthy cache is never quarantined, a genuinely
# corrupt cache is quarantined-and-rebuilt, and user state (favorites, history,
# collections, tag overrides) survives a quarantine. Uses raw sqlite3 access
# for the override-injection/verification, hence the explicit SQLITE3 linkage.
ssm_add_engine_test(TestCacheIntegrity Source/test_cache_integrity_main.cpp)

# Malformed-Audio Regression Test -- Phase 2 Section 78: proves genuinely
# corrupt/malformed WAV files (garbage bytes, truncated header, zero-byte,
# lying data-chunk length) never crash the scanner, never get added to the
# library, never poison the cache, and never stop a valid file in the same
# scan batch from being processed correctly.
ssm_add_engine_test(TestMalformedAudio Source/test_malformed_audio_main.cpp)

# Format-aware scan regression test -- proves directory/file admission follows
# JUCE's registered readers and that the generic reader path processes mixed
# WAV/AIFF/FLAC input while ignoring unsupported or malformed siblings.
ssm_add_engine_test(TestFormatAwareScan Source/test_format_aware_scan_main.cpp)

# Multi-Instance Regression Test -- Phase 2 Section 30: two engine instances
# (simulating two plugin instances in one DAW process) concurrently scanning
# into the same shared on-disk cache DB, proving no deadlock, no corruption,
# and no cross-contamination between instances' in-memory sample lists.
ssm_add_engine_test(TestMultiInstance Source/test_multi_instance_main.cpp)

# Sort-Library-Async Regression Test -- proves reorganizeSamplesAsync()'s
# re-entrancy guard (a second concurrent call is a silent no-op) and
# cancellation (cancelSortLibrary() actually stops the operation before all
# files are processed), and exercises the engine-owned sortThread
# join-in-destructor fix (see docs/SORT_LIBRARY_BACKGROUND.md).
ssm_add_engine_test(TestSortLibraryAsync Source/test_sort_library_async_main.cpp)
ssm_add_engine_test(TestSortPreviewAndUndo Source/test_sort_preview_and_undo_main.cpp)

# Embedding Quality Regression Test -- proves the REAL production pipeline
# (dr_wav decode -> the engine's own linear-interpolation resampler -> ONNX
# inference) produces acoustically meaningful embeddings, not just that the
# model export was numerically correct in isolation (see
# model_export/export_cnn10.py for that separate check).
ssm_add_engine_test(TestEmbeddingQuality Source/test_embedding_quality_main.cpp)

# Inference Batch Flush Test -- verifies the batched-inference pipeline's
# tail behavior: sub-kMinBatch batches flush and commit (never dropped) on
# both enqueue paths (fresh-decode and cache-hit), and don't stall once the
# scan pool has drained (engineering/slo-perf-scale-v1 Phase 1).
ssm_add_engine_test(TestInferenceBatchFlush Source/test_inference_batch_flush_main.cpp)

# Path Index Integrity Test -- behavioral coverage for the pathToIndex map
# (Phase 3): map-miss lookups, prune + rescan without duplicates, and
# post-prune similarity-query consistency.
ssm_add_engine_test(TestPathIndexIntegrity Source/test_path_index_integrity_main.cpp)

# Find-Similar Regression Test -- proves findSimilarSamples() ranks
# acoustically similar samples correctly through the real production
# pipeline, using the same real_*.wav fixtures as TestEmbeddingQuality.
ssm_add_engine_test(TestFindSimilar Source/test_find_similar_main.cpp)

# Scan/search benchmark harness for docs/PERFORMANCE_BASELINE.md. Dev
# tooling only -- not part of the shipped product (see docs/RELEASE_MANIFEST.md's
# exclusion list). Mirrors TestFindSimilar's dependency set exactly since it
# exercises the same engine code paths.
ssm_add_engine_test(BenchmarkScan Source/benchmark_scan_main.cpp)

# Ableton Taxonomy Regression Test -- pure-logic unit test for
# AbletonTaxonomy::classify()/detectLoopVsOneShot(). No JUCE/TagLib/ONNX
# dependency: the module under test has none, so this stays a fast,
# dependency-free build unlike the other test executables above.
# Beta safety: the decision policy that gates Sort Library, and the correction
# log that turns user edits into label evidence. Both are header-only and pure,
# so they get plain executables rather than the engine test core.
add_executable(TestBetaDecisionPolicy Source/test_beta_decision_policy_main.cpp)
target_include_directories(TestBetaDecisionPolicy PRIVATE Source)

add_executable(TestBetaSortGate Source/test_beta_sort_gate_main.cpp)
target_include_directories(TestBetaSortGate PRIVATE Source)

add_executable(TestCorrectionLog Source/test_correction_log_main.cpp)
target_include_directories(TestCorrectionLog PRIVATE Source)

add_executable(TestTaxonomy
    Source/AbletonTaxonomy.cpp
    Source/test_taxonomy_main.cpp
)
target_include_directories(TestTaxonomy PRIVATE Source)

# Versioned, decision-neutral evidence contract and flat-taxonomy compatibility
# adapter. Pure C++ so architectural parity remains fast to verify.
add_executable(TestAudioEvidence
    Source/test_audio_evidence_main.cpp
)
target_include_directories(TestAudioEvidence PRIVATE Source)

# Read-only JSON bridge for label-free evidence packets.  Keep this target on
# JUCE Core only: it validates the receipt schema without pulling in the
# production ONNX runtime or any classifier state.
add_executable(TestLabelFreeEvidencePacket
    Source/test_label_free_evidence_packet_main.cpp
)
target_include_directories(TestLabelFreeEvidencePacket PRIVATE Source)
target_link_libraries(TestLabelFreeEvidencePacket PRIVATE juce::juce_core)

# Aspect-scored similarity contract used by the retrieval layer. Kept as a
# pure header test so UI/search changes cannot weaken taxonomy or rename policy.
add_executable(TestAudioSimilarity
    Source/test_audio_similarity_main.cpp
)
target_include_directories(TestAudioSimilarity PRIVATE Source)

# Pure audition tempo regression: no engine, models or sample-library access.
add_executable(TestAuditionTempo Source/test_audition_tempo_main.cpp)
target_include_directories(TestAuditionTempo PRIVATE Source)

# Read-only producer-language synonym search. Kept dependency-free so the
# search vocabulary can be regression-tested without launching the plugin.
add_executable(TestSearchLexicon
    Source/test_search_lexicon_main.cpp
)
target_include_directories(TestSearchLexicon PRIVATE Source)
target_link_libraries(TestSearchLexicon PRIVATE juce::juce_core)

# Acoustic classifier input-safety regression test -- pure header-only logic
# for the model-output boundary.  Keep this independent of JUCE/ONNX so the
# fail-closed zero/NaN/Inf/null guards remain runnable on low CPU.
add_executable(TestAcousticClassifierInputSafety
    Source/test_acoustic_classifier_input_safety_main.cpp
)
target_include_directories(TestAcousticClassifierInputSafety PRIVATE Source)

# Classification presentation regression test -- pure field-precedence logic
# used by the canvas. Keeps an explicit ML OOD abstention from falling back to
# a stale legacy instrumentType label without requiring JUCE or a native build.
add_executable(TestClassificationPresentation
    Source/test_classification_presentation_main.cpp
)
target_include_directories(TestClassificationPresentation PRIVATE Source)

# Physical Acoustics Regression Test -- proves modal resonator template fits,
# Bessel membrane mode matching, plate/bar dispersion, stiff-string inharmonicity
# and pitch trajectory dynamics.
add_executable(TestPhysicalAcoustics
    Source/test_physical_acoustics_main.cpp
)
target_include_directories(TestPhysicalAcoustics PRIVATE Source)

# Ableton XMP Writer Regression Test -- proves the experimental Tier-3 XMP
# sidecar writer round-trips its own output AND correctly parses/extends a
# real Ableton/LiveTagger-format sidecar without disturbing other files'
# entries (see AbletonXmpWriter.h). Needs JUCE (XmlDocument/File) but not
# TagLib/ONNX.
add_executable(TestXmpWriter
    Source/AbletonXmpWriter.cpp
    Source/test_xmp_writer_main.cpp
)
target_include_directories(TestXmpWriter PRIVATE
    Source
    "${CMAKE_CURRENT_BINARY_DIR}/SmartSampleManager_artefacts/JuceLibraryCode"
)
add_dependencies(TestXmpWriter SmartSampleManager)
target_link_libraries(TestXmpWriter PRIVATE
    ssm_juce_core
    juce::juce_recommended_config_flags
    juce::juce_recommended_warning_flags
)

# Licensing Test Executable (see Source/Licensing/ and licensing_server/)
add_executable(TestLicensing
    Source/Licensing/LicenseManager.cpp
    Source/test_licensing_main.cpp
)
target_include_directories(TestLicensing PRIVATE
    Source
    ${SODIUM_INCLUDE_DIR}
    "${CMAKE_CURRENT_BINARY_DIR}/SmartSampleManager_artefacts/JuceLibraryCode"
)
target_link_libraries(TestLicensing PRIVATE
    ssm_juce_core
    ${SODIUM_LIBRARY}
)
target_link_libraries(TestLicensing PUBLIC
    juce::juce_recommended_config_flags
    juce::juce_recommended_warning_flags
)
if(SSM_TEST_LTO)
    target_link_libraries(TestLicensing PUBLIC juce::juce_recommended_lto_flags)
endif()

# --- RECOVERY PHASE R1 -- restored regression targets --------------------
# See docs/SLO_LOST_WORK_RECOVERY_MANIFEST.md. These mirror TestFindSimilar's
# dependency set exactly (same engine translation unit + full native deps).
# Only targets whose underlying engine API has actually been restored this
# phase are wired up here (Favorites, History, Smart Collections, plus the
# new cache-isolation safety regression test) -- the other recovered test
# *sources* (test_audio_features_main.cpp etc.) are committed but
# deliberately NOT added below yet, since the engine APIs they call
# (audio-feature extraction, weighted similarity, timbre refinement,
# near-duplicate/auto-tag/map-cluster/reference-search/cache-version-
# enforcement) are still REIMPLEMENTATION REQUIRED -- see the manifest.
#
# --- RECOVERY PHASE R2 -- Audio Features restored below (see
# docs/SLO_AUDIO_FEATURE_RECOVERY.md). TestAudioFeatures was previously
# orphaned (source present, no target) since SampleItem::audioFeatures /
# featureVersion didn't exist yet -- now configured like the R1 targets
# above. Weighted Find Similar / Timbre Refinement / Auto-Tagging /
# Near-Duplicates / Reference Search / Map Clusters / Cache Version
# Enforcement remain REIMPLEMENTATION REQUIRED -- explicitly R3 scope, not
# touched this phase.

ssm_add_engine_test(TestFavorites Source/test_favorites_main.cpp)

# Exercises PrecisionBrowser's click-to-sort ordering through the real
# sortOrderChanged()/applySort() path, so it links the browser translation
# unit alongside the usual engine dependency set. Enrolled in
# SSM_TEST_TARGETS below, which grants it SSM_TEST_BINARY and therefore the
# production-cache-path abort.
ssm_add_engine_test(TestPrecisionBrowserSorting
    Source/test_precision_browser_sorting.cpp
    EXTRA_SOURCES Source/PrecisionBrowser.cpp
)
target_link_libraries(TestPrecisionBrowserSorting PRIVATE ssm_juce_ui)

# B-010 (SLO Beta Blocker Register): real-time deadline-stress + allocation
# instrumentation for processBlock(). PluginProcessor.cpp/PluginEditor.cpp
# aren't part of SSM_ENGINE_CORE_SOURCES (they're plugin-format sources, only
# otherwise compiled into the SmartSampleManager plugin target itself) --
# added here as EXTRA_SOURCES against the ssm_juce_ui tier, same pattern as
# TestPrecisionBrowserSorting above.
ssm_add_engine_test(TestRtDeadlineStress
    Source/test_rt_deadline_stress_main.cpp
    EXTRA_SOURCES
        Source/PluginProcessor.cpp
        Source/PluginEditor.cpp
        Source/SampleCanvas.cpp
        Source/Licensing/LicenseManager.cpp
        Source/AppSettings.cpp
        Source/MainMenuModel.cpp
        Source/PreferencesWindow.cpp
        Source/ResultsPanel.cpp
        Source/PrecisionBrowser.cpp
        Source/SmartCollectionsPanel.cpp
        Source/SortPreviewPanel.cpp
)
target_include_directories(TestRtDeadlineStress PRIVATE ${SODIUM_INCLUDE_DIR})
target_link_libraries(TestRtDeadlineStress PRIVATE ssm_juce_ui ${SODIUM_LIBRARY})

ssm_add_engine_test(TestHistory Source/test_history_main.cpp)

# Fine-Grained Subcategorization V1, Phase 9 (B-006 follow-on): bass timbre
# tag (808/Reese) regression sanity test. BassTimbreClassifier is header-only
# and pure (no engine/JUCE dependency beyond what ssm_engine_core_test
# already provides), so this needs no EXTRA_SOURCES.
ssm_add_engine_test(TestBassTimbre Source/test_bass_timbre_main.cpp)

# Fine-Grained Subcategorization V1, Phase 10 (B-006 follow-on): kick length
# (Short/Long) regression test -- real engine, real fixture audio.
ssm_add_engine_test(TestKickLength Source/test_kick_length_main.cpp)

# Fine-Grained Subcategorization V1, Phase 11 (B-006 follow-on): hi-hat type
# tag (Open/Closed) regression sanity test. Header-only and pure, same as
# TestBassTimbre -- no EXTRA_SOURCES needed.
ssm_add_engine_test(TestHiHatType Source/test_hihat_type_main.cpp)

# SLO private beta readiness: read-only safety qualification. Proves, with
# real SHA-256 checksums on a disposable fixture library (never the owner's
# real library), that the production scan/classify path never mutates
# sample files. See docs/classification/../SLO_READ_ONLY_SAFETY_QUALIFICATION_V1.md.
ssm_add_engine_test(TestReadOnlySafetyQualification Source/test_readonly_safety_qualification_main.cpp)
target_include_directories(TestReadOnlySafetyQualification PRIVATE ${SODIUM_INCLUDE_DIR})
target_link_libraries(TestReadOnlySafetyQualification PRIVATE ${SODIUM_LIBRARY})

ssm_add_engine_test(TestAudioFeatures Source/test_audio_features_main.cpp)

# --- RECOVERY PHASE R3 -- Intelligence Stack test targets ---------------
# See docs/SLO_R3_INTELLIGENCE_RECOVERY.md. Mirror the TestAudioFeatures/
# TestFavorites dependency set exactly (same engine translation unit + full
# native deps) -- these test sources were already committed by a prior phase
# but deliberately not wired up until the engine APIs they exercise
# (findSimilarWeighted, findSimilarRefined, findSimilarToReference,
# findNearDuplicates, getPredictedTags, computeMapClusters, and the
# embedding_model_version cache-version-enforcement path) actually existed.

ssm_add_engine_test(TestFindSimilarWeighted       Source/test_find_similar_weighted_main.cpp)
ssm_add_engine_test(TestTimbreRefinement          Source/test_timbre_refinement_main.cpp)
ssm_add_engine_test(TestReferenceSearch           Source/test_reference_search_main.cpp)
ssm_add_engine_test(TestNearDuplicates            Source/test_near_duplicates_main.cpp)
ssm_add_engine_test(TestAutoTagging               Source/test_auto_tagging_main.cpp)
ssm_add_engine_test(TestMapClusters               Source/test_map_clusters_main.cpp)
ssm_add_engine_test(TestCacheVersionEnforcement   Source/test_cache_version_enforcement_main.cpp)
ssm_add_engine_test(TestPersistedCacheHydration   Source/test_persisted_cache_hydration_main.cpp)

ssm_add_engine_test(TestSmartCollections Source/test_smart_collections_main.cpp)

# Safety regression test (brief section 10) -- deliberately NOT given
# SSM_TEST_BINARY below: it never constructs a SampleManagerEngine (so
# openCacheDb()'s guard is never reached either way), and needs to resolve
# the real production path via the same code a non-test binary would use in
# order to prove the guard logic classifies it correctly.
ssm_add_engine_core_prod_consumer(TestSafetyRegression Source/test_safety_regression_main.cpp)

add_executable(TestAcousticClassifierParity
    Source/TestAcousticClassifierParity.cpp
    Source/AbletonTaxonomy.cpp
)
target_include_directories(TestAcousticClassifierParity PRIVATE Source "${CMAKE_CURRENT_BINARY_DIR}/SmartSampleManager_artefacts/JuceLibraryCode")
# Compile-time fixture root, used by the test as the PRIMARY way to locate
# tools/classification_benchmark/parity_references.json (the executable-path
# walk is only a fallback). This is what makes the test -- and therefore the
# whole project -- buildable and runnable from an out-of-tree directory such
# as _build/qualification; previously it could only resolve fixtures when the
# binary lived inside an ancestor literally named "SmartSampleManager".
target_compile_definitions(TestAcousticClassifierParity PRIVATE
    SMART_SAMPLE_MANAGER_SOURCE_DIR="${CMAKE_CURRENT_SOURCE_DIR}"
)
target_link_libraries(TestAcousticClassifierParity PRIVATE
    ssm_juce_core
)
target_link_libraries(TestAcousticClassifierParity PUBLIC
    juce::juce_recommended_config_flags
    juce::juce_recommended_warning_flags
)
if(SSM_TEST_LTO)
    target_link_libraries(TestAcousticClassifierParity PUBLIC juce::juce_recommended_lto_flags)
endif()

add_executable(TestCachedReclassification
    Source/TestCachedReclassification.cpp
)
target_include_directories(TestCachedReclassification PRIVATE Source ${SQLITE3_INCLUDE_DIR} "${CMAKE_CURRENT_BINARY_DIR}/SmartSampleManager_artefacts/JuceLibraryCode")
target_link_libraries(TestCachedReclassification PRIVATE
    ssm_juce_core
    ${SQLITE3_LINK_TARGET}
)
target_link_libraries(TestCachedReclassification PUBLIC
    juce::juce_recommended_config_flags
    juce::juce_recommended_warning_flags
)
if(SSM_TEST_LTO)
    target_link_libraries(TestCachedReclassification PUBLIC juce::juce_recommended_lto_flags)
endif()

# RECOVERY PHASE R1 P0 fail-closed guard (see openCacheDb() in
# SampleManagerEngine.cpp, docs/SLO_LOST_WORK_RECOVERY_MANIFEST.md,
# AGENT_SAFETY.md): every Test*/Benchmark* target -- except
# TestSafetyRegression, see its comment above -- gets SSM_TEST_BINARY so any
# test binary that resolves to the production cache path (i.e. forgot
# ScopedIsolatedCacheDb) aborts before ever calling sqlite3_open, rather than
# silently touching the real production DB.
set(SSM_TEST_TARGETS
    TestSampleEngine TestPathTraversal TestDuplicateDetection TestPruneMissing
    TestResilience TestMalformedAudio TestFormatAwareScan TestMultiInstance TestSortLibraryAsync
    TestSortPreviewAndUndo
    TestEmbeddingQuality TestFindSimilar BenchmarkScan TestFavorites
    TestInferenceBatchFlush TestPathIndexIntegrity
    TestHistory TestSmartCollections TestAudioFeatures TestCacheIntegrity
    TestFindSimilarWeighted TestTimbreRefinement TestReferenceSearch
    TestNearDuplicates TestAutoTagging TestMapClusters TestCacheVersionEnforcement
    TestPersistedCacheHydration TestAcousticClassifierParity TestCachedReclassification
    TestPrecisionBrowserSorting TestRtDeadlineStress TestBassTimbre
    TestReadOnlySafetyQualification TestKickLength TestHiHatType
    TestAudioEvidence TestAudioSimilarity TestSearchLexicon TestCorrectionLog
    TestPhysicalAcoustics TestDiagnosticsBundle TestFusionV2 TestLoopV2
)
foreach(_ssmTestTarget IN LISTS SSM_TEST_TARGETS)
    if(TARGET ${_ssmTestTarget})
        target_compile_definitions(${_ssmTestTarget} PRIVATE SSM_TEST_BINARY=1)
    endif()
endforeach()

# RECOVERY PHASE R1 build-ordering fix: every target that includes
# SampleManagerEngine.h (and therefore <JuceHeader.h>) reads the header from
# "${CMAKE_CURRENT_BINARY_DIR}/SmartSampleManager_artefacts/JuceLibraryCode",
# which juce_generate_juce_header(SmartSampleManager) only produces once the
# SmartSampleManager target itself has been configured/built. Building a
# Test*/Benchmark* target in isolation (e.g. `cmake --build . --target
# TestFavorites`, without also building SmartSampleManager first) failed
# with "'JuceHeader.h' file not found" until this dependency was made
# explicit -- previously only TestXmpWriter had this
# (`add_dependencies(TestXmpWriter SmartSampleManager)`); every other
# JuceHeader.h-consuming test target relied on incidental build-order luck.
#
# BUILD-SYSTEM OPTIMISATION (2026-08-22): ssm_engine_core_prod /
# ssm_engine_core_test now carry the SmartSampleManager dependency themselves,
# and every engine-core consumer inherits it transitively, so only the
# standalone JuceHeader-consuming targets still need to be listed here.
set(SSM_JUCE_HEADER_DEPENDENT_TARGETS
    TestXmpWriter TestLicensing TestAcousticClassifierParity TestCachedReclassification
    TestRtDeadlineStress
)
foreach(_ssmJuceDepTarget IN LISTS SSM_JUCE_HEADER_DEPENDENT_TARGETS)
    if(TARGET ${_ssmJuceDepTarget})
        add_dependencies(${_ssmJuceDepTarget} SmartSampleManager)
    endif()
endforeach()

# --- BUILD-SYSTEM OPTIMISATION (2026-08-22): selective qualification groups --
#
# Map tests to risk surfaces so a small classification change does not force a
# rebuild/run of every unrelated target. Groups are plain custom targets:
#     cmake --build <tree> --target ssm_qual_classification
# Full-suite qualification remains available via ssm_qual_full.
add_custom_target(ssm_qual_fast_regression
    DEPENDS TestTaxonomy TestAcousticClassifierInputSafety TestClassificationPresentation TestXmpWriter TestPathTraversal TestDuplicateDetection
            TestPruneMissing TestSafetyRegression TestCachedReclassification
            TestReadOnlySafetyQualification TestAudioEvidence TestLabelFreeEvidencePacket TestAudioSimilarity
            TestSearchLexicon TestCorrectionLog TestDiagnosticsBundle
    COMMENT "Fast pure-logic / low-cost regression suite")
add_custom_target(ssm_qual_cache
    DEPENDS TestResilience TestCacheIntegrity TestCacheVersionEnforcement
            TestPersistedCacheHydration TestMalformedAudio TestFormatAwareScan TestMultiInstance
            TestSortLibraryAsync TestSortPreviewAndUndo
    COMMENT "Cache integrity / resilience / concurrency risk surface")
add_custom_target(ssm_qual_classification
    DEPENDS TestTaxonomy TestAcousticClassifierInputSafety TestClassificationPresentation TestAudioFeatures TestAutoTagging TestSmartCollections
            TestMapClusters TestAcousticClassifierParity ClassificationBenchmark
            TestBassTimbre TestKickLength TestHiHatType TestFusionV2 TestLoopV2
    COMMENT "Classification & tagging risk surface")
add_custom_target(ssm_qual_intelligence
    DEPENDS TestEmbeddingQuality TestFindSimilar TestFindSimilarWeighted
            TestTimbreRefinement TestReferenceSearch TestNearDuplicates
    COMMENT "Embedding/similarity intelligence stack")
add_custom_target(ssm_qual_ui
    DEPENDS TestPrecisionBrowserSorting TestFavorites TestHistory TestLicensing
            TestSampleEngine TestRtDeadlineStress TestAuditionTempo
    COMMENT "User state, browser behaviour, licensing, RT deadline/allocation stress")
add_custom_target(ssm_plugins
    DEPENDS SmartSampleManager_VST3 SmartSampleManager_AU SmartSampleManager_Standalone
    COMMENT "Build all JUCE plugin formats")
add_custom_target(ssm_qual_full
    DEPENDS ssm_qual_fast_regression ssm_qual_cache ssm_qual_classification
            ssm_qual_intelligence ssm_qual_ui BenchmarkScan
            SmartSampleManager_VST3 SmartSampleManager_AU SmartSampleManager_Standalone
    COMMENT "Full qualification: all tests/benchmarks + all plugin formats")
