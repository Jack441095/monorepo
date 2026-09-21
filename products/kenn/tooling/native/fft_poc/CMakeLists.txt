cmake_minimum_required(VERSION 3.20)
project(kenn_fft_poc LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_executable(kenn_fft_poc fft_poc.cpp)
target_compile_options(kenn_fft_poc PRIVATE -Wall -Wextra -Wpedantic)

add_executable(kenn_fft_core_contract fft_core_contract.cpp)
target_compile_options(kenn_fft_core_contract PRIVATE -Wall -Wextra -Wpedantic)

include(CTest)
if(BUILD_TESTING)
  add_test(NAME kenn_fft_poc_smoke COMMAND kenn_fft_poc --iterations 4)
  add_test(NAME kenn_fft_core_contract COMMAND kenn_fft_core_contract)
endif()
