cmake_minimum_required(VERSION 3.22)
project(KENNPeakCompare LANGUAGES C CXX)

# This offline tool reuses a caller-supplied JUCE checkout. It neither fetches a
# dependency nor changes the plug-in's linked modules or installed bundles.
if (NOT EXISTS "${KENN_JUCE_SOURCE_DIR}/modules/juce_dsp/juce_dsp.h")
    message(FATAL_ERROR "Set KENN_JUCE_SOURCE_DIR to the existing JUCE 8.0.2 checkout")
endif()
set(CMAKE_CXX_STANDARD 20)
set(JUCE_MODULES_ONLY ON CACHE BOOL "Configure cached modules without helper tools" FORCE)
add_subdirectory("${KENN_JUCE_SOURCE_DIR}" juce)
add_executable(KENNPeakCompare main.cpp)
target_include_directories(KENNPeakCompare PRIVATE ../../../plugins/kenn-vst3-au/Source)
target_compile_definitions(KENNPeakCompare PRIVATE
    JUCE_GLOBAL_MODULE_SETTINGS_INCLUDED=1 JUCE_USE_CURL=0 JUCE_WEB_BROWSER=0)
target_link_libraries(KENNPeakCompare PRIVATE juce::juce_dsp)
