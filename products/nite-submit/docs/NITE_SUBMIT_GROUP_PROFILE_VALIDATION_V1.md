# NITE Submit group profile validation v1

Validation date: 25 August 2026

## Safety rule

Group filenames use the explicit template:

```text
{group_id}_{project_title}
```

NITE Submit accepts `Group ID`, `Group Number`, `Group Name`, `Team ID`,
`Team Number`, or `Team Name` labels, or a manual Group ID entered by the
user. Multiple student names remain separate candidates; they are never joined
into a guessed group identifier.

## Real-PDF dry run

Command:

```sh
artifacts/Submit-0.2.0-macOS.app/Contents/MacOS/nitesubmit-cli batch \
  real_validation_corpus/public_examples \
  --out real_validation_corpus/test_results/group_profile_validation.FdJaMw \
  --template '{group_id}_{project_title}' --dry-run
```

Result: `real_validation_corpus/test_results/group_profile_validation.FdJaMw/`

- 2 real PDFs inspected
- 2 review-required results
- 0 detected group IDs
- 2 explicit `group_id` gaps
- 0 filenames written

This is the expected safe result: the public Berklee examples contain student
names but no group identifier, so the Group ID + Project rule refuses to guess.
Entering an approved group ID manually is required before a group filename can
be previewed or written.
