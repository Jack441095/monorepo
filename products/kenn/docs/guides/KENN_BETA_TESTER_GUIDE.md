# KENN Internal Beta Tester Guide

**Beta scope: Mix Review (command-line) and Chat (local HTTP service).**
AutoMix, the desktop companion, the VST3 plugin's server-backed features,
and the VSCode extension are **not** part of this beta -- see
`docs/KENN_BETA_READINESS_REPORT.md` for why. This guide covers the two
workflows ready for you to try: analysing a local WAV file with Mix
Review, and asking Chat a mix-engineering question.

## Part 1: Mix Review

## What Mix Review can and can't tell you

KENN measures 7 things directly from the audio and reports each with
evidence, a confidence score, and a plain-language explanation:

- **Clipping** -- sustained runs of near-full-scale samples
- **Headroom** -- how close the loudest peak is to full scale
- **Silence / truncation** -- whether the file is effectively empty
- **Channel imbalance** -- left/right level difference (stereo only)
- **Phase / polarity / mono compatibility** -- left/right correlation and
  mono-sum cancellation (stereo only)
- **DC offset**
- **An approximate loudness estimate** -- an unweighted RMS proxy, *not* a
  calibrated LUFS meter

It explicitly does **not** evaluate masking, tonal/EQ balance, arrangement,
dynamics, genre fit, calibrated loudness (LUFS), or true peak -- every
report says so by name rather than staying silent about it. Treat this as a
narrow technical-issue checker, not a general mixing opinion.

It only accepts mono or stereo 16-bit/24-bit PCM WAV files. 32-bit float
WAV, MP3, and other formats are rejected with a clear error rather than
silently misread.

## Setup

1. Install Python 3.11+.
2. Mix Review includes a Python standard-library fallback, so no NumPy
   installation is required to run it. If you also want the optional
   accelerator and the test suite, install the repository requirements:
   ```sh
   pip install pytest
   ```
3. Confirm it works with the test suite:
   ```sh
   python3 -m pytest mix-review/tests -v
   ```
   You should see 24 passed. If you see any failures, stop and report them
   (see the support runbook) before analysing your own audio.

## Running an analysis

```sh
python3 mix-review/adapter.py /path/to/your/mix.wav
```

This prints a JSON receipt to stdout. Key fields to look at:

- `status`: `"completed"`, `"failed"`, or `"rejected"`. Only `"completed"`
  means analysis actually ran.
- `analysis.findings`: a list of 13 entries (7 measured + 6 explicitly
  not-evaluated). Each has `detected`, `severity`, `confidence`, `evidence`
  (the actual numbers), `explanation`, `suggested_next_step`, and
  `limitations`.
- `analysis.technical_rating`: a one-line summary.
- `analysis.limitations`: global caveats that apply to every finding.

Optional flags:
- `--mix-goal <text>` -- currently recorded in the receipt but does not
  change analysis behaviour.
- `--light` -- recorded in the receipt; the engine does not yet vary its
  measurement depth based on this flag.
- `--no-bands` -- recorded in the receipt; per-frequency band analysis is
  not implemented in this build (see `not_evaluated_fault_families`).

## What "safe" means here

- Your audio is read into memory only for the duration of the analysis. It
  is never written to disk by the adapter, never uploaded, and never sent
  over the network (`audio_uploaded: false`, `external_network: false`,
  `storage: "memory_only"` in every receipt).
- A SHA-256 hash of your file is recorded in the receipt so a result can be
  tied back to the exact file later, without KENN retaining the audio
  itself.
- Nothing about your mix is ever modified. Mix Review is read-only by
  design; there is no "apply" or "export" step in this beta.

### What to report (Mix Review)

Please report, for each file you test:
1. The file (or a description of it, if you'd rather not share the audio)
   and what you expected KENN to flag, if anything.
2. The full JSON receipt.
3. Whether the findings matched your own listening/technical judgment --
   including false positives (flagged something that wasn't actually a
   problem) and false negatives (missed something you could hear/measure).

## Part 2: Chat

Chat answers text mix-engineering questions from a real, cited knowledge
base of 232 approved notes (mostly Ableton device workflows, mixing/
mastering fundamentals, and Wwise game-audio integration). It does **not**
accept audio, and it never analyses or alters anything -- it's pure
text-in, text-out.

**Current limitation, be aware:** retrieval is keyword-based (BM25) only.
Semantic/paraphrase understanding isn't active yet (the model download for
that hasn't been done), so a question using different words than the
notes' vocabulary may not match even if the answer exists. Try rephrasing
with more specific audio-engineering terms if you get an abstention you
didn't expect.

### Running it

The knowledge index is generated, not committed to git -- build it once
after cloning (and again any time notes under `apps/backend/src/kenn/Training_Data_Notes/`
change):

```sh
pip install -r requirements.txt
python3 apps/backend/src/kenn/main.py build
```

You should see `Built index version ... with 1104 chunks` and
`Notes: 232 indexed, 12 skipped` (the 12 are unreviewed drafts not yet marked
`Status: Approved`). Then start the chat service:

```sh
cd chat
cp .env.example .env   # review the defaults, no values need to be filled in
uvicorn app:app --reload --port 8000
```

Then, from another terminal:
```sh
curl -X POST http://127.0.0.1:8000/kenn/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "Why does my mix collapse when I check it in mono?"}'
```

Key response fields:
- `found`: `true` if KENN located and returned a grounded answer; `false`
  means it abstained (see `diagnostic_reason`).
- `sources`: the note file(s) the answer is drawn from.
- `confidence`: KENN's own confidence in the match, not a guarantee of
  correctness.
- `llm_enabled` (on `/health`): always `false` in this beta -- every answer
  is retrieved and templated from the notes, not generated freeform.

### What "safe" means here

- No audio is ever accepted (`audio_uploaded: false` on every response;
  requests with an `audio` field are rejected with HTTP 422).
- No LLM is used (`AUDIO_TOO_LLM_ENABLED=0` is enforced in code before any
  KENN module loads, not just by configuration).
- Nothing is ever modified -- chat only reads its local knowledge index.

### What to report (Chat)

For each question you try:
1. The exact question text.
2. Whether it answered or abstained, and whether that was the right call.
3. If it answered: whether the cited source(s) actually support the
   answer, and whether the answer itself was accurate/useful.

Both sets of feedback are exactly what's needed to move these from
"live-verified to work" to "qualified" -- see the gap matrix. See
`docs/KENN_BETA_SUPPORT_RUNBOOK.md` for where to send it and what to do if
something breaks.

## Note for VST3/AU plugin integration work (not a tester workflow)

`apps/backend/src/kenn/server.py` -- the full local companion server the plugin's
"Ask KENN" feature is designed to call -- now also runs standalone
(`python3 apps/backend/src/kenn/server.py`, defaults to `http://127.0.0.1:8090`,
same `/api/ask` behaviour as Chat above plus `/api/health`). It's
loopback-only by design and aimed at developers wiring up the plugin
integration, not at beta testers directly -- most of its other routes
(Ableton hardware control, stem separation, AutoMix upload, voice
synthesis) remain unimplemented and return a clean error if hit. See
`docs/KENN_BETA_GAP_MATRIX.md` GAP-04 for exactly what works.
