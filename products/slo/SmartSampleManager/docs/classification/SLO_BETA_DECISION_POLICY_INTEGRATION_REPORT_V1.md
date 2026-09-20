# SLO Beta Decision Policy — Integration Report V1

## The gap this closes

SLO already had a **Sort Library** feature that physically moves or copies files
into category folders based on `instrumentType`. It had a Copy/Move confirmation
dialog — but **no quality gate at all**. Every processed sample was sorted,
including classes the measurements say are unsafe.

Concretely: a `Percussion` file has **15.4% measured precision**. Sort Library
would have relocated it into a `Percussion` folder — roughly five wrong moves
for every right one. Impulse responses would have been filed as Kicks.

## What was integrated

**`Source/BetaDecisionPolicy.h`** — a pure, side-effect-free header mirroring
the Python policy. Tiers come from measured collection-held-out precision, not
intuition.

**Gate in `SampleManagerEngine::reorganizeSamples()`** — before any file is
touched, the policy decides. Non-eligible files are skipped and counted in
`sortSkippedByPolicy`, surfaced through `SortLibraryProgress` so "SLO sorted
fewer files than I have" is explained rather than mysterious.

**`SampleManagerEngine::previewBetaSort()`** — a `const` preview returning
counts per action. Reads state, touches no file. This is what the beta UI calls
*before* the user agrees to anything.

**Defaults to ON** (`betaPolicyGateEnabled{true}`). Disabling it is a deliberate
explicit act, not a config drift.

## Auto-rename is preview-only in beta

`BetaAction::AutoRenameEligible` means *eligible for a rename preview*, and the
decision still carries `requiresApproval = true`. The name of the enum says
`Eligible` for exactly this reason — nothing in the codebase can read it as
permission to mutate.

The existing Copy/Move confirmation remains, so a sort now requires **two**
independent gates: the policy must find a file eligible, and the user must
confirm the operation.

## Verification

The app **builds clean** (`cmake --build build --target SmartSampleManager`).

| test | result |
|---|---|
| `test_beta_decision_policy_main.cpp` | 17/17 pass |
| `test_beta_sort_gate_main.cpp` | 6/6 pass |

The gate test runs a realistic 11-file library slice: **3 eligible, 8 left
exactly where the user put them**, with explicit assertions that no Percussion
file, no impulse response and no misleading-token file is ever eligible — and
that raising confidence from 0.0 to 1.0 never makes Percussion eligible.

## One design decision worth recording

`dbLock` was made `mutable` so `previewBetaSort()` can be `const`. Const-ness
here is a safety property, not style: a preview that cannot mutate engine state
cannot accidentally become an action.
