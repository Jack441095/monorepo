cmake_minimum_required(VERSION 3.22)

# A DAW loads native code into its own process. Ship one macOS bundle that can
# be loaded by both Apple Silicon and Intel hosts instead of relying on Rosetta.
# A DAW loads native code into its own process. Build universal when requested
# or target the native host architecture on macOS.
option(KENN_BUILD_UNIVERSAL "Build universal binary (arm64;x86_64) on macOS" OFF)
if (APPLE)
    if (KENN_BUILD_UNIVERSAL)
        set(CMAKE_OSX_ARCHITECTURES "arm64;x86_64" CACHE STRING "macOS architectures for KENN plug-ins" FORCE)
    else()
        set(CMAKE_OSX_ARCHITECTURES "arm64" CACHE STRING "macOS architectures for KENN plug-ins" FORCE)
    endif()
endif()

project(KENNMixAssistant VERSION 0.1.0 LANGUAGES C CXX)

if (WIN32)
    # Audio Unit is a macOS format. Keep the Windows job focused on the
    # supported VST3 artifact instead of asking JUCE to configure an AU target
    # that cannot load on Windows.
    set(KENN_PLUGIN_FORMATS VST3)
else()
    set(KENN_PLUGIN_FORMATS VST3 AU)
endif()

if (NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
    set(CMAKE_BUILD_TYPE "Release" CACHE STRING "Choose the type of build" FORCE)
endif()

enable_testing()

# Deliberately disabled for shipped builds. Enable only for a disposable Live
# qualification build after the direct OSC writer has passed real
# confirmation/readback/undo evidence.
option(KENN_ENABLE_DIRECT_LIVE_WRITES "Enable explicitly confirmed direct C++ Live parameter writes" OFF)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

if (NOT TARGET juce::juce_audio_utils)
    include(FetchContent)
    FetchContent_Declare(JUCE
        GIT_REPOSITORY https://github.com/juce-framework/JUCE.git
        GIT_TAG 8.0.2)
    FetchContent_MakeAvailable(JUCE)
endif()

juce_add_plugin(KENNMixAssistant
    COMPANY_NAME "Shenrendao AI"
    BUNDLE_ID "com.shenrendao.kenn-mix-assistant"
    IS_SYNTH FALSE
    NEEDS_MIDI_INPUT FALSE
    NEEDS_MIDI_OUTPUT FALSE
    IS_MIDI_EFFECT FALSE
    EDITOR_WANTS_KEYBOARD_FOCUS TRUE
    COPY_PLUGIN_AFTER_BUILD FALSE
    PLUGIN_MANUFACTURER_CODE AECO
    PLUGIN_CODE KnMa
    FORMATS ${KENN_PLUGIN_FORMATS}
    PRODUCT_NAME "KENN Mix Assistant")

juce_generate_juce_header(KENNMixAssistant)

target_sources(KENNMixAssistant PRIVATE
    Source/PluginProcessor.cpp
    Source/PluginEditor.cpp
    Source/LocalCommandLanguage.cpp
    Source/LocalLivePlan.cpp
    Source/LocalAbletonOscProtocol.cpp
    Source/LocalAbletonOscProbe.cpp
    Source/LocalAbletonOscWriter.cpp)

target_include_directories(KENNMixAssistant PRIVATE Source)
target_compile_definitions(KENNMixAssistant PRIVATE
    JUCE_WEB_BROWSER=1
    JUCE_USE_CURL=0
    JUCE_VST3_CAN_REPLACE_VST2=0
    KENN_ENABLE_DIRECT_LIVE_WRITES=$<BOOL:${KENN_ENABLE_DIRECT_LIVE_WRITES}>)
target_link_libraries(KENNMixAssistant PRIVATE
    juce::juce_audio_utils
    juce::juce_gui_extra
    juce::juce_recommended_config_flags
    juce::juce_recommended_warning_flags)

# Realtime-thread concurrency stress test for AudioTooRealtimeCore (shared
# by every Audio Too plug-in). Not a plugin format -- a standalone
# executable that hammers analyse()/snapshot() from concurrent threads.
#
# Build with -DKENN_ENABLE_TSAN=ON to compile under ThreadSanitizer for a
# tool-verified answer on data races, not just a "ran without crashing"
# smoke test:
#   cmake -S studio/vst3_plugins/KENNMixAssistant -B build/kenn-tsan -DKENN_ENABLE_TSAN=ON
#   cmake --build build/kenn-tsan --target TestRealtimeThreadSafety
#   ./build/kenn-tsan/TestRealtimeThreadSafety
option(KENN_ENABLE_TSAN "Build KENNMixAssistant test targets with ThreadSanitizer" OFF)

add_executable(TestRealtimeThreadSafety
    Source/test_realtime_thread_safety_main.cpp)
# AudioTooRealtimeCore.h includes <JuceHeader.h> -- that's generated per-target
# by juce_generate_juce_header(KENNMixAssistant) above, into that target's own
# artefacts directory. Point this standalone executable at the same generated
# header rather than duplicating juce_generate_juce_header for a second target.
target_include_directories(TestRealtimeThreadSafety PRIVATE
    Source
    "${CMAKE_CURRENT_BINARY_DIR}/KENNMixAssistant_artefacts/JuceLibraryCode")
# JuceHeader.h is generated as a side effect of building KENNMixAssistant's
# own sources (juce_generate_juce_header ties the custom command to that
# target, not to a standalone always-available file) -- without this
# dependency, make has no reason to generate it before compiling this target.
add_dependencies(TestRealtimeThreadSafety KENNMixAssistant)
target_link_libraries(TestRealtimeThreadSafety PRIVATE
    juce::juce_audio_utils
    juce::juce_recommended_config_flags
    juce::juce_recommended_warning_flags)
if(KENN_ENABLE_TSAN)
    target_compile_options(TestRealtimeThreadSafety PRIVATE -fsanitize=thread -g -O1)
    target_link_options(TestRealtimeThreadSafety PRIVATE -fsanitize=thread)
endif()

# Integration check: constructs the real KENNMixAssistantAudioProcessor (the
# same class createPluginFilter() hands to a DAW) and calls its actual
# askKenn()/testKennConnection() methods against a live apps/backend/src/kenn/server.py
# -- proves the compiled binary, not just the source, talks to the real
# server contract. Links against the already-built KENNMixAssistant
# shared-code library (rather than recompiling PluginProcessor.cpp/
# PluginEditor.cpp here) because juce_add_plugin() injects JucePlugin_*
# macros only for its own target -- recompiling those sources in a plain
# add_executable would be missing them. Skips cleanly (exit 0) if no server
# is reachable; not run as part of the default build/test loop.
add_executable(TestServerIntegration
    Source/test_server_integration_main.cpp)
target_include_directories(TestServerIntegration PRIVATE
    Source
    "${CMAKE_CURRENT_BINARY_DIR}/KENNMixAssistant_artefacts/JuceLibraryCode")
target_link_libraries(TestServerIntegration PRIVATE
    KENNMixAssistant
    juce::juce_audio_utils
    juce::juce_gui_extra
    juce::juce_recommended_config_flags
    juce::juce_recommended_warning_flags)

# Focused integration check for the confirmation-gated Live command client.
# Kept separate from TestServerIntegration because generic chat has its own
# provider/index timing budget; this target proves the new C++ command path
# independently against the running local companion.
add_executable(TestCommandIntegration
    Source/test_command_integration_main.cpp)
target_include_directories(TestCommandIntegration PRIVATE
    Source
    "${CMAKE_CURRENT_BINARY_DIR}/KENNMixAssistant_artefacts/JuceLibraryCode")
target_link_libraries(TestCommandIntegration PRIVATE
    KENNMixAssistant
    juce::juce_audio_utils
    juce::juce_gui_extra
    juce::juce_recommended_config_flags
    juce::juce_recommended_warning_flags)

# Pure local language extraction test. This target intentionally has no JUCE,
# network, OSC, or model dependency: it proves the hosted plug-in can classify
# common Live commands on the UI/worker side before asking the companion for a
# fresh snapshot and guarded proposal.
add_executable(TestLocalCommandLanguage
    Source/LocalCommandLanguage.cpp
    Source/test_local_command_language_main.cpp)
target_include_directories(TestLocalCommandLanguage PRIVATE Source)
add_test(NAME KENN.LocalCommandLanguage COMMAND TestLocalCommandLanguage)

# Pure standard-OSC codec test used by the plug-in's serverless read-only
# liveness fallback. It does not open a socket or touch Live.
add_executable(TestLocalAbletonOscProtocol
    Source/LocalAbletonOscProtocol.cpp
    Source/test_local_ableton_osc_protocol_main.cpp)
target_include_directories(TestLocalAbletonOscProtocol PRIVATE Source)
add_test(NAME KENN.LocalAbletonOscProtocol COMMAND TestLocalAbletonOscProtocol)

# Loopback integration check for the plug-in's read-only direct OSC fallback.
# The fake endpoint replies only to song-level getter messages; no Live or
# external network state is required.
add_executable(TestLocalAbletonOscProbe
    Source/LocalAbletonOscProtocol.cpp
    Source/LocalAbletonOscProbe.cpp
    Source/LocalAbletonOscWriter.cpp
    Source/test_local_ableton_osc_probe_main.cpp)
target_include_directories(TestLocalAbletonOscProbe PRIVATE
    Source)
target_link_libraries(TestLocalAbletonOscProbe PRIVATE
    juce::juce_core
    juce::juce_recommended_config_flags
    juce::juce_recommended_warning_flags)
add_test(NAME KENN.LocalAbletonOscProbe COMMAND TestLocalAbletonOscProbe)

# Deterministic C++ read/plan parity for the first self-contained command
# slice. It creates no confirmation token and sends no Live mutation.
add_executable(TestLocalLivePlan
    Source/LocalCommandLanguage.cpp
    Source/LocalLivePlan.cpp
    Source/test_local_live_plan_main.cpp)
target_include_directories(TestLocalLivePlan PRIVATE Source)
add_test(NAME KENN.LocalLivePlan COMMAND TestLocalLivePlan)

# Numerical correctness and reference parity test for AudioTooRealtimeCore
add_executable(TestNumericalParity
    Source/test_numerical_parity_main.cpp)
target_include_directories(TestNumericalParity PRIVATE
    Source
    "${CMAKE_CURRENT_BINARY_DIR}/KENNMixAssistant_artefacts/JuceLibraryCode")
add_dependencies(TestNumericalParity KENNMixAssistant)
target_link_libraries(TestNumericalParity PRIVATE
    juce::juce_audio_utils
    juce::juce_recommended_config_flags
    juce::juce_recommended_warning_flags)

# Standalone realtime benchmark. Keep it as a first-class build target so the
# performance claim can be reproduced alongside the correctness checks.
add_executable(TestRealtimePerformance
    Source/test_realtime_performance_main.cpp)
target_include_directories(TestRealtimePerformance PRIVATE
    Source
    "${CMAKE_CURRENT_BINARY_DIR}/KENNMixAssistant_artefacts/JuceLibraryCode")
add_dependencies(TestRealtimePerformance KENNMixAssistant)
target_link_libraries(TestRealtimePerformance PRIVATE
    KENNMixAssistant
    juce::juce_audio_utils
    juce::juce_recommended_config_flags
    juce::juce_recommended_warning_flags)

add_test(NAME KENN.ServerIntegration COMMAND TestServerIntegration)
add_test(NAME KENN.CommandIntegration COMMAND TestCommandIntegration)
add_test(NAME KENN.NumericalParity COMMAND TestNumericalParity)
add_test(NAME KENN.RealtimeThreadSafety COMMAND TestRealtimeThreadSafety)
add_test(NAME KENN.RealtimePerformance COMMAND TestRealtimePerformance)

# The plug-in bundles are intentionally universal, but these local test
# executables do not need a second architecture.  Leaving the global
# arm64;x86_64 setting on them makes the Makefile lipo wrapper race/fail on
# some Command Line Tools installations.  Build tests for the host only so
# the normal all-target build remains deterministic while the shipped bundles
# stay universal.
if (APPLE)
    set_target_properties(
        TestRealtimeThreadSafety
        TestServerIntegration
        TestCommandIntegration
        TestLocalCommandLanguage
        TestLocalAbletonOscProtocol
        TestLocalAbletonOscProbe
        TestLocalLivePlan
        TestNumericalParity
        TestRealtimePerformance
        PROPERTIES OSX_ARCHITECTURES "")
endif()
