# Recovered AutoMix native kernels

These sources were restored from `origin/main` at commit
`f4a90d2c603b56f6088d7e0d2c8f2bd7f402c8f1` while qualifying the KENN C++ DSP
plan. They are preserved here as a recovery boundary; they are not yet wired
into the current AutoMix Python worker or the `products/kenn` nanobind wheel.

Build a standalone archive with:

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release
ctest --test-dir build --output-on-failure
```

The CTest smoke links and calls the recovered EQ, limiter, smoothing/gate,
transient-threshold, reverb, saturator, and correlation entry points with
deterministic buffers. It verifies finite output and zero-lag correlation
without attaching these kernels to the current AutoMix worker.

From the KENN product root the same target is available as
`make automix-kernel-build`; set `CMAKE=/opt/homebrew/bin/cmake` on hosts where
the default PATH selects an incompatible x86_64 CMake binary.

Before enabling any kernel, recreate its Python reference parity test and
measure the complete AutoMix request. The historical audit rejected direct
phase correlation and marginal reverb/saturator primitives; see
`products/kenn/docs/research/CPP_DSP_PHASE4_AUTOMIX_KERNEL_RECEIPT.md`.
