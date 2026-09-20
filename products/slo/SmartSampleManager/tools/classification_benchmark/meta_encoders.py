#!/usr/bin/env python3
"""
Meta (FAIR) audio encoders as classification features -- licence-filtered.

Meta publishes a lot of audio research, but most of the models one would
actually want here are released CC-BY-NC and are therefore unusable in a
commercial product:

    AudioMAE ................ CC-BY-NC   masked audio autoencoder
    ImageBind ............... CC-BY-NC   joint audio/image/text embedding
    MusicGen / AudioGen ..... CC-BY-NC   (weights; the CODE is MIT)
    MMS / Seamless .......... CC-BY-NC

What is genuinely permissive, and therefore all this script tests:

    EnCodec ................. MIT        neural codec, 24kHz and 48kHz
    HuBERT .................. Apache-2.0 speech SSL
    wav2vec2 ................ Apache-2.0 speech SSL
    Demucs .................. MIT        source separation (tested separately)

Prior expectation, recorded before running so it can be scored:
  - EnCodec latents are optimised for RECONSTRUCTION, not semantics. Codec
    bottlenecks discard perceptually-irrelevant-but-semantically-useful
    structure. Expect them to underperform Perch/CLAP.
  - HuBERT/wav2vec2 are trained on SPEECH at 16kHz. Drum one-shots are
    broadband transients with most of their identity above 8kHz, which
    resampling to 16k destroys. Expect weak.
  I have been wrong about encoder choice before (MERT was predicted to win and
  did not), which is the entire reason this is measured rather than asserted.

Baseline to beat: Perch+CLAP linear probe on the same 649 by-ear files.
"""
import os, csv, time, argparse, warnings
import numpy as np
warnings.filterwarnings("ignore")

SD = os.path.dirname(os.path.abspath(__file__))
VERIFIED = os.path.join(SD, "verified_drums.csv")
CACHE = os.path.join(SD, "meta_emb.npz")


def load_audio(path, sr):
    import soundfile as sf, librosa
    y, s = sf.read(path, dtype="float32", always_2d=False)
    if y.ndim > 1:
        y = y.mean(1)
    if s != sr:
        y = librosa.resample(y, orig_sr=s, target_sr=sr)
    if len(y) < sr // 2:                       # pad short one-shots to 0.5s
        y = np.pad(y, (0, sr // 2 - len(y)))
    return y[: sr * 10].astype(np.float32)     # cap at 10s


def encodec_embed(paths, batch=8):
    """Mean+max pooled continuous latents from the MIT-licensed EnCodec."""
    import torch
    from transformers import EncodecModel, AutoProcessor
    name = "facebook/encodec_24khz"
    proc = AutoProcessor.from_pretrained(name)
    m = EncodecModel.from_pretrained(name).eval()
    sr = proc.sampling_rate
    out, t0 = [], time.time()
    for i in range(0, len(paths), batch):
        wavs = [load_audio(p, sr) for p in paths[i:i + batch]]
        with torch.no_grad():
            for w in wavs:
                x = torch.tensor(w)[None, None, :]
                h = m.encoder(x)                       # [1, 128, frames]
                h = h[0].T                             # [frames, 128]
                out.append(torch.cat([h.mean(0), h.max(0).values]).numpy())
        if i and i % (batch * 20) == 0:
            print(f"  encodec {i}/{len(paths)} {i/(time.time()-t0):.1f}/s", flush=True)
    return np.stack(out).astype(np.float32)


def hf_ssl_embed(paths, name, batch=8):
    """Mean+max pooled hidden states from an Apache-2.0 speech SSL encoder."""
    import torch
    from transformers import AutoModel, AutoFeatureExtractor
    fe = AutoFeatureExtractor.from_pretrained(name)
    m = AutoModel.from_pretrained(name).eval()
    sr = fe.sampling_rate
    out, t0 = [], time.time()
    for i in range(0, len(paths), batch):
        wavs = [load_audio(p, sr) for p in paths[i:i + batch]]
        with torch.no_grad():
            inp = fe(wavs, sampling_rate=sr, return_tensors="pt", padding=True)
            h = m(**inp).last_hidden_state              # [b, frames, dim]
            out.append(torch.cat([h.mean(1), h.max(1).values], -1).numpy())
        if i and i % (batch * 20) == 0:
            print(f"  {name.split('/')[-1]} {i}/{len(paths)} "
                  f"{i/(time.time()-t0):.1f}/s", flush=True)
    return np.concatenate(out).astype(np.float32)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-class", type=int, default=15)
    a = ap.parse_args()

    rows = [r for r in csv.DictReader(open(VERIFIED))
            if r["label"] not in ("__skip__", "Misc/Review")
            and os.path.exists(r["path"])]
    paths = [r["path"] for r in rows]
    y = np.array([r["label"] for r in rows])
    print(f"{len(paths)} by-ear labelled files\n")

    if os.path.exists(CACHE):
        z = np.load(CACHE)
        E = {k: z[k] for k in z.files}
        print(f"loaded cached: {list(E)}")
    else:
        E = {}
        print("EnCodec 24kHz (MIT)...");        E["encodec"] = encodec_embed(paths)
        print("HuBERT base (Apache-2.0)...");   E["hubert"] = hf_ssl_embed(paths, "facebook/hubert-base-ls960")
        print("wav2vec2 base (Apache-2.0)..."); E["w2v2"] = hf_ssl_embed(paths, "facebook/wav2vec2-base")
        np.savez(CACHE, **E)
    for k, v in E.items():
        print(f"  {k:10} {v.shape}")

    z = np.load(os.path.join(SD, "bioacoustic_emb.npz"))
    Xp, Xc = z["perch"], z["clap"]
    assert len(Xp) == len(paths), f"cache mismatch {len(Xp)} vs {len(paths)}"

    from collections import Counter
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import make_pipeline
    from sklearn.model_selection import cross_val_predict
    cnt = Counter(y)
    viable = [c for c in cnt if cnt[c] >= a.min_class]
    m = np.isin(y, viable)
    print(f"\nevaluating on {m.sum()} files, {len(viable)} classes\n")

    def run(X, name):
        clf = make_pipeline(StandardScaler(),
                            LogisticRegression(max_iter=3000, class_weight="balanced"))
        pred = cross_val_predict(clf, X[m], y[m], cv=5)
        acc = 100 * (pred == y[m]).mean()
        print(f"  {name:38} {acc:5.1f}%")
        return pred, acc

    preds = {}
    _, base = run(np.hstack([Xp, Xc]), "BASELINE Perch+CLAP")
    for k in E:
        preds[k], _ = run(E[k], f"{k} alone")
    for k in E:
        _, acc = run(np.hstack([Xp, Xc, E[k]]), f"Perch+CLAP + {k}")
        print(f"    {'':36} {acc-base:+5.1f}pp vs baseline")
    _, acc = run(np.hstack([Xp, Xc] + [E[k] for k in E]), "Perch+CLAP + ALL Meta")
    print(f"    {'':36} {acc-base:+5.1f}pp vs baseline")

    print("\nper-class recall (does any Meta encoder win SOMEWHERE?):")
    hdr = f"  {'class':>16} {'n':>4}" + "".join(f"{k[:9]:>11}" for k in preds)
    print(hdr)
    for c in sorted(viable, key=lambda k: -cnt[k]):
        sel = y[m] == c
        line = f"  {c:>16} {int(sel.sum()):4d}"
        for k in preds:
            line += f"{100*(preds[k][sel]==c).mean():10.0f}%"
        print(line)


if __name__ == "__main__":
    main()
