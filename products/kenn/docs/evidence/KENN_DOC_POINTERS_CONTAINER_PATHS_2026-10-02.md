# Document pointers and container paths — 2 October 2026

The last open audit item in A3: dangling document links under `products/kenn`, and the paths the Dockerfiles,
compose files and symlinks depend on.

## Document pointers

A scan of every tracked `.md` under `products/kenn` (261 files, 257 relative links, code blocks skipped, external
URLs and anchors ignored) found 19 links that pointed at files no longer there. Most were relative links
written when the reports lived in one flat folder; the evidence, guides and handover files have since moved and each
target exists at exactly one tracked path, so those links were repointed:

- `docs/reports/ABLETON_ASSISTANT_CURRENT_STATE.md`: eight links, to `docs/evidence`, `docs/handover`, `docs/beta`,
  `docs/guides`.
- `docs/reports/ABLETON_ASSISTANT_READINESS_REPORT.md` (2), `docs/research/GLM_AUDIO_INTELLIGENCE_EVALUATION.md` (1),
  `docs/beta/ABLETON_INTERNAL_BETA_0.1.md` (1), `docs/legacy/STANDALONE_README.md` (3, now `docs/GETTING_STARTED.md`,
  `PRODUCT_MAP.md` and `CONTRIBUTING.md`).
- `docs/research/MINIMAX_MUSIC3_KENN_RESEARCH.md`: three links to `<LOCAL_VOLUME>/Shenrendao/KENN/...` (the old
  standalone checkout) now point at `apps/backend/src/kenn/...` in this tree.
- `KENN_HUGGINGFACE_DATASET_INTAKE_PLAN.md` no longer exists: it was removed with the retired plans in `f060bf54`.
  The sentence keeps its name as plain text, says where it went, and links the registry that is still tracked,
  `apps/backend/src/kenn/training/huggingface_dataset_candidates.json`.

Re-running the same scan afterwards: 257 links, 0 broken. Only link targets changed; no report wording was edited
beyond that one sentence.

## Container paths

- `products/kenn/apps/backend/Dockerfile`: every `COPY` source and `server.py` exist.
- `products/kenn/packages/chat/Dockerfile`: sources exist, and it no longer reads Audio_Too (see the
  [canonical wrapper receipt](KENN_CHAT_WRAPPER_CANONICAL_2026-10-02.md)).
- `Audio_Too/Dockerfile` and `docker-compose.yml`: every named source exists on this disk, and all 11 tracked
  symlinks under Audio_Too and `products/kenn` resolve (including the retargeted `studio/kenn`).

## Open finding: the Audio_Too image probably cannot build

The compose file builds with context `Audio_Too/`, but `studio/audio_analysis`, `studio/audiogen`, `studio/m4l`,
`studio/stem_separation`, `studio/vst3_plugins`, `studio/kenn` and `studio/agents/MixReview` are symlinks to
`../../audio-technology/...` and `../../products/kenn/...`, outside that context. Docker does not follow a symlink
out of the build context, and the Dockerfile's `COPY studio/audio_analysis/.../dsp_engine/native` goes through one.
So the image can only build if the context is widened to the repo root. No workflow builds this image, and there is
no Docker here, so this is read from the files, not observed. Changing the context or Dockerfile is a build change
for Jack to approve, so it is left alone.

## Limits

- Link check covers relative markdown links in tracked `.md` files, not `.json` pointers or links in code comments.
- Untracked and git-ignored documents were not scanned.
- Docker was not run.
