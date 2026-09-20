# Thursday V2-H QA Independence Report

## Principle

The specialist that produces a change is never the sole authority declaring it
correct. `IndependentQA` attempts **falsification**, not confirmation, and holds
independent veto authority that no producing specialist can override.

## Veto conditions (fail closed)

* "tests passed" claim without machine-verifiable receipt (unverified evidence)
* candidate SHA ≠ claimed SHA; stale SHA vs current branch head
* claimed success with nonzero test exit code
* test-count decrease vs baseline (test/skip deletion) → TEST_INTEGRITY_VIOLATION
* benchmark threshold loosening → TEST_INTEGRITY_VIOLATION
* changed files outside declared plan boundaries (scope drift)

`QAReport.integration_permitted` is true only for `PASS` + `CLEAN`. A `FAIL`
verdict or integrity violation blocks integration even though it is not a veto.

## Independence mechanics

* Evidence is collected by a separate component (`evidence_collector.py`) from
  real process exit codes, real SHA lookups, real file hashes — never from
  specialist claims.
* Security review is triggered independently of the QA outcome and can veto
  when QA is silent (Z-30: security veto not overrideable).
* Post-integration QA (`post_integration_validator.py`) re-verifies the actual
  integrated branch state independently of pre-integration results.

## Benchmark + soak evidence

* Category J (QA independence): 15/15 PASS.
* Adversarial Z cases touching QA (Z-04…Z-07, Z-12, Z-17, Z-24): all rejected.
* Soak: 5,000 cycles — 564 vetoes, 533 integrity FAILs, 1,707 clean passes;
  unsupported claims accepted: **0**.
