<!--
The checks that catch a bad change are cheap to run locally and easy to forget:

  cd products/kenn && bash tooling/scripts/ci_verification.sh
  python3 tooling/scripts/score_natural_phrasings.py --show wrong   # 0 wrong plans is the Stage 1 gate
  python3 tooling/scripts/check_personal_paths.py                    # no owner paths, no committed hostnames

The last one is not optional housekeeping: an absolute home path or a GPU hostname in a tracked file is a leak, and
AGENTS.md forbids both.
-->

## What this changes

<!-- One or two sentences. What behaviour changes for a producer, not a list of files. -->

## Why

<!-- The problem, or the measurement that says it needs doing. If this is a fix, the failing output. -->

## How it was verified

<!-- Name the commands you ran and paste the numbers, not "tests pass". -->

- [ ] `bash tooling/scripts/ci_verification.sh` from `products/kenn`
- [ ] `python3 tooling/scripts/score_natural_phrasings.py --show wrong` — **wrong plans: 0**
- [ ] The full backend suite run, with the counts
- [ ] If this touches the Live write path: the proposal → Apply → readback → receipt → undo path exercised on
      `FakeLiveBackend`, and the write is still one a producer can undo

## Safety

- [ ] No write to a real Ableton Live session. Daily work uses `FakeLiveBackend`; a real-Live run is an
      owner-scheduled supervised soak with its receipts committed.
- [ ] The model still never writes to Live. New capabilities go through proposal → Apply → readback → receipt → undo.
- [ ] No new capability is called supported without a measured gate. "It demos well" is not the gate.
- [ ] Nothing here commits a remote hostname, an IP address, a credential, a licensed Ableton manual, private audio,
      a user's stems or any personal session data.

## Numbers in the plans

- [ ] If this changes a measured number, the **North Star** (`products/kenn/docs/plans/KENN_NORTH_STAR_2026-09-24.md`)
      and the **four-week plan** are updated **in this same commit**, with the date and what was actually measured.
      A recorded number that has drifted from the tooling is worse than no number.
- [ ] Where a recorded number was wrong, it is corrected **in place** rather than appended to, and the correction says
      what was measured instead.

## Testing

- [ ] New behaviour has tests named for the behaviour or boundary they protect, not for the function.
- [ ] Boundary failures and isolation are covered, not only the happy path.