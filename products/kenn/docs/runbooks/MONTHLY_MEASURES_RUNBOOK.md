# Monthly measures report

`tooling/scripts/monthly_measures.py` prints the North Star's "Measures reported
every month" list from one command. It runs the evaluation scripts that already
measure those things and quotes their output. It does not recompute, re-weight or
re-score anything, because a measure that quietly changes definition is the
failure the North Star's risk table calls "a gate quietly stops gating".

Run it from `products/kenn`:

```bash
PYTHONPATH=apps/backend/src:tooling python3 tooling/scripts/monthly_measures.py
```

It takes about 10 s on a clean checkout and writes nothing. The slowest script is
`e2e_demo_commands.py` at roughly 8 s; there is nothing here that needs caching
yet. Re-running it is safe and changes no tracked file.

## The exit code is the gate

Two measures are the North Star's required-zero gates, and the exit code is what
makes them gates rather than printouts:

| Exit | Meaning |
|---|---|
| 0 | Both required-zero measures were measured and both hold |
| 1 | A required-zero measure was violated |
| 2 | A required-zero measure could not be measured, so nothing is claimed about it |

Exit 2 is not a soft 0. A required-zero measure that nobody measured is not a
measure that passed, and treating it as one is the exact failure this report
exists to catch. On a fresh worktree the retrieval index is gitignored and absent,
so the uncited-answer count cannot be produced and the run exits 2. That is the
honest answer, not a bug to work around: build the index on the machine that keeps
it (`./ableton build`) and the same command closes the gate.

## Reading a measure

Every measure prints the same five lines, and a measure that could not be produced
prints the reason instead of a number.

- `status` — `measured`, or `not run` (the script could not produce it) or
  `not measured` (the thing it needs does not exist here, such as a runtime log).
  A `not ...` status is never accompanied by a number.
- `number` — the figure, quoted from the script. Never a blank, a zero or a guess.
- `denominator` — what the figure is out of. Read this before comparing months; the
  chat-coverage script's denominator is the cases it expected an answer to, not its
  whole corpus.
- `command` — the command that produced it, so any line can be re-run by hand.
- `measured` — when. A figure from a script with no timestamp of its own says the
  date it was run today; a figure from a receipt carries the timestamp the script
  wrote.

`quoted:` lines are the script's own output, kept verbatim. `note:` lines say why a
figure reads the way it does, and which measure a number does *not* stand in for.

## Which scripts it calls, and which it does not

Called as subprocesses, each one already the authority for its own number:

| Script | Measure it supplies |
|---|---|
| `score_natural_phrasings.py` | Understanding: right / total over the 505-phrasing holdout |
| `e2e_demo_commands.py` | Unauthorised writes and undo success, on the demo backend |
| `eval_chat_coverage.py` | Answers with no citable source, plus the coverage context |
| `evaluate_retrieval_modes.py` | recall@4 per retrieval fixture |
| `route_latency_report.py` | Latency, and how often the local model's answer lands |
| `adjudicate_human_review.py` | Answer quality, only with `--reviewer-a` and `--reviewer-b` |
| `evaluate_supervised_pilot.py` | Real-session writes and tester sign-off, only with `--pilot-log` |

Deliberately not called, though they exist in `tooling/scripts/`:

- `evaluate_ableton_manual_grounding.py` measures whether official-reference
  queries select local manual evidence. That is not one of the North Star's monthly
  measures, and with no manual indexed it prints `manual_not_indexed` and exits 0,
  which reads like a pass for something unmeasured. Run it on its own when the
  manual catalogue work lands.
- `check_notes_against_measurements.py` is a contradiction check over approved
  notes, useful before an index build, not a monthly figure.
- `evaluate_chat_brain.py` measures the answer-landing rate on the GPU box. The
  North Star asks for that rate per tester's Mac, and the box's seconds say nothing
  about a Mac.

Two measures cannot be produced from a script's stdout at all, and the report says
so rather than approximating them:

- **Latency by stage.** The route log stores one total per route. The planning, OSC
  round trip, readback and analysis split lives in `kenn.core.timing_stats`, which
  keeps 200 samples in memory and writes no file, so no script can print it.
  Recording those four stages in `route_log.record` is the fix, and it is a change
  to the product, not to this report.
- **The top grounding-gate warning.** The rate is countable from
  `answer_upgrade:rejected` rows. The reason is not: the warnings sit in
  `generation_validation.warnings` on the streamed answer payload and nothing writes
  them to disk. The standing guard against the gate failing open is
  `test_the_marker_prefix_is_not_a_grounding_input_anywhere`, not a number.

## Things the report will not do

- It does not create a retrieval index, a route log or a pilot log to fill a gap.
  Those are built by the product during real use, and a number derived from a
  fixture the report invented is worth less than an absent one.
- It does not reclassify an undo shortfall. KENN has no safe inverse for track
  creation, so those commands ask to undo rather than losing an undo. Undo success
  is reported against its 100% requirement but does not gate the exit code, because
  the North Star names only unauthorised writes and uncited answers as its two
  required-zero gates.
- It does not pick between the North Star's figure and the script's. Where they
  differ both are printed and the note says which is the older one. At the time of
  writing the North Star quotes 494 / 505 phrasings and the script reports 492 / 505
  over the same two files.

## Monthly checklist

1. Run the command on the machine that holds the index, and keep the printed output
   with the month's notes.
2. Read every `not ...` status. Each one is a measure that will not be reported this
   month, and most of them close by using KENN normally on a Mac.
3. Check `exit 0` before treating the month as clean. Exit 1 names the violated gate
   in the gate summary; exit 2 names the measure nobody could count.
4. To attach a receipt to the month, add `--receipt`. It writes
   `tooling/evaluation/results/KENN_MONTHLY_MEASURES_<date>.json` with schema
   `kenn.monthly_measures.v1`. Nothing is written without that flag.
5. Where a real supervised session happened, pass `--pilot-log <log>` (repeatable)
   so the real-Live write count and the tester's sign-off are on the record rather
   than left unmeasured.
