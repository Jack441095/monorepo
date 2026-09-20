cmake_minimum_required(VERSION 3.16)
project(disksweep VERSION 0.1.0 LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
# NOTE: if your cmake is an x86_64 Intel binary on an arm64 box with an
# arm64-only CLT, `project()` fails in xcrun. Use /opt/homebrew/bin/cmake
# (arm64) or compile directly:
#   /usr/bin/clang++ -std=c++17 -Wall -Wextra scanner/main.cpp -o build/disksweep-scanner
add_executable(disksweep-scanner scanner/main.cpp)
target_include_directories(disksweep-scanner PRIVATE scanner)
add_executable(disksweep-policycheck scanner/policycheck.cpp)
target_include_directories(disksweep-policycheck PRIVATE scanner)
add_executable(disksweep-parity scanner/parity.cpp)
target_include_directories(disksweep-parity PRIVATE scanner)
add_executable(disksweep-helper privileged-helper/helper.cpp)
target_include_directories(disksweep-helper PRIVATE scanner)
if(APPLE)
  foreach(t disksweep-scanner disksweep-policycheck disksweep-parity disksweep-helper)
    target_compile_options(${t} PRIVATE -Wall -Wextra)
  endforeach()
endif()
include(CTest)
add_test(NAME policycheck COMMAND disksweep-policycheck)
