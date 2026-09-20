"""
SLO real-corpus benchmark V2 -- same full-evidence vs audio-only ablation
methodology as run_real_corpus_benchmark.py (V1, see that script's docstring
for full rationale), re-run against a much larger corpus.

V1 was capped at 60 files/class, 15 files/vendor/class (620 files, 14
vendors) purely for runtime reasons -- not because more real data wasn't
available. V2 uses the exact same trusted vendor folders (no new labeling
work; ground truth still comes from each vendor's own folder naming) with
those caps removed, plus one new vendor (Black Lotus Audio x Dianna Artist
Pack), for 4,917 files across 15 vendors. See
build_real_corpus_v2.py for how the corpus itself was built.

This is a separate script rather than a parameterized version of the V1
script so V1 stays exactly reproducible as the historical record; V2
supersedes it as the current number to cite.

Usage:
    python3 run_real_corpus_v2_benchmark.py <path-to-ClassificationBenchmark-binary>

Requires fixtures/real_corpus_v2/{full_evidence,audio_only}/ and
fixtures/real_corpus_v2/real_corpus_v2_manifest.json to already exist --
produced by build_real_corpus_v2.py.
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
        print("Usage: run_real_corpus_v2_benchmark.py <path-to-ClassificationBenchmark-binary>")
        sys.exit(1)
    benchmark_bin = sys.argv[1]
    if not os.path.exists(benchmark_bin):
        print(f"FAIL: benchmark executable not found at {benchmark_bin}")
        sys.exit(1)

    base_dir = os.path.dirname(os.path.abspath(__file__))
    corpus_dir = os.path.join(base_dir, "fixtures", "real_corpus_v2")
    manifest_path = os.path.join(corpus_dir, "real_corpus_v2_manifest.json")
    full_dir = os.path.join(corpus_dir, "full_evidence")
    audio_dir = os.path.join(corpus_dir, "audio_only")

    for p in (manifest_path, full_dir, audio_dir):
        if not os.path.exists(p):
            print(f"FAIL: expected corpus artifact missing: {p}")
            print("Run build_real_corpus_v2.py first.")
            sys.exit(1)

    with open(manifest_path) as f:
        manifest = json.load(f)

    by_full_relpath = {os.path.basename(m["full_evidence_relpath"]): m for m in manifest}
    by_audio_name = {m["audio_only_filename"]: m for m in manifest}
    subclasses = sorted(set(m["expected_subcategory"] for m in manifest))

    print(f"Real corpus V2: {len(manifest)} files across {len(subclasses)} classes, "
          f"{len(set(m['source_vendor'] for m in manifest))} vendors")

    print("Running ClassificationBenchmark on full-evidence slice (real filenames + folders)...")
    full_out = os.path.join(base_dir, "results_real_corpus_v2_full.json")
    if os.path.exists(full_out):
        os.remove(full_out)
    subprocess.run([benchmark_bin, "scan", full_dir, full_out], check=True)
    with open(full_out) as f:
        full_results = json.load(f)

    print("Running ClassificationBenchmark on audio-only slice (generic filenames, flat dir)...")
    audio_out = os.path.join(base_dir, "results_real_corpus_v2_audio_only.json")
    if os.path.exists(audio_out):
        os.remove(audio_out)
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

    class_table = "| Class | N | Audio-only Accuracy |\n|---|---|---|\n"
    for cls in subclasses:
        m = class_metrics_audio.get(cls, {"n": 0, "recall": 0.0})
        class_table += f"| {cls} | {m['n']} | {m['recall']*100:.1f}% |\n"

    evidence_table = "| Evidence Source | Count | Accuracy When Winning |\n|---|---|---|\n"
    for ev, count in sorted(evidence_counts.items(), key=lambda x: -x[1]):
        acc = evidence_correct[ev] / count if count else 0.0
        evidence_table += f"| {ev} | {count} | {acc*100:.1f}% |\n"

    n_vendors = len(set(m["source_vendor"] for m in manifest))
    vendor_table = "| Vendor | Files |\n|---|---|\n"
    vendor_counts = defaultdict(int)
    for m in manifest:
        vendor_counts[m["source_vendor"]] += 1
    for v, n in sorted(vendor_counts.items(), key=lambda x: -x[1]):
        vendor_table += f"| {v} | {n} |\n"

    report = f"""# SLO Real-Corpus Cross-Vendor Accuracy Report V2

**Generated by:** `run_real_corpus_v2_benchmark.py`, corpus built by `build_real_corpus_v2.py`
**Supersedes:** `REAL_CORPUS_CROSS_VENDOR_V1_REPORT.md` (620 files, 14 vendors) --
kept as the historical record, not deleted.
**Corpus:** {len(manifest)} real, licensed, commercial sample-pack files across
{len(subclasses)} classes and {n_vendors} vendors, drawn from
`/Volumes/Jack_Gandy_1TB_SSD/testing-for-NITE-DSP/sample_pack_testing`. V1 was
capped at 60 files/class, 15/vendor/class purely for runtime reasons; V2 uses
every file in the exact same trusted, already-mapped vendor folders (no new
labeling work) with those caps removed, plus one new vendor (Black Lotus
Audio x Dianna Artist Pack -- Spoken Phrases + Sung Phrases -> Vocal Phrase;
its "Misc Sounds" folder was deliberately excluded as low-confidence, unlike
every other folder used here).
**Ground truth:** derived from each vendor pack's own folder naming (e.g. a
"Kicks" folder is trusted to contain kicks). Not manually verified per file --
directionally decisive at this sample size, not a certified label set.

## Headline numbers

| Metric | Full evidence (real filenames+folders) | Audio-only (generic names, flat dir) |
|---|---|---|
| Subcategory accuracy | {acc_full*100:.1f}% ({matched_full} matched) | {acc_audio*100:.1f}% ({matched_audio} matched) |
| Macro F1 | {macro_f1_full:.3f} | {macro_f1_audio:.3f} |

**Do not report a single blended accuracy number for this product.**
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

## Per-vendor file counts
{vendor_table}

## Errors on the full-evidence slice (should be rare -- filename/folder evidence is trusted)
Total errors: {len(errors_full)} / {matched_full}
"""
    if errors_full:
        report += "\n| Expected | Predicted | Evidence | Vendor | File |\n|---|---|---|---|---|\n"
        for e in errors_full[:40]:
            report += f"| {e['expected']} | {e['predicted']} | {e['evidence']} | {e['vendor']} | `{e['file']}` |\n"

    report += """
## Scope limitations (read before citing this report)
- Folder-name-derived ground truth, not hand-verified per file.
- Covers 13 of SLO's 17 taxonomy classes (Synth, Synth Loop, Vocal Loop, Music
  Loop had no reliably keyword-matchable vendor folders in this corpus scan --
  not evidence those classes work or don't work, just not measured here).
- Two classes remain thin even at this larger scale: Riser (25 files) and
  Bass Loop (27 files) -- the trusted vendor folders scanned here simply don't
  contain much real content in these categories. This is a real constraint of
  the available library, not a benchmark oversight; don't over-read these two
  classes' numbers.
- Real audio content, but skewed toward one-shots/short loops matching common
  vendor folder conventions -- may not represent every real-world library
  layout.
- Still a sample of the full ~28,330-file/34-vendor tester library, not all of
  it -- the remaining ~20 vendors either had too few files to matter (most
  under 10) or are organized in ways (DAW project exports, date/machine-name
  folders) that don't give free, confident category labels from folder names
  alone; they were deliberately not included here rather than mislabeled.
"""

    docs_dir = os.path.join(os.path.dirname(os.path.dirname(base_dir)), "docs", "classification")
    os.makedirs(docs_dir, exist_ok=True)
    report_path = os.path.join(docs_dir, "REAL_CORPUS_CROSS_VENDOR_V2_REPORT.md")
    with open(report_path, "w") as f:
        f.write(report)

    print(f"\nFull evidence accuracy: {acc_full*100:.1f}%  |  Audio-only accuracy: {acc_audio*100:.1f}%")
    print(eval_contract.split_line("Full-evidence accuracy", round(acc_full * matched_full), matched_full))
    print(eval_contract.split_line("Audio-only accuracy", round(acc_audio * matched_audio), matched_audio))
    print(f"Report written to {report_path}")


if __name__ == "__main__":
    main()
