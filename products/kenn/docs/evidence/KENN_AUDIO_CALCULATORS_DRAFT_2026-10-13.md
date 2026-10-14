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

## Review fixes, 14 October 2026

A read-only review found ways the calculator printed a wrong or unrequested figure. That matters more here than a
missing one: the gate accepts a calculated figure anywhere in the answer, so a spurious reading lets an invented
sentence through. Each fix below has a regression test that was written first and seen failing.

- A cut read as a boost: "reduce by 6 dB, what percent" gave +6 dB and 199.5%, and "a 3 dB pad" gave 141.3%. Cut
  words (cut, reduce, lower, attenuate, drop, down, pad) now make an unsigned dB negative (-6 dB = 50.1%, -3 dB =
  70.8%). Only a typed "+" or a boost word gives a boost factor. An unsigned dB with no direction word ("the 3 dB
  point of the filter", "what percent is 3 dB"), or with both, now gets no factor; 0 dB is unity either way.
  (`test_a_cut_is_worked_out_as_a_reduction`, `test_a_pad_is_a_cut`, `test_an_unsigned_db_with_no_direction_gets_no_factor`)
- "Gain" is accepted as a conversion target: "convert -3 dB to gain", "-6 dB as gain", "what gain is -6 dB",
  "-6 dB gain factor". "What gain should I set" is still not a conversion. (`test_gain_is_a_conversion_target`)
- A stated tuning ignored: "A4 at 432 tuning" was answered at 440. A stated reference other than 440 Hz ("A=442",
  "432 tuning", "tuned to 432 Hz") now gives no pitch figure at all, rather than computing at another reference.
  (`test_a_stated_tuning_other_than_440_gets_no_pitch_figure`)
- False triggers: a trigger word anywhere in the question converted any figure nearby ("cut 200 Hz ... what pitch is
  the vocal", a sampler called E4, a compressor's "ratio 4:1, threshold -18 dB", "time signature 7/8 at 140 bpm",
  "half time feel"). Pitch and level now need the conversion asked of the figure itself ("what note is 220 Hz",
  "how many Hz is A4", "-6 dB as a ratio", "what percent"); bare "time" no longer counts as a timing word; "half",
  "whole", "quarter" and "4th" count as note values only with "note" after them.
  (`test_a_figure_mentioned_beside_an_unrelated_question_gets_no_calculation`, `test_half_time_is_not_a_half_note`)
- Rounding: ties rounded to even, so a dotted 1/8 at 144 BPM (312.5 ms) read "about 312". All rounding is now
  half-up: "about 313 ms", and 1/8T at 128 BPM is 156.3 ms. (`test_an_exact_half_rounds_up`)
- No MIDI bound: 20 000 Hz was named MIDI note 135. A frequency outside MIDI 0-127 (about 8.2 Hz to 12.54 kHz) now
  gets no note. (`test_a_frequency_above_the_midi_range_gets_no_note`)

## Checks

- `test_audio_calculators.py`: 44 cases (21 original, all still passing, plus 23 from the review fixes). Expected
  values were worked out by hand first; two of my own expectations were wrong (450 ms, not 225, for a dotted 1/8 at
  100 BPM; 1.413, not 1.995, for +3 dB on amplitude), and the code was right both times.
- The answer-path contrast: the same model answer quoting "351.6 ms" keeps the figure with the calculator and loses
  it to the gate's figure cut without it. Dropping the calculation, or computing from the search query instead of
  the typed question, each fail a test.
- Full backend suite (14 Oct): 5168 passed, 175 skipped, 3 failed, all pre-existing and also red on clean `main`:
  the two `test_mixing_doctor.py` advisory tests and the typo-routing test.

## To try it on the Mac

Check out the branch with the index linked (as for the synonym draft), start the companion, and ask: "what delay time
is a dotted 1/8 at 128 BPM?", "how much latency is 256 samples at 44.1 kHz?", "what note is 110 Hz?", "what is -6 dB
as a ratio?". Merge when the answers read right and a probe run shows no new rejections.
