cmake_minimum_required(VERSION 3.22)
project(AudioToo_Reverb VERSION 1.0.0 LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# JUCE CMake target setup
add_subdirectory(JUCE)

juce_add_plugin(AudioToo_Reverb
    COMPANY_NAME "Audio Engineering Company"
    IS_SYNTH FALSE
    NEEDS_MIDI_INPUT FALSE
    NEEDS_MIDI_OUTPUT FALSE
    IS_MIDI_EFFECT FALSE
    EDITOR_WANTS_KEYBOARD_FOCUS FALSE
    COPY_PLUGIN_AFTER_BUILD TRUE
    PLUGIN_MANUFACTURER_CODE AECO
    PLUGIN_CODE AtRv
    FORMATS VST3 AU
    PRODUCT_NAME "AudioToo Reverb"
)

target_sources(AudioToo_Reverb
    PRIVATE
        Source/PluginProcessor.cpp
        ../../audio_analysis/audio_analysis/dsp_engine/native/reverb_full_kernel.cpp
)

target_compile_definitions(AudioToo_Reverb
    PUBLIC
        JUCE_WEB_BROWSER=0
        JUCE_USE_CURL=0
        JUCE_VST3_CAN_REPLACE_VST2=0
)

target_link_libraries(AudioToo_Reverb
    PRIVATE
        juce::juce_audio_utils
    PUBLIC
        juce::juce_recommended_config_flags
        juce::juce_recommended_lto_flags
        juce::juce_recommended_warning_flags
)
