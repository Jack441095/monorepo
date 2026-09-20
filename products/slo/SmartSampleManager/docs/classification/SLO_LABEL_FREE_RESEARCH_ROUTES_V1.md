# SLO label-free research routes — V1

Date: 2026-09-12

## Decision

Do not start another broad encoder bake-off while the 600-file breadth batch is
unlabelled. The project has already tested the main representation and generic
fusion routes under collection-held-out evaluation. The remaining useful
research is either taxonomy design or label-free diagnostics.

## What the external work adds

### AudioSet ontology and dataset

AudioSet provides a hierarchical ontology spanning music, human, animal,
environmental, and mechanical sounds, with 632 ontology classes and over two
million labelled ten-second clips. It is a strong reference vocabulary for a
future real-world branch, not a reason to add hundreds of classes to the
current SLO production taxonomy.

### FSD50K

FSD50K contains 51,197 human-labelled Freesound clips across 200 AudioSet
classes. It is useful as an external sanity-check or teacher-data source for
environmental and animal concepts. Its Freesound distribution is not the same
as short, mastered music samples, so transfer results must not be presented as
SLO accuracy.

### HEAR benchmark

HEAR evaluates representations across 19 tasks covering speech, environmental
sound, and music. It is useful if a new encoder is proposed, but it is not a
replacement for SLO's collection-held-out product metric.

### UCS metadata standard

UCS 8.2.1 is a public-domain sound-effects categorisation and naming system.
It is useful for future SFX/environmental metadata and filename interoperability
but is aimed primarily at sound effects, not the current one-shot/loop musical
sample taxonomy.

### Models already known in this project

CLAP is already present and has been measured. BEATs, MERT, AST, LoRA, generic
waveform fusion, and mastering augmentation have already been tested or ruled
out against the incumbent gate. Re-running those without a new hypothesis is
not justified.

## Research that can happen before more labels

1. **Ontology mapping (read-only).** Map current classes and rejection reasons
   to AudioSet/UCS concepts and report unmapped concepts. Do not activate new
   classes.
2. **Open-vocabulary disagreement audit.** Run CLAP/AudioSet-style teachers on
   the 600 queue and compare their suggestions with filename evidence and the
   physical cards. Store disagreement as review evidence, never as ground
   truth.
3. **Unlabelled domain audit.** Measure collection, duration, loudness,
   spectral, and form distributions over the 28,330-file library to identify
   regions absent from the current labelled corpus.
4. **Self-supervised adaptation design.** Pretrain only on unlabelled audio,
   with the sealed validation paths excluded, then test one pre-registered
   projection against the existing collection-held-out incumbent after labels
   arrive. This is a candidate experiment, not a promised gain.

## Animal and real-world branch

Keep the existing `real_world_taxonomy_v1.json` dormant. Its domain/source/
event/form axes and `animal_unknown` fallback are the right shape: species
should not be guessed when the recording only supports a broader family.
Activation still requires human labels from multiple collections, collection-
held-out evaluation, and the same 95% precision gate.

## Recommended order

1. Finish the collection-breadth labels.
2. Run the read-only ontology and teacher-disagreement audits.
3. Retrain/recalibrate the current SLO branch.
4. Only if the incumbent remains limited, run one pre-registered
   self-supervised adaptation experiment.
5. Treat animal/environment classification as a separate product branch.
