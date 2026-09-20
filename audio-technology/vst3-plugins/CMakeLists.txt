# CMake Build Configuration for Audio_Too JUCE VST3 / Audio Unit (AU) Native Plugin Suite
cmake_minimum_required(VERSION 3.22)
project(AudioToo_Plugins VERSION 2.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# JUCE framework submodule path (or fetch via FetchContent if building standalone)
include(FetchContent)
FetchContent_Declare(
    JUCE
    GIT_REPOSITORY https://github.com/juce-framework/JUCE.git
    GIT_TAG 8.0.2
)
FetchContent_MakeAvailable(JUCE)

# Enable VST3 and AU formats
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

target_sources(AudioToo_Reverb PRIVATE
    AudioToo_PluginWrapper.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../audio_analysis/audio_analysis/dsp_engine/native/reverb_full_kernel.cpp
)

target_include_directories(AudioToo_Reverb PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/../audio_analysis/audio_analysis/dsp_engine/native
)

target_link_libraries(AudioToo_Reverb PRIVATE
    juce::juce_audio_utils
)

add_subdirectory(SmartSampleManager)
add_subdirectory(MidiGenerator)

