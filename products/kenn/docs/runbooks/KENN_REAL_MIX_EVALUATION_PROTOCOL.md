# KENN real-mix evaluation protocol

## Purpose and boundary

This protocol measures whether KENN's Mix Review findings are correct and
useful on consented real material. It is separate from the synthetic detector
benchmark. Source audio and completed manifests remain outside Git; generated
packets contain hashes and review evidence, never audio bytes or audio paths.

The framework cannot supply consent, ground truth, listening judgment, or
reviewer independence. Humans must provide those inputs.

## Corpus

Use 12–20 short WAV excerpts spanning vocals, drums, bass, dense electronic,
and sparse acoustic material. Every case requires:

- a non-identifying case ID;
- a relative path beneath a separately supplied audio root;
- an exact SHA-256;
- explicit consent confirmation and an accepted rights basis;
- human observations, confidence, and acceptable alternatives;
- subjective choices that should not be scored as faults.

Copy `evaluation/review/REAL_MIX_CORPUS_MANIFEST_TEMPLATE.json` to secure
storage outside the repository and expand it there. Do not commit real paths,
audio, identities, or completed private manifests.

## Prepare a blinded packet

```bash
python3 scripts/evaluate_real_mix_corpus.py prepare \
  --manifest /secure/kenn-real-mix/manifest.json \
  --audio-root /secure/kenn-real-mix/audio \
  --packet /secure/kenn-real-mix/review-packet.json \
  --reviewer-a-template /secure/kenn-real-mix/reviewer-a.json \
  --reviewer-b-template /secure/kenn-real-mix/reviewer-b.json
```

Preparation verifies consent fields, rights basis, path containment, WAV
extension, file presence, SHA-256, non-empty structured human observations,
and the required vocals/drums/bass/dense-electronic/sparse-acoustic category
coverage before running the current engine. The packet reports whether the
12-case and category minimums are met but does not claim quality.

The command creates separately labelled, packet-bound forms for each reviewer.
Reviewers must work independently and fill every evidence-correctness,
usefulness, severity-order, and abstention score. False
positive and missed-issue families should use the engine's fault-family names.
Each reviewer must enter a distinct reviewer ID and explicitly confirm
independent completion. IDs are compared case-insensitively after trimming, so
capitalization or whitespace cannot disguise a duplicated reviewer.

## Score completed reviews

```bash
python3 scripts/evaluate_real_mix_corpus.py score \
  --packet /secure/kenn-real-mix/review-packet.json \
  --review /secure/kenn-real-mix/reviewer-a.json \
  --review /secure/kenn-real-mix/reviewer-b.json \
  --output /secure/kenn-real-mix/evaluation-result.json
```

Qualification requires at least 12 cases spanning every required category,
successful engine completion for every case, two distinct independent
reviewers, at least 90% evidence correctness, at least 85% of usefulness
ratings at 4/5 or above, at least 85% correct severity ordering and abstention,
and no more than 10% reviewer-recorded false positives per case review.
Missing, reordered, incomplete, or packet-mismatched reviews fail closed.
The packet and final receipt include the SHA-256 of the exact Mix Review engine;
the release gate rejects the receipt after that engine changes. The gate also
rechecks every quality flag and its underlying metric instead of trusting the
top-level `qualified` field alone.

Passing qualifies only the exact corpus, packet, engine output, and reviewers.
It does not establish universal mix intelligence or permission to train on the
audio.
