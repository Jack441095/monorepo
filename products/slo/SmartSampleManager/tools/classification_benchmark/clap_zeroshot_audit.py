#!/usr/bin/env python3
"""
CLAP zero-shot audit of the keyword-derived labels.

Why this exists
---------------
Training labels come from filename/folder keyword matching. Measured
evidence that those labels are noisy:
  - collapsing to 4 acoustically-obvious classes still only reaches 84.9%
  - 14.7% of predictions at >0.95 confidence disagree with the label

CLAP classifies from text prompts with no training on this corpus at all, so
it is an INDEPENDENT opinion that never saw the filenames. Where CLAP and the
supervised model both disagree with the keyword label, the label is the most
likely thing to be wrong.

This does not prove any individual label is wrong -- CLAP is imperfect too.
It bounds how much of the residual error is label noise rather than model
capacity, and produces a ranked list of files worth human review.

Runs on GPU 1 via CUDA_VISIBLE_DEVICES=1.
"""

import os
import sys
import json
import time
import argparse
import numpy as np
import torch
import soundfile as sf

CLAP_SR = 48000

# Several phrasings per class, averaged. Single prompts are brittle; CLAP is
# sensitive to wording, and averaging a few reduces that variance.
PROMPTS = {
    # v2 prompts. The v1 set described a sample's ROLE in a production
    # workflow ("a foley recording", "a percussion instrument"). CLAP matches
    # acoustic content, not producer jargon, and scored Foley 2.0% /
    # Percussion 12.8% as a result -- it almost never picked those prompts.
    # These describe the SOUND instead, and name concrete objects.
    "Bass Loop":      ["a repeating bassline groove", "a looping bass riff",
                       "a funky electric bass guitar riff"],
    "Bass One-Shot":  ["a deep sub bass note", "a low sine wave tone",
                       "an 808 bass drop note", "a single low frequency hum"],
    "Clap":           ["a hand clap", "hands clapping once", "a sharp clap slap"],
    "FX":             ["a whoosh sound effect", "a glitchy digital noise burst",
                       "a laser zap", "a sci-fi electronic effect"],
    "Foley":          ["footsteps on gravel", "a door creaking open",
                       "rustling paper", "an object being picked up and put down",
                       "a household object being handled", "water splashing"],
    "Hi-Hat":         ["a hi-hat cymbal", "a closed hi-hat tick",
                       "a short crisp metallic cymbal"],
    "Impact":         ["a large explosion boom", "a heavy cinematic hit",
                       "a massive crashing impact"],
    "Kick":           ["a kick drum", "a bass drum hit", "a deep thumping kick drum"],
    "Music Loop":     ["a musical loop with chords and melody",
                       "a short piece of instrumental music", "a band groove loop"],
    "Percussion":     ["a tambourine shaking", "a shaker rattling", "a conga drum",
                       "a bongo drum hit", "a woodblock click", "a cowbell"],
    "Riser":          ["a rising whoosh building tension",
                       "an ascending sweep upward", "a build up transition effect"],
    "Snare":          ["a snare drum", "a snare drum rimshot", "a sharp cracking snare"],
    "Synth":          ["a sustained synthesizer chord", "an electronic keyboard note",
                       "a synth pad tone"],
    "Synth Loop":     ["a looping synth arpeggio", "a repeating electronic sequence",
                       "an arpeggiated synthesizer pattern"],
    "Vocal Loop":     ["a chopped up vocal sample repeating",
                       "a looping sung vocal hook", "a rhythmic vocal chop"],
    "Vocal Phrase":   ["a person singing", "a human voice speaking words",
                       "a solo singer holding a note", "speech"],
}


def load_batch(paths):
    out = []
    for p in paths:
        try:
            y, sr = sf.read(p, dtype="float32", always_2d=False)
            if y.ndim > 1:
                y = y.mean(axis=1)
        except Exception:
            y = np.zeros(CLAP_SR, dtype=np.float32)
        if len(y) == 0:
            y = np.zeros(CLAP_SR, dtype=np.float32)
        out.append(y)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio-dir", default="clap_audio")
    ap.add_argument("--model", default="clap_model",
                    help="local model dir (the GPU box has no HuggingFace access)")
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--out", default="clap_zeroshot_result.npz")
    args = ap.parse_args()

    # transformers 5.x returns BaseModelOutputWithPooling from
    # get_audio_features/get_text_features; .pooler_output is the 512-D
    # joint-space projection. Verified by a semantic spot check (Kick,
    # Snare, Hi-Hat, Synth, Clap all rank their own prompt first).
    from transformers import ClapModel, ClapProcessor

    manifest_path = os.path.join(args.audio_dir, "manifest.json")
    with open(manifest_path) as f:
        man = json.load(f)
    classes = man["classes"]
    items = man["items"]

    usable = [m for m in items
              if m["ok"] and os.path.exists(os.path.join(args.audio_dir, f"{m['pos']:05d}.flac"))]
    print(f"{len(usable)} usable clips of {len(items)}")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"device: {device}"
          + (f" ({torch.cuda.get_device_name(0)})" if torch.cuda.is_available() else ""))

    proc = ClapProcessor.from_pretrained(args.model)
    model = ClapModel.from_pretrained(args.model).to(device).eval()

    # Text side: average the prompt embeddings per class, then renormalise.
    flat, owner = [], []
    for ci, c in enumerate(classes):
        for p in PROMPTS[c]:
            flat.append(p); owner.append(ci)
    with torch.no_grad():
        ti = proc(text=flat, return_tensors="pt", padding=True)
        ti = {k: v.to(device) for k, v in ti.items()}
        tfeat = model.get_text_features(**ti).pooler_output
        tfeat = torch.nn.functional.normalize(tfeat, dim=-1)
    owner = torch.tensor(owner, device=device)
    cls_emb = torch.zeros(len(classes), tfeat.shape[1], device=device)
    cls_emb.index_add_(0, owner, tfeat)
    cls_emb = torch.nn.functional.normalize(cls_emb, dim=-1)

    positions, preds, confs, sims = [], [], [], []
    t0 = time.time()
    for s in range(0, len(usable), args.batch):
        chunk = usable[s:s + args.batch]
        paths = [os.path.join(args.audio_dir, f"{m['pos']:05d}.flac") for m in chunk]
        audio = load_batch(paths)
        with torch.no_grad():
            ai = proc(audio=audio, sampling_rate=CLAP_SR, return_tensors="pt", padding=True)
            ai = {k: v.to(device) for k, v in ai.items()}
            af = model.get_audio_features(**ai).pooler_output
            af = torch.nn.functional.normalize(af, dim=-1)
            sim = af @ cls_emb.T
            prob = torch.softmax(sim * 100.0, dim=-1)
        positions.extend(m["pos"] for m in chunk)
        preds.extend(prob.argmax(-1).cpu().numpy().tolist())
        confs.extend(prob.max(-1).values.cpu().numpy().tolist())
        sims.append(sim.cpu().numpy())
        if s and s % (args.batch * 20) == 0:
            done = s + len(chunk)
            r = done / (time.time() - t0)
            print(f"  {done}/{len(usable)} - {r:.1f} clips/s - ETA {(len(usable)-done)/r/60:.1f} min",
                  flush=True)

    positions = np.array(positions)
    preds = np.array(preds)
    confs = np.array(confs)
    sims = np.concatenate(sims, axis=0)
    labels = np.array([classes.index(m["label"]) for m in usable])

    agree = float((preds == labels).mean())
    print(f"\nCLAP zero-shot agreement with keyword labels: {agree*100:.2f}%")
    print("(zero-shot, never trained on this corpus and never saw the filenames)\n")

    print(f"{'class':>14} {'n':>5} {'CLAP agrees':>12}")
    for ci, c in enumerate(classes):
        m = labels == ci
        if m.sum() == 0:
            continue
        print(f"{c:>14} {int(m.sum()):5d} {100*(preds[m]==ci).mean():11.1f}%")

    np.savez(args.out, positions=positions, clap_pred=preds, clap_conf=confs,
             clap_sims=sims, keyword_label=labels, classes=np.array(classes))
    print(f"\nSaved {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
