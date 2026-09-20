# KENN Hugging Face Dataset Intake Plan

**Review date:** 2026-09-05

**Status:** research candidates only; no external dataset is currently imported, trained, or bundled with KENN.

The machine-readable registry is [`apps/backend/src/kenn/training/huggingface_dataset_candidates.json`](apps/backend/src/kenn/training/huggingface_dataset_candidates.json), and it can be checked without network access with `PYTHONPATH=.:source python3 scripts/audit_kenn_dataset_manifest.py`.

When a legally cleared local JSONL export is eventually available, [`scripts/prepare_kenn_external_text_sample.py`](scripts/prepare_kenn_external_text_sample.py) maps caption/QA/aspect fields into KENN's bounded text-only record schema. The separate `audit_kenn_external_dataset_records.py` command must then pass before the sample can be considered for research evaluation.

## Decision in one sentence

Hugging Face is useful for KENN's music-understanding, perception, MIDI, and evaluation layers, but the Ableton Live control lane must remain grounded in KENN-owned, capability-bound, human-reviewed examples.

This is an engineering intake plan, not legal advice. A dataset card is evidence about a repository, not a blanket licence for every underlying audio file, linked source, annotation, or model-generated derivative.

## Candidate inventory

| Candidate | KENN lane | What it can teach or measure | Licence / access finding | Initial decision |
| --- | --- | --- | --- | --- |
| [NVIDIA MF-Skills](https://huggingface.co/datasets/nvidia/MF-Skills) | perception + music knowledge | Structured captions and QA about tempo, key, structure, instrumentation, harmony, mood, and production | NVIDIA OneWay Noncommercial; access request; audio is represented by source IDs and carries separate source terms | Research-only text/annotation experiments; do not put in a commercial release without a separate clearance |
| [Google MusicCaps](https://huggingface.co/datasets/google/MusicCaps) | perception + evaluation | Musician-written aspects and captions for sonic attributes such as instruments, timbre, mood, and arrangement | CC BY-SA 4.0 for the dataset card's dataset; audio must be retrieved from YouTube and has separate source considerations | Good small pilot for caption-to-feature evaluation; keep audio retrieval out of the product pipeline until cleared |
| [MTG-Jamendo](https://huggingface.co/datasets/m-a-p/MTG/blob/main/mtg-jamendo-dataset/README.md) | perception | Genre, instrument, and mood/theme tagging; over 55,000 tracks and 195 tags are described in the card | Code Apache-2.0, metadata CC BY-NC-SA 4.0, audio has individual Creative Commons terms | Use annotations for a research classifier; do not assume the audio is commercially reusable |
| [Lakh MIDI](https://huggingface.co/datasets/mimbres/lakh_full) | symbolic MIDI | Rhythm, harmony, note density, phrase structure, and MIDI rendering checks | The Hub mirror reports CC BY-NC-SA 4.0; it is a mirror of the original collection | Research-only MIDI experiments; never ship its files or weights without clearance |
| [MAESTRO v3](https://huggingface.co/datasets/projectlosangeles/maestro-v3.0.0) | symbolic MIDI + timing | High-quality aligned piano audio/MIDI and performance timing | The listed repository reports CC BY-NC-SA 4.0; verify original source terms before use | Useful for timing and MIDI evaluation, not a default commercial training source |
| [CMI-Bench](https://huggingface.co/datasets/nicolaus625/CMI-bench/blob/main/README.md) | evaluation only | Instruction-following tests for genre, emotion, instruments, captioning, pitch, key, lyrics, melody, and beat tracking | CC BY-NC 4.0, research/evaluation intent, and aggregated source datasets retain their own terms | Keep in a quarantined evaluation environment; do not train on its test audio |
| [Music-Instruct](https://huggingface.co/datasets/m-a-p/Music-Instruct/tree/main) | knowledge baseline | General music instruction and question-answering patterns | The repository page reports CC BY-NC 4.0 | Optional research baseline only; not Ableton-control supervision |

The inventory intentionally does not treat community claims such as “god-level producer” datasets as trusted training data. A dataset that contains opaque provenance, hidden reasoning tags, mixed DAW claims, or no clear licence metadata is a review candidate at most, not an input to KENN.

## How each lane connects to KENN

### 1. Ableton control lane — first-party and deterministic

This lane produces typed plans such as:

```json
{
  "action": "set_device_parameter",
  "track_name": "4-Audio",
  "device_name": "EQ Eight",
  "parameter_name": "2 Gain A",
  "value": -3.0,
  "unit": "dB"
}
```

Training examples must be generated from KENN's own intent/parser contracts, exact Live snapshots, device capability matrix, and reviewed user wording. External music datasets may suggest terminology or provide paraphrase ideas, but they must never create an OSC action, widen an allowlist, or override deterministic refusal/confirmation rules.

### 2. Music knowledge lane — licensed text and annotations

Use captions, QA, and reviewed text to improve explanations of arrangement, timbre, mixing, mastering, and production decisions. These records should be labelled as advisory knowledge and kept separate from the action schema.

### 3. Perception lane — audio features, not commands

Use tags/captions to evaluate or improve feature extraction such as instrumentation, mood, density, spectral character, and structure. KENN should report measured evidence and confidence; a caption dataset must not be treated as proof that a particular EQ or compressor change is correct.

### 4. Symbolic/MIDI lane — bounded artefacts

MIDI datasets can improve rhythm, harmony, phrase, and timing models used by AudioGen/MIDI workflows. All generated MIDI remains an explicitly bounded artefact with provenance, event limits, and a separate audition/import confirmation boundary.

### 5. Evaluation lane — held out and quarantined

CMI-Bench and similar collections belong in evaluation-only storage. Never use a benchmark's test examples for supervised training, and preserve source-dataset terms when a benchmark aggregates other corpora.

## Intake gate before downloading or training

1. Record the exact Hub repository, commit/revision, dataset-card URL, access date, declared licence, original-source licence, and whether files are audio, MIDI, metadata, captions, or generated text.
2. Classify the intended use as `commercial`, `research_only`, `evaluation_only`, or `blocked`. If the most restrictive underlying term is unknown, use `blocked`.
3. Download only an allow-listed subset into an isolated staging directory. Do not copy arbitrary dataset files into the KENN repository or onto the Ableton machine.
4. Hash every accepted file and retain provenance next to the derived record. Keep raw media out of git.
5. Scan text for prompt injection, hidden reasoning tags, duplicated boilerplate, unsupported plugin claims, and instructions that attempt to mutate the host.
6. Normalize into a lane-specific schema. Do not mix command plans, production advice, audio captions, and MIDI events in one training file.
7. Deduplicate against KENN's holdout and current command corpus. A paraphrase is not automatically a valid command label.
8. Require human review for action-adjacent records and run the existing parser/validator, mechanical-expansion audit, deterministic agreement check, and shadow model contract gate.
9. Train and evaluate offline. Promotion requires licence approval, held-out improvement, no safety regression, and explicit product sign-off.

## Recommended sequence

### Phase A — no external model training yet

Use MusicCaps and selected MF-Skills text annotations to build a small, provenance-preserving perception/knowledge evaluation set. Use CMI-Bench only as a held-out evaluator. This measures whether external data helps before spending GPU time.

### Phase B — controlled research adapters

If the licence permits the intended use, train separate adapters for `music_knowledge`, `audio_perception`, and `midi_structure`. Keep the Ableton command adapter separate and continue to evaluate it against the exact KENN validator and sealed holdout.

### Phase C — commercial-cleared data

For a distributable KENN product, prioritize user-owned sessions, opt-in anonymized command logs, KENN-generated synthetic cases, permissively licensed technical documentation, and newly commissioned human examples. These are more valuable for reliable Ableton control than a much larger generic music corpus.

## Current recommendation

Do not bulk-download or train on the Hugging Face candidates yet. First create a small, isolated manifest and run a text-only, licence-labelled evaluation. The likely highest return is:

1. KENN-owned command examples for Live control.
2. MusicCaps-style captions for audio-language evaluation.
3. A cleared set of production/mixing explanations for advisory responses.
4. Separate, legally cleared MIDI data for AudioGen/MIDI features.

This preserves the architecture that is already working: the model may improve KENN's language and musical reasoning, while KENN's deterministic capability matrix, confirmation boundary, readback, replay protection, and undo remain authoritative.
