cmake_minimum_required(VERSION 3.22)

# A DAW loads native code into its own process. Ship one macOS bundle that can
# be loaded by both Apple Silicon and Intel hosts instead of relying on Rosetta.
if (APPLE AND NOT CMAKE_OSX_ARCHITECTURES)
    set(CMAKE_OSX_ARCHITECTURES "arm64;x86_64" CACHE STRING "macOS architectures for KENN plug-ins" FORCE)
endif()

project(KENNMixAssistant VERSION 0.1.0 LANGUAGES C CXX)

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
    COMPANY_NAME "Audio Engineering Company"
    BUNDLE_ID "com.audioengineeringcompany.kenn-mix-assistant"
    IS_SYNTH FALSE
    NEEDS_MIDI_INPUT FALSE
    NEEDS_MIDI_OUTPUT FALSE
    IS_MIDI_EFFECT FALSE
    EDITOR_WANTS_KEYBOARD_FOCUS FALSE
    COPY_PLUGIN_AFTER_BUILD FALSE
    PLUGIN_MANUFACTURER_CODE AECO
    PLUGIN_CODE KnMa
    FORMATS VST3 AU
    PRODUCT_NAME "KENN Mix Assistant")

juce_generate_juce_header(KENNMixAssistant)

target_sources(KENNMixAssistant PRIVATE
    Source/PluginProcessor.cpp
    Source/PluginEditor.cpp)

target_include_directories(KENNMixAssistant PRIVATE Source)
target_compile_definitions(KENNMixAssistant PRIVATE
    JUCE_WEB_BROWSER=0
    JUCE_USE_CURL=0
    JUCE_VST3_CAN_REPLACE_VST2=0)
target_link_libraries(KENNMixAssistant PRIVATE
    juce::juce_audio_utils
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
