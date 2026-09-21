cmake_minimum_required(VERSION 3.20)
project(kenn_dsp_native LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

find_package(Python COMPONENTS Interpreter Development.Module REQUIRED)
execute_process(
  COMMAND "${Python_EXECUTABLE}" -m nanobind --cmake_dir
  OUTPUT_VARIABLE nanobind_ROOT
  OUTPUT_STRIP_TRAILING_WHITESPACE
  RESULT_VARIABLE nanobind_result
)
if(nanobind_result)
  message(FATAL_ERROR "nanobind is required to build the optional KENN native module")
endif()
list(APPEND CMAKE_PREFIX_PATH "${nanobind_ROOT}")
find_package(nanobind CONFIG REQUIRED)

set(KENN_AUTOMIX_NATIVE_DIR
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../../../audio-technology/audio-analysis/audio_analysis/dsp_engine/native")

nanobind_add_module(
  _kenn_dsp_native
  kenn_dsp_native.cpp
  automix_bindings.cpp
  loudness_bindings.cpp
  "${KENN_AUTOMIX_NATIVE_DIR}/eq_kernel.cpp"
  "${KENN_AUTOMIX_NATIVE_DIR}/limiter_kernel.cpp"
  "${KENN_AUTOMIX_NATIVE_DIR}/phase_correlation_kernel.cpp"
  "${KENN_AUTOMIX_NATIVE_DIR}/smooth_envelope_kernel.cpp"
  "${KENN_AUTOMIX_NATIVE_DIR}/transient_threshold_kernel.cpp")
if(MSVC)
  target_compile_options(_kenn_dsp_native PRIVATE /W4 /permissive-)
else()
  target_compile_options(_kenn_dsp_native PRIVATE -Wall -Wextra -Wpedantic)
endif()
target_include_directories(_kenn_dsp_native PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}")
target_include_directories(_kenn_dsp_native PRIVATE "${KENN_AUTOMIX_NATIVE_DIR}")
option(KENN_USE_ACCELERATE "Use Apple Accelerate/vDSP for the spectral backend" ${APPLE})
if(KENN_USE_ACCELERATE)
  if(NOT APPLE)
    message(FATAL_ERROR "KENN_USE_ACCELERATE requires an Apple platform")
  endif()
  find_library(ACCELERATE_FRAMEWORK Accelerate REQUIRED)
  target_compile_definitions(_kenn_dsp_native PRIVATE KENN_HAS_ACCELERATE=1)
  target_link_libraries(_kenn_dsp_native PRIVATE "${ACCELERATE_FRAMEWORK}")
endif()
# On POSIX the extension is a shared library; on Windows the import library
# and the loadable `.pyd` are separate artifacts. Keep every platform's
# runtime payload inside the Python package so the wheel is importable without
# a post-build copy step.
install(
  TARGETS _kenn_dsp_native
  LIBRARY DESTINATION kenn/core
  RUNTIME DESTINATION kenn/core
  ARCHIVE DESTINATION kenn/core)
