# KENN Standalone Migration Receipt

## Destination

`<LOCAL_VOLUME>/Shenrendao/KENN`

## Source units

- Product source candidate: `NITE_DSP/workspace/worktrees/root/kenn-m02-independent-source-v1/products/kenn`
- Product source candidate SHA: `83fd9fae7e76a286769c6133300efc06e7996681`
- Evaluation repository: `NITE_DSP/products/kenn-evaluation`
- Evaluation SHA: `7f76f620d9185d0f913e577dbfa2af8012529509`

## Included

- KENN source and desktop companion
- KENN chat service
- Mix Review boundary and tests
- AutoMix boundary and tests
- VST3 plugin candidate
- KENN product README and existing documentation
- KENN evaluation harness copied under `evaluation/`
- Beta sprint prompt

## Explicitly excluded

- The dirty `Audio_Too` working tree
- SLO, NITE Submit, Thursday, platform, and other NITE DSP products
- private audio, sample libraries, secrets, model weights, and generated state
- `.DS_Store`, `.pytest_cache`, `.runtime`, virtual environments, and Python caches

## Migration method

This is a clean standalone import into a new local Git repository. The source
candidate is preserved in its original location. The new repository starts
with a migration commit and retains the source SHAs above for traceability.

## Important limitation

The product candidate was extracted from the umbrella repository rather than
being a standalone Git history. The destination therefore has a clean initial
repository history plus this provenance receipt; it does not rewrite or alter
the original repository history.

The imported candidate also contains legacy adapter and documentation references
to `Audio_Too` and sibling-estate paths. These were preserved for traceability,
but the new repository is not yet runtime-independent. The beta sprint prompt
requires those dependencies to be removed, replaced with KENN-owned code, or
explicitly disabled before KENN can be called fully independent.
