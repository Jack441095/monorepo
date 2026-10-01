# Wording triage: what KENN did not understand, once a week

**Status (30 Sept 2026):** the triage script is built and tested against a synthetic sample. **0 rows of real tester
wording have been through it**, because no tester has run a session yet (E2 in the engineering plan). The loop below
starts the week the first one does.

This is plan task B4. Its job is the second half: the log already exists, and clustering it does not.

## The log is already there

The app writes one every time KENN asks back or refuses, on the producer's own Mac:
`apps/backend/src/kenn/core/asked_log.py`, 300 rows, `0600`, at
`$KENN_ASKED_LOG` or `kenn/data/asked_log.jsonl` inside KENN's data folder. One row per ask or refusal, and it
fills in the tester's reply when the next message follows within 300 s:

```json
{"timestamp": 1759000000.0, "said": "lower the bass a bit", "kenn_said": "By how much? ...",
 "status": "clarification_required", "next_said": "down 2", "next_status": "proposal_ready"}
```

Three things to know before reading it:

- **It only ever holds misses.** A request KENN understood is not written at all, by design: it would be a record of
  everything a producer asked, which is not what a support file needs. So the log cannot tell you a rate. The scorer
  (`score_natural_phrasings.py`) owns rates, and this script never re-grades anything.
- **The opt-in is on the way out, not on the way in.** The rows are written automatically; the checkbox on the setup
  page ("Also include the N KENN didn't understand") only decides whether they are included in a diagnostics file
  that leaves the Mac. Nobody has to remember to switch logging on.
- **A correct parse is therefore absent, not hidden.** A row whose outcome says `right` (a scorer file) is counted in
  the report and never becomes a cluster.

## Getting the rows

The log stays on the producer's Mac. On the setup page, **Save diagnostics for support** with the "Also include the N
KENN didn't understand" box ticked writes one file, `kenn-diagnostics-<stamp>.json`, into `$KENN_DIAGNOSTICS_DIR` or
`.runtime/diagnostics` in the KENN data folder. The tester attaches that file; the rows sit under `asked_log` in it.

The triage script reads that whole file, so nothing has to be extracted by hand:

```bash
python3 tooling/scripts/triage_unparsed_requests.py ~/Downloads/kenn-diagnostics-20261007-181500.json
```

**Not** the support bundle (`build_support_bundle.py`). A bundle is built for sharing and by design never carries
typed text, so it has no `asked_log` in it.

Copy the rows out of the diagnostics JSON into a file of their own if you want to keep the weeks apart. Keep them out
of git: these are a real producer's words. A scorer's `--out` file is the other shape the script reads, and the only
one that carries `right` rows:

```bash
python3 tooling/scripts/score_natural_phrasings.py --out /tmp/holdout-score.json
python3 tooling/scripts/triage_unparsed_requests.py /tmp/holdout-score.json ~/kenn-asked-week1.jsonl \
  --out ~/triage-2026-10-07.txt
```

`--json` prints the structured report (`kenn.wording_triage.v1`) instead of the text one. `--examples N` changes how
many wordings each cluster shows (default 3).

To see the shape without a tester, the synthetic sample is in the repo and is marked as synthetic on every row:

```bash
python3 tooling/scripts/triage_unparsed_requests.py \
  tooling/data/synthetic_asked_log_sample_2026-09-30.jsonl
```

## Reading the report

Clusters are keyed on **what the parser got wrong**, not on how the sentence reads: which action it recognised and
which field it then asked for. `lower the bass a bit` and `pan the snare a bit` both end in "KENN asked for a number",
and they are separate clusters, because the pattern that would catch one is not the pattern that catches the other.
Ranked by rows, with the distinct-wording count beside it, so 20 copies of a producer's typo cannot look like the
week's biggest win.

Each cluster carries: the label, the real `live_intent.py` symbols that came closest, what the parser said was
missing, the shape (words, whether a number was present, whether a track resolved), the wordings, what KENN said
back, one **proposal**, and the test to add.

That last line matters. "I didn't catch a change to make there" is the generic answer: the producer learns nothing
and cannot reply with a number. "By how much?" is a real question. Same parser gap, different work. **A proposal is for a human. The script never edits `live_intent.py`.** It also never touches
Live: it forces `KENN_LIVE_BACKEND=fake` before importing the parser, so it is safe to run on the Mac where
`KENN_LIVE_BACKEND=osc` is set.

Four clusters are not rule fixes, and the report says so:

| Cluster | What it means |
|---|---|
| `refused` | The boundary worked. Count it; do not add a rule. |
| `no_action/transport` | "Kill playback", "roll the tape". The pinned policy call B2 owes an answer on. |
| `how_to`, `no_action/question` | A question, not a request. Check the router sent it to the notes route. |
| `asked_after_parsing` | The rules understand it and the gateway still asked. Look in `core/live_command.py`, not the parser. |

## The weekly round

1. **Friday, after the session.** The tester ticks the box and sends the diagnostics file.
2. **Triage.** Run the script on this week's rows. Read the top two clusters; ignore anything under 2 rows.
3. **One cluster, one sitting.** A cluster is worth a rule only when the wording carries the value. "Lower the bass
   a bit" carries no dB, and the right fix is a better question, not a default number: a guessed amount is a wrong
   plan, and a wrong plan is the failure the North Star counts at zero.
4. **Test first, then the rule.** Write the producer's sentence as a test on `FakeLiveBackend`, see it fail, then fix.
5. **Re-score.** `python3 tooling/scripts/score_natural_phrasings.py`. The Stage 1 gate is ≥ 95% correct on ≥ 500
   natural phrasings, and the holdout files that gate depends on are not edited from a triage report. New wording goes
   into a blind round (B1), not into the holdout.
6. **Commit** with the cluster size in the message, so the next week can tell whether the fix took.

Reading the counts: they must reconcile with the scorer. On
`tooling/data/natural_blind_drafted_2026-09-29_first_run.json` the script reports 101 correct, 42 asked, 3 wrong, and
the scorer's own `counts` block in that file says the same three numbers. If they ever differ, one of the two has
changed and the disagreement is the bug.
