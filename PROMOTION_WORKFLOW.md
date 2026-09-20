# Platform promotion workflow

The platform monorepo is the canonical whole-product source for NITE DSP.
Product and integration work lives under `products/` and shared platform code
lives at the repository root.

`Nite-DSP/colloidal-cyclone` is a focused KENN collaboration/release surface,
not a mirror of this repository. Promote only a reviewed, KENN-scoped change
to it. The receiving PR must record:

- source commit SHA and source path;
- the exact files or feature scope being promoted;
- tests run and any platform-only tests not applicable;
- intentional differences introduced by the focused layout.

Do not copy the entire monorepo, generated build workspaces, local corpora,
model weights, secrets, or agent metadata into the focused repository.

The current `slo/eval-feat-ai-perf-v1` branch preserves the latest experimental
KENN/SLO implementation. It must remain a review branch until its import and
test-collection failures are repaired; it is not a release baseline.
