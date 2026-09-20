# NITE Submit categorized acceptance sweep v1

Validation date: 25 August 2026

The packaged CLI was exercised against the retained local corpus using dry-run
mode. No source PDF was renamed and no PDF output was created by this sweep.

| Category | PDFs | Dry-run | Review-required | Image-only | Written/failed/collision |
| --- | ---: | ---: | ---: | ---: | ---: |
| Student submissions (dissertations, reports, public examples) | 16 | 16 | 0 | 0 | 0 |
| University guidance/templates | 27 | 25 | 2 | 0 | 0 |
| Anonymous candidate fixture | 1 | 1 | 0 | 0 | 0 |
| Image-only fixture | 1 | 0 | 0 | 1 | 0 |
| Name-prohibited policy on real PDFs | 2 | 0 | 2 | 0 | 0 |
| Module-code-required template on real PDFs | 2 | 0 | 2 | 0 | 0 |

The two guidance/template review cases remain review-held because they are not
ordinary student submissions. The name-prohibited run reports `name_present`
and the module-code run reports `module_code` as the missing required field.

Reports are retained under:

`real_validation_corpus/test_results/acceptance_sweep_current/`

The run is reproducible with:

```sh
./tools/run_acceptance_sweep.sh
```

This is acceptance evidence, not a claim that every university uses the same
filename or document-identity rule.
