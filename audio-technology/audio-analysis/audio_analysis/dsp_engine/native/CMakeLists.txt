cmake_minimum_required(VERSION 3.20)

project(kenn_automix_kernels LANGUAGES CXX)

add_library(kenn_automix_kernels STATIC
    eq_kernel.cpp
    limiter_kernel.cpp
    phase_correlation_kernel.cpp
    reverb_full_kernel.cpp
    reverb_kernel.cpp
    saturator_kernel.cpp
    smooth_envelope_kernel.cpp
    transient_threshold_kernel.cpp
)

add_executable(kenn_automix_kernel_smoke kernel_link_smoke.cpp)
target_link_libraries(kenn_automix_kernel_smoke PRIVATE kenn_automix_kernels)

include(CTest)
if(BUILD_TESTING)
    add_test(NAME kenn_automix_kernel_link_smoke COMMAND kenn_automix_kernel_smoke)
endif()

target_compile_features(kenn_automix_kernels PUBLIC cxx_std_17)
target_include_directories(kenn_automix_kernels PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}
)

if(MSVC)
    target_compile_options(kenn_automix_kernels PRIVATE /W4 /WX)
else()
    target_compile_options(kenn_automix_kernels PRIVATE -Wall -Wextra -Werror)
endif()
