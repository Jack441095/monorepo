# Five-turn conversations, first run with the model — 3 October 2026

Recorded source: `ce8e2a49` plus the new runner (`tooling/scripts/run_conversation_cases.py`) and its cases file
(`apps/backend/src/kenn/evals/five_turn_conversations.json`). The [numeric receipt](KENN_C3_FIVE_TURN_FIRST_RUN_2026-10-03.json)
is the raw output of one run. Answer text is model prose and stays out of the repo; the findings below describe it in
our words.

Same Mac, model and index as the C1 runs (Ollama `kenn-brain-qwen3-8b`, index `v-db8c6334cf63`), FakeLive, temp chats
and database, `KENN_LLM_CACHE=0`, stream surface, nothing else heavy running. Six scripted conversations of five turns
each, run once. History is built the way the browser companion builds it: the earlier user turns and the answers KENN
gave. The cases hold questions only, no expected text.

Covered: anaphora, corrections, topic changes, partial requests, read-only against action, and asking about a job that
never ran. Not covered: two-track choices, project switching, cancel and restart as a real flow, and the UI delivery
path. C3 stays unticked.

## Counts

| | turns |
| --- | ---: |
| Total | 30 |
| Went to the model | 24 |
| Accepted | 12 |
| Rejected by the measurement guard | 11 |
| Stream timed out | 1 |
| Never reached the model (clarify, controller route, out of scope, template) | 6 |
| Runner errors | 0 |

- Accepted answers took 13.2 to 58.0 s, median 37.1 s. One of the 24 model turns was accepted within 15 s. The
  single-question stream runs had a median of 18.9 s, so these are about twice as slow. We did not look for the cause
  (longer prompts with history, machine state, or a slow stretch); one run cannot separate them.
- 11 of the 12 rejections were unsupported measurements (ms values, kHz and Hz cuts, dB and dBFS levels, -14 LUFS).
  Eleven of 24 is a higher guard rate than the single-question runs, where it was 4 to 7 of 29.

## What the conversations showed

Read from the first part of each answer, not every word, and from one run.

- **Follow-ups that lose the thread.** `used_history` is decided by wording (`should_use_history`, `is_followup_query`).
  "And the attack?" after a sidechain-on-bass answer had it false and got generic compressor advice. "No, on the drum
  bus instead." had it false and got drum bus steps with no limiter in the part we read. "Anything else I should check before I
  touch the EQ?" had it false. The flag is not a clean measure of what the model saw, because "The snare." had it
  false and still got an answer about making the snare bigger; we did not trace why.
- **A correction is answered as a new question.** "Sorry, it is the acoustic guitar that is muddy, not the vocal."
  routed to the controller and got a canned low-end session reading plus an offer to add an EQ, with no mention of the
  guitar. The first turn of that script ("My vocal sounds muddy in the mix.") took the same controller route in 0.05 s
  without calling the model; we did not read what it said.
- **Clarify forgets the conversation.** "What would you try first?" after the snare and "without making it louder"
  turns, and "What was the problem with it?", both got the generic "mix problem, Ableton, mastering…" menu even
  though history was present.
- **An analysis that never ran was described.** With no mix analysis anywhere in the session, "How did the analysis of
  my mix go?" got an accepted model answer written as if one had run, with a cited -18 dB figure, and "Run it again."
  returned essentially the same text. The guard checks measurements against sources, not whether the job exists, so it
  passed. This is the worst result in the run.
- **Internal notes reach the user.** After "Cancel that, I will do it myself.", the search query carried the previous
  question rather than the cancel, and the served template explained the AutoMix instrument-rules table by file and
  function name. The model's answer had been rejected on a dBFS value, so this is the template, not the model.
- **Read-only against action held in the part we read.** "Put a limiter on the master for me." got mastering advice
  and did not claim a change. It was a rejected-answer template, so this says little about the model.
- **Topic changes.** "What do I need to export stems for a client?" and the loudness question both carried the drum
  reverb question into their search query. The return to "the drum reverb" had no history, and was answered as Ableton
  steps. Their answers were not read closely enough to say whether the carried context did harm.

## What this does not cover

One run, no repeat, and the model is not deterministic. The answers were read for the turns above only. No judge, no
expected text, so "lost the thread" is our reading. FakeLive and Live-closed. Nothing here changes the 15 s gate result.
Fixes are not attempted yet; the plan item stays open.
