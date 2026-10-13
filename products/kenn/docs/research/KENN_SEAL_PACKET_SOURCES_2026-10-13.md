# KENN specialist draft source evidence

**Checked:** 13 October 2026. **Status:** unapproved local author draft. This note records primary-source checks and partition design for S2; it contains no reserved final questions or answers. No model endpoint, generation worker, training run, GPU, or Live session was used.

The input is ignored `products/kenn/.runtime/seal-specialist-draft-input-2026-10-13/spec.draft.json`. Its file SHA-256 is `e663c9c1c7127e0272e371ce6b42dc301364342f9580944df006120e6ab2a655`; its canonical JSON digest is `89664355ef44885c633adec3233aff09415d24cae6d70ec3b9a223cc2cb1e5c9`. Every source declares public privacy, rights review pending, owner review pending, and `training_permission: false`. Public availability and paraphrasing do not establish training rights.

## Primary evidence and family assignments

All 20 Ableton families were checked against the official Live 12 online manual. The linked pages are mutable; the draft records retrieval date and does not claim compatibility with an unidentified installed minor build. Facts were grouped with their concrete task templates before variants were written. Each row names the checked section without publishing final target wording.

| Partition | Fact family | Targets | Primary manual section checked |
| --- | --- | ---: | --- |
| Train | Utility stereo controls | 2 | [Audio effects: Utility, Width, channel modes, Bass Mono](https://www.ableton.com/en/live-manual/12/live-audio-effect-reference/) |
| Train | Beats and Re-Pitch tradeoffs | 2 | [Audio clips: Beats and Re-Pitch modes](https://www.ableton.com/en/live-manual/12/audio-clips-tempo-and-warping/) |
| Train | Return sends and feedback | 2 | [Mixing: return tracks and Pre/Post send tapping](https://www.ableton.com/en/live-manual/12/mixing/) |
| Train | Internal and summing precision | 2 | [Audio fact sheet: summing and recording unprocessed signals](https://www.ableton.com/en/live-manual/12/audio-fact-sheet/) |
| Reward | Rack selector input filtering | 3 | [Racks: zones and chain-select zones](https://www.ableton.com/en/live-manual/12/instrument-drum-and-effect-racks/) |
| Reward | Groove preprocessing and commit | 3 | [Grooves: groove parameters and committing](https://www.ableton.com/en/live-manual/12/using-grooves/) |
| Reward | Session launch gestures and onset grid | 3 | [Clip launching: launch modes and quantization](https://www.ableton.com/en/live-manual/12/launching-clips/) |
| Reward | Tuning files and default divisions | 3 | [Tuning systems: Scala, Ableton Scala and equal temperament](https://www.ableton.com/en/live-manual/12/using-tuning-systems/) |
| Reward | Collection tags and visibility | 3 | [Browser: Collections](https://www.ableton.com/en/live-manual/12/working-with-the-browser/) |
| Reward | Project collection and missing-file resolution | 3 | [Files: locating missing files and collecting external files](https://www.ableton.com/en/live-manual/12/managing-files-and-sets/) |
| Reward | MIDI note deactivation | 3 | [MIDI editing: deactivating notes](https://www.ableton.com/en/live-manual/12/editing-midi/) |
| Reward | Push 2 fixed length and phrase sync | 3 | [Push 2: fixed-length recording](https://www.ableton.com/en/live-manual/12/using-push-2/) |
| Final | Operator algorithm and fixed frequency | 3 | [Instruments: Operator](https://www.ableton.com/en/live-manual/12/live-instrument-reference/) |
| Final | Arpeggiator rate units and gate duration | 3 | [MIDI effects: Arpeggiator](https://www.ableton.com/en/live-manual/12/live-midi-effect-reference/) |
| Final | Automation override and re-enable scope | 3 | [Automation: overriding automation](https://www.ableton.com/en/live-manual/12/automation-and-editing-envelopes/) |
| Final | Unlinked envelope local loops | 3 | [Clip envelopes: unlinking envelopes from clips](https://www.ableton.com/en/live-manual/12/clip-envelopes/) |
| Final | Capture MIDI and Set state | 3 | [Recording: Capture MIDI](https://www.ableton.com/en/live-manual/12/recording-new-clips/) |
| Final | Audio load meter processing ratio | 3 | [Computer audio: CPU load meter](https://www.ableton.com/en/live-manual/12/computer-audio-resources-and-strategies/) |
| Final | Max editing and save scope | 3 | [Max for Live: editing devices](https://www.ableton.com/en/live-manual/12/max-for-live/) |
| Final | Link peers and transport scope | 3 | [Synchronization: Link](https://www.ableton.com/en/live-manual/12/synchronizing-with-link-tempo-follower-and-midi/) |

The four retention groups are authored, self-contained fictional language, shopping/time arithmetic, missing-reference clarification, and archive-permission fixtures: three checks each. Their primary definitions reside in the ignored specification; they contain no Ableton facts or private session information. The train contexts cover documented behavior rather than universal mix presets. Quantities in ordinary answers use the same units as their supporting source text.

## Semantic separation review

One author compared factual concepts and concrete task forms, beyond chapter names and alias strings. No cross-partition factual or template collision was identified. The draft records the reviewed seams: playback rate/pitch versus groove preprocessing, launch gestures and local envelope loops; selected-note toggles and Rack membership versus capture and instrument behavior; send tapping and numeric precision versus audio processing time; browser tags and sample-reference repair versus Max save scope; and Push recording length versus Capture and Link transport. Facts about Warp markers, linked envelopes, Max missing paths and Push Capture shortcuts were excluded where they would cross these seams.

Unit labeling, resolving history, stating evidence limits, source conflict handling, device-name restraint and proposal boundaries recur intentionally. Concrete tasks and required domain facts remain assigned to one partition. An independent owner must still decide whether these seams and task forms provide adequate semantic isolation. One author's pass is not human certification, and author access to final targets does not establish reviewer blindness.

## Scoped verification and remaining review

The latest `seal_experiment.preparation.prepare(spec)` passed in memory: four train contexts with two targets each, 24 reward, 12 retention and 24 final. Reward and final each include all seven required coverage categories. Cross-partition lexical flags at the 0.35 Jaccard review threshold: zero; maximum cross-partition question Jaccard: `0.2222222222222222`. Alias/template guards and the ordinary-example 0.6 overlap guard passed. Source reference text is absent from knowledge-only inference messages; supporting text remains human evidence. Training is disabled and approvals are empty. `git check-ignore` confirms the input boundary.

No packet was emitted by this research task. Factual support, target wording, source and derived-target rights, semantic independence, owner grades and shared-weight permissions remain pending. Exact installed Live behavior has not been tested; Max's documented UI version threshold is carried explicitly in the draft. No final model answers or paired KENN retrieval captures exist from this work.
