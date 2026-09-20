cmake_minimum_required(VERSION 3.22)
project(MidiGenerator VERSION 1.0.0 LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

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

juce_add_plugin(MidiGenerator
    COMPANY_NAME "Audio Engineering Company"
    BUNDLE_ID "com.audioengineeringcompany.midigenerator"
    IS_SYNTH FALSE
    NEEDS_MIDI_INPUT FALSE
    NEEDS_MIDI_OUTPUT TRUE
    IS_MIDI_EFFECT TRUE
    EDITOR_WANTS_KEYBOARD_FOCUS FALSE
    COPY_PLUGIN_AFTER_BUILD TRUE
    PLUGIN_MANUFACTURER_CODE AECO
    PLUGIN_CODE MdGn
    FORMATS VST3 AU
    PRODUCT_NAME "MIDI Generator"
)

juce_generate_juce_header(MidiGenerator)

target_sources(MidiGenerator PRIVATE
    Source/PluginProcessor.cpp
    Source/PluginEditor.cpp
    Source/MidiGeneratorEngine.cpp
    Source/NoteRollComponent.cpp
)

target_include_directories(MidiGenerator PRIVATE
    Source
)

target_compile_definitions(MidiGenerator PUBLIC
    JUCE_WEB_BROWSER=0
    JUCE_USE_CURL=0
    JUCE_VST3_CAN_REPLACE_VST2=0
)

target_link_libraries(MidiGenerator PRIVATE
    juce::juce_audio_utils
)

target_link_libraries(MidiGenerator PUBLIC
    juce::juce_recommended_config_flags
    juce::juce_recommended_lto_flags
    juce::juce_recommended_warning_flags
)
