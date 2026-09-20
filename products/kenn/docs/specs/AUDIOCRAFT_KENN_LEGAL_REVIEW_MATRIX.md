# AudioCraft components for KENN — legal review matrix

Checked 2026-09-02 against the official Meta repositories and model cards. This
is an engineering due-diligence aid, not legal advice. A lawyer should review
the exact files, checkpoints, dependencies, training data, and distribution
model before KENN is commercialised.

## The important split

AudioCraft has two different licensing layers:

1. The AudioCraft repository code is released under the MIT license. If KENN
   distributes copied or modified code, retain the copyright and MIT notice.
2. The released AudioCraft model weights are separately released under
   CC-BY-NC 4.0. That is a non-commercial license, so do not bundle or deploy
   those checkpoints in a paid or commercial KENN product without separate
   permission. The weight license also has attribution and modification
   notice requirements when the material is shared.

Primary references: [AudioCraft repository and licenses](https://github.com/facebookresearch/audiocraft),
[MIT code license](https://raw.githubusercontent.com/facebookresearch/audiocraft/main/LICENSE),
and [CC-BY-NC weights license](https://raw.githubusercontent.com/facebookresearch/audiocraft/main/LICENSE_weights).

## Candidate components

| Component | Useful KENN role | Current legal signal | Recommendation |
|---|---|---|---|
| `audiocraft/models/encodec.py` and quantization modules | Offline learned audio representation, codec experiments, or a research feature extractor | AudioCraft source code is MIT; the pretrained AudioCraft checkpoints are a separate license question | Study or isolate the architecture first. Do not ship the `facebook/encodec_32khz` checkpoint until its model-card/weight terms are cleared. |
| Standalone [facebookresearch/encodec](https://github.com/facebookresearch/encodec) code | A cleaner codec reference than importing all of AudioCraft | The standalone repository says its code is MIT | Strongest AudioCraft-adjacent candidate, but audit any checkpoint and dependency separately. It is not needed for Live command control. |
| `MusicGen` | Optional offline generation of musical ideas, beds, or variations from a prompt | Code MIT; released MusicGen weights CC-BY-NC 4.0; the model card is research-oriented and warns about downstream use | Research-only unless Meta grants additional rights or KENN uses a separately licensed model and data. Keep it outside the Ableton control path. |
| `AudioGen` | Optional offline generation of sound-design/SFX suggestions | Code MIT; released weights CC-BY-NC 4.0; its model card lists multiple training/evaluation sources and research limitations | Useful conceptually for a future SFX assistant, not a commercial KENN dependency in its released form. |
| `MAGNeT` | Faster non-autoregressive text-to-audio research and generation experiments | AudioCraft’s released model family is covered by the repository’s separate weight terms; verify the exact Hugging Face checkpoint card | Low priority for KENN. Do not deploy its released weights commercially without a checkpoint-specific clearance. |
| `JASCO` | Conditioning generation on chords, drums, and melody; useful as a design reference for musical context | Code is in the MIT-code repository, but released weights still need checkpoint review; the implementation also uses a Chordino-derived chord mapping, which needs its own audit | Good research reference for a future musical-context layer, not part of the Live command model. Audit the chord-extractor asset independently. |
| Multi Band Diffusion | Alternative decoder/reconstruction research for generated audio | Treat code, checkpoints, and dependencies separately; it does not solve KENN’s command or Live-control problem | Do not prioritise for the product roadmap. |
| AudioCraft training/data/solver patterns | Dataset manifests, conditioning, token training, and experiment reproducibility | Repository code is MIT, but dependencies and all training inputs retain their own terms; AudioCraft does not grant KENN rights to its training audio | Reuse ideas and isolated code only after dependency review. Train KENN on audio/metadata with documented rights. |
| [AudioSeal](https://github.com/facebookresearch/audioseal) | Watermark/provenance for KENN-generated or exported audio | Its current official README says the code and model weights are MIT, including commercial use; retain the MIT notice and verify the exact checkpoint artifact | The most directly useful Meta audio component for a future provenance/export feature. Keep it separate from Live control and verify the current checkpoint notice before release. |

## What is actually useful for KENN

The best technical reuse is not the MusicGen model itself. It is the pattern of
separating:

- audio tokenisation/representation from the language model;
- conditioning inputs such as text, melody, chords, and drums;
- offline generation from the real-time/control process; and
- model output from a typed, validated action boundary.

For KENN, that suggests this order:

1. Keep the command LLM and Ableton safety boundary independent of AudioCraft.
2. If learned audio evidence is needed, benchmark an isolated EnCodec-style
   encoder against KENN’s existing spectral evidence before adding it to the
   product.
3. If KENN generates audio, run it as an offline, opt-in service with a
   provenance receipt, explicit user confirmation, and a separately reviewed
   model/data license.
4. Consider AudioSeal for provenance after its exact dependency and checkpoint
   notices are recorded.

## Legal checks before copying or shipping

- Record the exact repository commit, file paths, and checkpoint IDs.
- Keep MIT notices for copied code and produce a dependency/license inventory.
- Treat every pretrained checkpoint as separately licensed from its source
  repository code.
- Do not assume a model’s generated output is commercially clear merely because
  the inference code is MIT; review the checkpoint terms, model card, dataset
  provenance, and any rights in user-provided source audio.
- Audit transitive dependencies such as PyTorch, torchaudio, Demucs, xformers,
  ffmpeg, Chordino/chord-extractor, and any downloaded tokenizer or decoder.
- Keep non-commercial checkpoints out of production builds, published Docker
  images, hosted inference endpoints, and customer-facing downloads unless a
  written permission or an appropriate replacement license is documented.
- Record whether KENN is merely studying an algorithm, copying code, shipping
  weights, fine-tuning weights, or distributing generated audio; these are
  different legal questions.

## Current KENN decision

AudioCraft is not integrated into KENN. The current plan is to use its code and
papers as research references only, keep released AudioCraft checkpoints out
of the commercial product by default, and evaluate separately licensed or
self-trained audio models if KENN later needs generation or learned audio
evidence.
