# Audio calculators, draft for trying on the Mac — 13 October 2026

Branch `draft/audio-calculators`, not merged. Cloud session, Fake Live, stubbed model replies; nothing here says
how often real answers improve.

## Why

The specialist curriculum (KENN_PLAN.md, C4) asks KENN to "use existing deterministic calculations for numeric
results", and none existed for the everyday arithmetic producers ask for. Those figures had to come from the model's
memory, and the grounding gate refuses any figure the evidence does not print, so a correct "351.6 ms" for a dotted
1/8 at 128 BPM was cut from the answer as unsupported.

## What it does (`apps/backend/src/kenn/core/audio_calculators.py`)

From the producer's typed question only, it computes:

- note lengths at a tempo: straight, dotted and triplet note values in ms, plus the same as an LFO rate in Hz; a
  timing question with a tempo but no note value gets 1/4, 1/8, dotted 1/8, 1/8 triplet and 1/16;
- buffer latency: samples at a sample rate in ms;
- pitch: a frequency's nearest note and how many cents off it is, or a note's frequency, at A4 = 440 Hz;
- level: a dB change as amplitude and power gain factors, and the doubling/halving arithmetic (±6.02 dB amplitude,
  ±3.01 dB power), with an explicit line that perceived loudness is not that arithmetic.

The sentences go into the same tool-evidence text the specialist observations use (`_tool_evidence` in
`chat_answer.py`), so they appear in the prompt's readings block and allowed-figures list, and the gate accepts the
figures, on both the payload and stream paths. Nothing else in the answer path changed.

Deliberately left out: perceived loudness, and anything without one exact answer. Also left out: adding the
calculation to the template answer, so with the model off a calculation question still gets the plain template.
That would change what the template's own grounding and quality checks see, and needs its own look.

## Octave names: confirm in Live

Pitch answers give the MIDI note number, the scientific-pitch name (middle C = C4) and Live's label, one octave lower
(middle C = C3). Live's convention rests on Ableton forum posts, not Ableton documentation, so check it once in
Live's piano roll. KENN's own MIDI generation card (`midi_generation_chat.py`) names pitches in scientific pitch, so
a producer can see "C4" from KENN and "C3" in Live for the same key; that is a separate item, not changed here.

## Checks

- `test_audio_calculators.py`: 21 cases. Expected values were worked out by hand first; two of my own expectations
  were wrong (450 ms, not 225, for a dotted 1/8 at 100 BPM; 1.413, not 1.995, for +3 dB on amplitude), and the code
  was right both times.
- The answer-path contrast: the same model answer quoting "351.6 ms" keeps the figure with the calculator and loses
  it to the gate's figure cut without it. Dropping the calculation, or computing from the search query instead of
  the typed question, each fail a test.
- Full backend suite: 4849 passed, 137 skipped, 1 failed (the pre-existing typo-routing test, also red on clean
  `main` here).

## To try it on the Mac

Check out the branch with the index linked (as for the synonym draft), start the companion, and ask: "what delay time
is a dotted 1/8 at 128 BPM?", "how much latency is 256 samples at 44.1 kHz?", "what note is 110 Hz?", "what is -6 dB
as a ratio?". Merge when the answers read right and a probe run shows no new rejections.
