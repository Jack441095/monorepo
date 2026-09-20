"""
SLO Master Plan Phase 2 (B-006) -- real, cross-vendor, leakage-controlled
accuracy benchmark.

Why this exists: GOLDEN_SET_V1_REPORT.md's "Audio only Accuracy: 5.9%" figure
is measured entirely on programmatically synthesized sine/noise fixtures
(see generate_golden_set.py) standing in for real drum/instrument sounds --
not real audio. The PANNs embedding model was trained on real-world audio, so
a poor score on crude synthetic tones does not by itself prove the audio-only
path is broken on real customer libraries. This script re-runs the same
full-evidence vs audio-only ablation methodology against REAL, licensed,
multi-vendor commercial sample packs, so the honest report this produces is
backed by real audio, not a synthetic proxy.

Ground truth here comes from each vendor pack's own folder naming (e.g. a
"Kicks" folder is trusted to contain kicks). This is not human-verified
per-file, and that limitation is stated explicitly in the report -- it is the
same class of evidence Slice A "full evidence" already relies on. Errors in a
few vendor folders are expected and acceptable at this corpus size; treat
these numbers as directionally decisive, not to the third decimal place.

Usage:
    python3 run_real_corpus_benchmark.py <path-to-ClassificationBenchmark-binary>

Requires fixtures/real_corpus_v1/{full_evidence,audio_only}/ and
fixtures/real_corpus_v1/real_corpus_v1_manifest.json to already exist --
produced by the one-off corpus-sampling script run for Phase 2 (see the SLO
master plan's Phase 2 section / "New findings" for how that sample was drawn).
"""
import os
import sys
import json
import subprocess
from collections import defaultdict

# P2-5 eval contract: split labels + Wilson CIs on every number (see eval_contract.py).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eval_contract


def calculate_metrics(y_true, y_pred, labels):
    metrics = {}
    total = len(y_true)
    for label in labels:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == label and p == label)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != label and p == label)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == label and p != label)
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2.0 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        n = sum(1 for t in y_true if t == label)
        metrics[label] = {"n": n, "precision": precision, "recall": recall, "f1": f1}
    macro_f1 = sum(m["f1"] for m in metrics.values()) / len(labels) if labels else 0.0
    accuracy = sum(1 for t, p in zip(y_true, y_pred) if t == p) / total if total > 0 else 0.0
    return metrics, macro_f1, accuracy


def main():
    if len(sys.argv) < 2:
        print("Usage: run_real_corpus_benchmark.py <path-to-ClassificationBenchmark-binary>")
        sys.exit(1)
    benchmark_bin = sys.argv[1]
    if not os.path.exists(benchmark_bin):
        print(f"FAIL: benchmark executable not found at {benchmark_bin}")
        sys.exit(1)

    base_dir = os.path.dirname(os.path.abspath(__file__))
    corpus_dir = os.path.join(base_dir, "fixtures", "real_corpus_v1")
    manifest_path = os.path.join(corpus_dir, "real_corpus_v1_manifest.json")
    full_dir = os.path.join(corpus_dir, "full_evidence")
    audio_dir = os.path.join(corpus_dir, "audio_only")

    for p in (manifest_path, full_dir, audio_dir):
        if not os.path.exists(p):
            print(f"FAIL: expected corpus artifact missing: {p}")
            print("Run the Phase 2 corpus-sampling step first (see SLO master plan).")
            sys.exit(1)

    with open(manifest_path) as f:
        manifest = json.load(f)

    # ClassificationBenchmark's "scan" reports filePath as a bare basename,
    # not a path relative to the scanned directory -- match on basename.
    # Safe because every full-evidence filename is prefixed with its unique
    # sample_id (see the corpus-sampling script), so basenames are globally
    # unique even though files live in per-category subfolders.
    by_full_relpath = {os.path.basename(m["full_evidence_relpath"]): m for m in manifest}
    by_audio_name = {m["audio_only_filename"]: m for m in manifest}
    subclasses = sorted(set(m["expected_subcategory"] for m in manifest))

    print(f"Real corpus: {len(manifest)} files across {len(subclasses)} classes, "
          f"{len(set(m['source_vendor'] for m in manifest))} vendors")

    print("Running ClassificationBenchmark on full-evidence slice (real filenames + folders)...")
    full_out = os.path.join(base_dir, "results_real_corpus_full.json")
    subprocess.run([benchmark_bin, "scan", full_dir, full_out], check=True)
    with open(full_out) as f:
        full_results = json.load(f)

    # NOTE: the underlying scan appears to share a persistent cache database
    # across invocations -- this second scan's raw JSON came back with
    # results from the FIRST (full-evidence) scan mixed in (1240 entries for
    # a 620-file directory in one observed run). The by_audio_name.get()
    # lookup below already only accepts entries whose filePath matches this
    # slice's generic sample_NNNNNN.wav naming, so cross-contaminated entries
    # are silently and correctly dropped -- but if this script ever stops
    # filtering by a matched-name lookup, this cache-sharing behavior will
    # silently corrupt results again. Don't remove the "if not expected:
    # continue" guards below.
    print("Running ClassificationBenchmark on audio-only slice (generic filenames, flat dir)...")
    audio_out = os.path.join(base_dir, "results_real_corpus_audio_only.json")
    subprocess.run([benchmark_bin, "scan", audio_dir, audio_out], check=True)
    with open(audio_out) as f:
        audio_results = json.load(f)

    # --- Full-evidence analysis ---
    y_true_full, y_pred_full = [], []
    evidence_counts = defaultdict(int)
    evidence_correct = defaultdict(int)
    errors_full = []
    for res in full_results:
        expected = by_full_relpath.get(os.path.basename(res["filePath"]))
        if not expected:
            continue
        t, p = expected["expected_subcategory"], res["subcategory"]
        y_true_full.append(t)
        y_pred_full.append(p)
        ev = res.get("winningEvidence", "")
        evidence_counts[ev] += 1
        if t == p:
            evidence_correct[ev] += 1
        else:
            errors_full.append({"expected": t, "predicted": p, "evidence": ev,
                                 "vendor": expected["source_vendor"], "file": expected["original_filename"]})

    _, macro_f1_full, acc_full = calculate_metrics(y_true_full, y_pred_full, subclasses)

    # --- Audio-only analysis ---
    y_true_audio, y_pred_audio = [], []
    for res in audio_results:
        name = os.path.basename(res["filePath"])
        expected = by_audio_name.get(name)
        if not expected:
            continue
        y_true_audio.append(expected["expected_subcategory"])
        y_pred_audio.append(res["subcategory"])

    class_metrics_audio, macro_f1_audio, acc_audio = calculate_metrics(y_true_audio, y_pred_audio, subclasses)

    matched_full = len(y_true_full)
    matched_audio = len(y_true_audio)

    # --- Per-class table (audio-only, the number that matters most) ---
    class_table = "| Class | N | Audio-only Accuracy |\n|---|---|---|\n"
    for cls in subclasses:
        m = class_metrics_audio.get(cls, {"n": 0, "recall": 0.0})
        class_table += f"| {cls} | {m['n']} | {m['recall']*100:.1f}% |\n"

    evidence_table = "| Evidence Source | Count | Accuracy When Winning |\n|---|---|---|\n"
    for ev, count in sorted(evidence_counts.items(), key=lambda x: -x[1]):
        acc = evidence_correct[ev] / count if count else 0.0
        evidence_table += f"| {ev} | {count} | {acc*100:.1f}% |\n"

    n_vendors = len(set(m["source_vendor"] for m in manifest))

    report = f"""# SLO Real-Corpus Cross-Vendor Accuracy Report V1

**Generated by:** SLO Master Plan Phase 2 (B-006), `run_real_corpus_benchmark.py`
**Corpus:** {len(manifest)} real, licensed, commercial sample-pack files across
{len(subclasses)} classes and {n_vendors} vendors, drawn from
`/Volumes/Jack_Gandy_1TB_SSD/testing-for-NITE-DSP/sample_pack_testing`.
**Ground truth:** derived from each vendor pack's own folder naming (e.g. a
"Kicks" folder is trusted to contain kicks). Not manually verified per file --
directionally decisive at this sample size, not a certified label set.

This supplements (does not replace) `GOLDEN_SET_V1_REPORT.md`. The golden set
uses synthetic sine/noise fixtures and remains useful for deterministic
regression testing; this report exists because a synthetic-audio score cannot
by itself tell you how the audio-only path performs on real customer
material, and the previous headline (96.5%) never separated the two.

## Headline numbers

| Metric | Full evidence (real filenames+folders) | Audio-only (generic names, flat dir) |
|---|---|---|
| Subcategory accuracy | {acc_full*100:.1f}% ({matched_full} matched) | {acc_audio*100:.1f}% ({matched_audio} matched) |
| Macro F1 | {macro_f1_full:.3f} | {macro_f1_audio:.3f} |

**Do not report a single blended accuracy number for this product again.**
Report both of the above together, every time.

## Headline numbers with uncertainty (P2-5 eval contract -- cite these)
{eval_contract.split_line("Full-evidence accuracy", round(acc_full * matched_full), matched_full)}
{eval_contract.split_line("Audio-only accuracy", round(acc_audio * matched_audio), matched_audio)}
Splits use Wilson 95% CIs across {n_vendors} vendors (folder-name-derived
ground truth -- see scope limitations). No adversarial slice exists for this
corpus; the golden set's adversarial number (n=2) is the only one.

## Per-class audio-only accuracy
{class_table}

## Winning evidence breakdown (full-evidence slice)
{evidence_table}

## Errors on the full-evidence slice (should be rare -- filename/folder evidence is trusted)
Total errors: {len(errors_full)} / {matched_full}
"""
    if errors_full:
        report += "\n| Expected | Predicted | Evidence | Vendor | File |\n|---|---|---|---|---|\n"
        for e in errors_full[:30]:
            report += f"| {e['expected']} | {e['predicted']} | {e['evidence']} | {e['vendor']} | `{e['file']}` |\n"

    report += """
## Scope limitations (read before citing this report)
- Folder-name-derived ground truth, not hand-verified per file.
- Covers 12 of SLO's 17 taxonomy classes (Synth, Synth Loop, Vocal Loop, Music
  Loop had no reliably keyword-matchable vendor folders in this corpus scan --
  not evidence those classes work or don't work, just not measured here).
- Capped at 60 files/class, 15/vendor/class for runtime -- a sample, not the
  full 43GB/~30k-file corpus.
- Real audio content, but skewed toward one-shots/short loops matching common
  vendor folder conventions -- may not represent every real-world library
  layout.
"""

    docs_dir = os.path.join(os.path.dirname(os.path.dirname(base_dir)), "docs", "classification")
    os.makedirs(docs_dir, exist_ok=True)
    report_path = os.path.join(docs_dir, "REAL_CORPUS_CROSS_VENDOR_V1_REPORT.md")
    with open(report_path, "w") as f:
        f.write(report)

    print(f"\nFull evidence accuracy: {acc_full*100:.1f}%  |  Audio-only accuracy: {acc_audio*100:.1f}%")
    print(eval_contract.split_line("Full-evidence accuracy", round(acc_full * matched_full), matched_full))
    print(eval_contract.split_line("Audio-only accuracy", round(acc_audio * matched_audio), matched_audio))
    print(f"Report written to {report_path}")


if __name__ == "__main__":
    main()
