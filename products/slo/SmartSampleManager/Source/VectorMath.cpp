#include "VectorMath.h"

#if defined(__APPLE__)
 #include <Accelerate/Accelerate.h>
#endif

namespace VectorMath {

void multiply(const float* a, const float* b, float* out, int n)
{
#if defined(__APPLE__)
    vDSP_vmul(a, 1, b, 1, out, 1, static_cast<vDSP_Length>(n));
#else
    for (int i = 0; i < n; ++i) {
        out[i] = a[i] * b[i];
    }
#endif
}

float dotProduct(const float* a, const float* b, int n)
{
#if defined(__APPLE__)
    float result = 0.0f;
    vDSP_dotpr(a, 1, b, 1, &result, static_cast<vDSP_Length>(n));
    return result;
#else
    float result = 0.0f;
    for (int i = 0; i < n; ++i) {
        result += a[i] * b[i];
    }
    return result;
#endif
}

}
