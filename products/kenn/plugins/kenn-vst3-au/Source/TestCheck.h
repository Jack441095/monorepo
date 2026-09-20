#pragma once

#include <cstdlib>
#include <iostream>

// Native test executables must fail loudly regardless of build configuration.
// A bare assert() compiles to nothing when NDEBUG is defined (e.g. a Release
// build, which is also what KENN ships), so a CTest run built Release would
// silently "pass" every check without evaluating it. This macro always
// evaluates its condition and always aborts on failure.
#define KENN_TEST_CHECK(condition) \
    do { \
        if (!(condition)) { \
            std::cerr << "[KENN_TEST_CHECK FAILED] " << #condition \
                       << " at " << __FILE__ << ":" << __LINE__ << std::endl; \
            std::abort(); \
        } \
    } while (false)
