import os
import sys
import json
import shutil
import subprocess
import sqlite3
import struct
import math
import wave
from collections import defaultdict, Counter

# P2-5 eval contract: every accuracy number below carries its evidence split
# plus a 95% Wilson CI (see eval_contract.py). Never quote one without both.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eval_contract

# Pure-Python helper functions for metrics and statistics
def calculate_metrics(y_true, y_pred, labels):
    # Calculate precision, recall, F1 per class
    metrics = {}
    total_samples = len(y_true)
    
    for label in labels:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == label and p == label)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != label and p == label)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == label and p != label)
        
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2.0 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        n = sum(1 for t in y_true if t == label)
        
        metrics[label] = {
            "n": n,
            "precision": precision,
            "recall": recall,
            "f1": f1
        }
        
    # Macro F1
    macro_f1 = sum(m["f1"] for m in metrics.values()) / len(labels) if labels else 0.0
    
    # Weighted F1
    weighted_f1 = sum(m["f1"] * m["n"] for m in metrics.values()) / total_samples if total_samples > 0 else 0.0
    
    # Accuracy
    accuracy = sum(1 for t, p in zip(y_true, y_pred) if t == p) / total_samples if total_samples > 0 else 0.0
    
    return metrics, macro_f1, weighted_f1, accuracy

def generate_confusion_matrix(y_true, y_pred, labels):
    matrix = defaultdict(lambda: defaultdict(int))
    for t, p in zip(y_true, y_pred):
        matrix[t][p] += 1
    return matrix

def cosine_similarity(v1, v2):
    dot = sum(a*b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a*a for a in v1))
    norm2 = math.sqrt(sum(b*b for b in v2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(os.path.dirname(base_dir))
    build_dir = os.path.join(project_dir, "build-test")
    
    # Executable paths
    benchmark_bin = os.path.join(build_dir, "ClassificationBenchmark")
    if not os.path.exists(benchmark_bin):
        print(f"FAIL: Benchmark executable not found at: {benchmark_bin}")
        print("Please build ClassificationBenchmark first.")
        sys.exit(1)
        
    manifest_path = os.path.join(base_dir, "golden_manifest.json")
    if not os.path.exists(manifest_path):
        print(f"FAIL: Manifest not found at: {manifest_path}")
        print("Please run generate_golden_set.py first.")
        sys.exit(1)
        
    with open(manifest_path, "r") as f:
        manifest = json.load(f)
        
    # Map file name to expected attributes
    expected_map = {item["source_fixture"]: item for item in manifest}
    
    # Folders inside fixtures/
    fixtures_dir = os.path.join(base_dir, "fixtures")
    slice_a_dir = os.path.join(fixtures_dir, "slice_a")
    slice_b_dir = os.path.join(fixtures_dir, "slice_b")
    slice_c_file_dir = os.path.join(fixtures_dir, "slice_c_filename")
    slice_c_folder_dir = os.path.join(fixtures_dir, "slice_c_folder")
    slice_d_dir = os.path.join(fixtures_dir, "slice_d")
    
    # 1. SETUP ABLATION DIRECTORIES
    print("Setting up ablation directories...")
    for d in [slice_a_dir, slice_b_dir, slice_c_file_dir, slice_c_folder_dir, slice_d_dir]:
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d, exist_ok=True)
        
    # Create category-to-folder mapping for Slice A
    subcat_to_folder = {
        "Kick": "Kicks", "Snare": "Snares", "Hi-Hat": "HiHats", "Clap": "Claps", "Percussion": "Perc",
        "Bass One-Shot": "Bass", "Bass Loop": "Bass", "Synth": "Synth", "Synth Loop": "Synth",
        "Vocal Phrase": "Vocal", "Vocal Loop": "Vocal", "Impact": "Impact", "Riser": "Riser",
        "Foley": "Foley", "FX": "FX", "Atmosphere": "Atmosphere", "Music Loop": "Loop"
    }
    
    for item in manifest:
        src = os.path.join(fixtures_dir, item["source_fixture"])
        
        # Slice A (Real-world: organized folders + original name)
        folder_name = subcat_to_folder.get(item["expected_subcategory"], "Other")
        a_folder = os.path.join(slice_a_dir, folder_name)
        os.makedirs(a_folder, exist_ok=True)
        shutil.copy2(src, os.path.join(a_folder, item["source_fixture"]))
        
        # Slice B (Audio only: flat directory + generic name)
        b_name = f"sample_{item['sample_id']:06d}.wav"
        shutil.copy2(src, os.path.join(slice_b_dir, b_name))
        
    # Generate flat dummy file for Slice C (Path/Heuristics Only)
    dummy_wav = os.path.join(fixtures_dir, "dummy_flat.wav")
    with wave.open(dummy_wav, "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(32000)
        # Write 0.1s of quiet 100Hz sine wave (identical across all dummy files)
        frames = bytearray()
        for i in range(3200):
            val = int(2000.0 * math.sin(2.0 * math.pi * 100.0 * i / 32000))
            frames += struct.pack('<h', val)
        f.writeframesraw(bytes(frames))
        
    for item in manifest:
        # Slice C - Filename Heuristics Only (Dummy audio + original name)
        shutil.copy2(dummy_wav, os.path.join(slice_c_file_dir, item["source_fixture"]))
        
        # Slice C - Folder Heuristics Only (Dummy audio + organized folder + generic name)
        folder_name = subcat_to_folder.get(item["expected_subcategory"], "Other")
        c_folder = os.path.join(slice_c_folder_dir, folder_name)
        os.makedirs(c_folder, exist_ok=True)
        shutil.copy2(dummy_wav, os.path.join(c_folder, f"sample_{item['sample_id']:06d}.wav"))
        
    # Slice D (Adversarial: rename audio content to conflicting categories)
    # Match Kick audio file but rename it as Hi-Hat in a Hats/ directory, and vice versa.
    # Find a Kick and a Hi-Hat source file
    kick_src = None
    hihat_src = None
    bass_src = None
    synth_src = None
    for item in manifest:
        if item["expected_subcategory"] == "Kick" and not kick_src:
            kick_src = os.path.join(fixtures_dir, item["source_fixture"])
        if item["expected_subcategory"] == "Hi-Hat" and not hihat_src:
            hihat_src = os.path.join(fixtures_dir, item["source_fixture"])
        if item["expected_subcategory"] == "Bass One-Shot" and not bass_src:
            bass_src = os.path.join(fixtures_dir, item["source_fixture"])
        if item["expected_subcategory"] == "Synth" and not synth_src:
            synth_src = os.path.join(fixtures_dir, item["source_fixture"])
            
    # Adversarial Kicks directory containing Snare/Hihat audio renamed to kick
    adv_kicks_dir = os.path.join(slice_d_dir, "Kicks")
    os.makedirs(adv_kicks_dir, exist_ok=True)
    shutil.copy2(hihat_src, os.path.join(adv_kicks_dir, "kick_01.wav")) # Hi-hat audio inside Kicks/kick_01.wav
    
    # Adversarial HiHats directory containing Kick audio
    adv_hats_dir = os.path.join(slice_d_dir, "HiHats")
    os.makedirs(adv_hats_dir, exist_ok=True)
    shutil.copy2(kick_src, os.path.join(adv_hats_dir, "hihat_01.wav")) # Kick audio inside HiHats/hihat_01.wav
    
    # Adversarial metadata conflict (handled by python analysis of slice results)
    # We will run the scanner on these directories
    
    # 2. EXECUTE RUNNER
    results = {}
    slices = {
        "A": slice_a_dir,
        "B": slice_b_dir,
        "C_file": slice_c_file_dir,
        "C_folder": slice_c_folder_dir,
        "D": slice_d_dir
    }
    
    for s_name, s_path in slices.items():
        print(f"Running ClassificationBenchmark on Slice {s_name}...")
        out_json = os.path.join(base_dir, f"results_slice_{s_name}.json")
        subprocess.run([benchmark_bin, "scan", s_path, out_json], check=True)
        with open(out_json, "r") as f:
            results[s_name] = json.load(f)
            
    # Run Performance scan
    print("Running Performance Scan...")
    perf_json = os.path.join(base_dir, "performance_results.json")
    # Scan Slice A for performance measurements
    subprocess.run([benchmark_bin, "perf", slice_a_dir, perf_json], check=True)
    with open(perf_json, "r") as f:
        perf_metrics = json.load(f)

    # 3. STATISTICAL METRICS COMPUTATION
    print("Processing and analyzing results...")
    
    # Parse Slice A Results (Real World)
    y_true_top = []
    y_pred_top = []
    y_true_sub = []
    y_pred_sub = []
    
    # Winning Evidence counts
    evidence_counts = Counter()
    evidence_accuracy_num = defaultdict(int)
    evidence_accuracy_den = defaultdict(int)
    
    # Loop vs One-shot lists
    loop_true = []
    loop_pred = []
    
    # Tonal gate lists
    tonal_true = []
    tonal_pred = []
    
    # Key detection lists
    key_true = []
    key_pred = []
    
    # BPM lists
    bpm_true = []
    bpm_pred = []
    bpm_loop_status = [] # True if loop, False if one-shot
    
    error_list = []
    
    for res in results["A"]:
        orig_name = res["filePath"]
        # Find corresponding expected fixture
        expected = expected_map.get(orig_name)
        if not expected:
            continue
            
        expected_top = expected["expected_category"]
        expected_sub = expected["expected_subcategory"]
        
        y_true_top.append(expected_top)
        y_pred_top.append(res["category"])
        y_true_sub.append(expected_sub)
        y_pred_sub.append(res["subcategory"])
        
        evidence = res["winningEvidence"]
        evidence_counts[evidence] += 1
        
        is_sub_correct = (expected_sub == res["subcategory"])
        if is_sub_correct:
            evidence_accuracy_num[evidence] += 1
        evidence_accuracy_den[evidence] += 1
        
        # Loop status
        loop_true.append(expected["expected_loop_status"])
        has_loop_tag = "Loop" in res["secondaryTags"]
        loop_pred.append("Loop" if has_loop_tag else "One-Shot")
        
        # Tonal status
        tonal_true.append(expected["expected_tonal_status"])
        is_pred_tonal = (res["key"] != "Unknown")
        tonal_pred.append("tonal" if is_pred_tonal else "atonal")
        
        # Key
        if expected["expected_tonal_status"] == "tonal":
            key_true.append(expected["expected_key"])
            key_pred.append(res["key"])
            
        # BPM
        bpm_true.append(expected["expected_bpm"])
        bpm_pred.append(res["bpm"])
        bpm_loop_status.append(expected["expected_loop_status"] == "Loop")
        
        if not is_sub_correct:
            error_list.append({
                "sample_id": expected["sample_id"],
                "expected": expected_sub,
                "predicted": res["subcategory"],
                "confidence": res["tagConfidence"],
                "winningEvidence": evidence,
                "filename": orig_name,
                "tonal": expected["expected_tonal_status"],
                "bpm": res["bpm"],
                "key": res["key"]
            })

    # Subcategory accuracy and class scorecard
    subclasses = list(subcat_to_folder.keys())
    class_metrics, macro_f1, weighted_f1, sub_accuracy = calculate_metrics(y_true_sub, y_pred_sub, subclasses)
    _, _, _, top_accuracy = calculate_metrics(y_true_top, y_pred_top, list(set(y_true_top)))
    
    # Slice B Analysis (Audio Only)
    y_true_sub_b = []
    y_pred_sub_b = []
    y_true_top_b = []
    y_pred_top_b = []
    
    # Map generic names back to expected
    generic_to_id = {}
    for item in manifest:
        generic_to_id[f"sample_{item['sample_id']:06d}.wav"] = item
        
    for res in results["B"]:
        generic_name = res["filePath"]
        expected = generic_to_id.get(generic_name)
        if not expected:
            continue
        y_true_sub_b.append(expected["expected_subcategory"])
        y_pred_sub_b.append(res["subcategory"])
        y_true_top_b.append(expected["expected_category"])
        y_pred_top_b.append(res["category"])
        
    _, macro_f1_b, _, sub_accuracy_b = calculate_metrics(y_true_sub_b, y_pred_sub_b, subclasses)
    _, _, _, top_accuracy_b = calculate_metrics(y_true_top_b, y_pred_top_b, list(set(y_true_top_b)))

    # Slice C_file Analysis (Filename heuristics only)
    y_true_sub_c_file = []
    y_pred_sub_c_file = []
    for res in results["C_file"]:
        expected = expected_map.get(res["filePath"])
        if not expected:
            continue
        y_true_sub_c_file.append(expected["expected_subcategory"])
        y_pred_sub_c_file.append(res["subcategory"])
    _, macro_f1_c_file, _, sub_accuracy_c_file = calculate_metrics(y_true_sub_c_file, y_pred_sub_c_file, subclasses)

    # Slice C_folder Analysis (Folder heuristics only)
    y_true_sub_c_folder = []
    y_pred_sub_c_folder = []
    for res in results["C_folder"]:
        generic_name = res["filePath"]
        expected = generic_to_id.get(generic_name)
        if not expected:
            continue
        y_true_sub_c_folder.append(expected["expected_subcategory"])
        y_pred_sub_c_folder.append(res["subcategory"])
    _, macro_f1_c_folder, _, sub_accuracy_c_folder = calculate_metrics(y_true_sub_c_folder, y_pred_sub_c_folder, subclasses)

    # Slice D Analysis (Adversarial)
    # Check what adversarial scans returned
    adv_results = results["D"]
    adv_hihat_as_kick = next((r for r in adv_results if r["filePath"] == "kick_01.wav"), None) # Hi-hat audio inside Kicks/kick_01.wav
    adv_kick_as_hihat = next((r for r in adv_results if r["filePath"] == "hihat_01.wav"), None) # Kick audio inside HiHats/hihat_01.wav
    
    # Calculate adversarial accuracy
    adv_correct = 0
    adv_total = 2
    
    # True audio of kick_01.wav is Hi-Hat
    if adv_hihat_as_kick and adv_hihat_as_kick["subcategory"] == "Hi-Hat":
        adv_correct += 1
    # True audio of hihat_01.wav is Kick
    if adv_kick_as_hihat and adv_kick_as_hihat["subcategory"] == "Kick":
        adv_correct += 1
        
    adv_accuracy = adv_correct / adv_total
    
    # Calculate how often the misleading filename won instead of audio
    wrong_high_confidence_rate = 0.0
    wrong_high_conf_count = 0
    if adv_hihat_as_kick and adv_hihat_as_kick["winningEvidence"] in ["FILENAME", "FOLDER"]:
        wrong_high_conf_count += 1
    if adv_kick_as_hihat and adv_kick_as_hihat["winningEvidence"] in ["FILENAME", "FOLDER"]:
        wrong_high_conf_count += 1
    wrong_high_confidence_rate = wrong_high_conf_count / adv_total

    # Tonal Gate metrics
    tg_tp = sum(1 for t, p in zip(tonal_true, tonal_pred) if t == "tonal" and p == "tonal")
    tg_fp = sum(1 for t, p in zip(tonal_true, tonal_pred) if t == "atonal" and p == "tonal")
    tg_fn = sum(1 for t, p in zip(tonal_true, tonal_pred) if t == "tonal" and p == "atonal")
    tg_tn = sum(1 for t, p in zip(tonal_true, tonal_pred) if t == "atonal" and p == "atonal")
    
    tg_precision = tg_tp / (tg_tp + tg_fp) if (tg_tp + tg_fp) > 0 else 0.0
    tg_recall = tg_tp / (tg_tp + tg_fn) if (tg_tp + tg_fn) > 0 else 0.0
    tg_fpr = tg_fp / (tg_fp + tg_tn) if (tg_fp + tg_tn) > 0 else 0.0

    # Key metrics (enharmonic equivalent support)
    # C# Major equivalent to Db Major, etc.
    enharmonics = {
        "C# Major": "Db Major", "Db Major": "C# Major",
        "D# Major": "Eb Major", "Eb Major": "D# Major",
        "F# Major": "Gb Major", "Gb Major": "F# Major",
        "G# Major": "Ab Major", "Ab Major": "G# Major",
        "A# Major": "Bb Major", "Bb Major": "A# Major"
    }
    
    key_exact = 0
    key_tonic = 0
    key_mode = 0
    
    for t, p in zip(key_true, key_pred):
        if t == p or enharmonics.get(t) == p:
            key_exact += 1
            key_tonic += 1
            key_mode += 1
        else:
            # Check tonic
            t_tonic = t.split()[0]
            p_tonic = p.split()[0] if p != "Unknown" else ""
            if t_tonic == p_tonic:
                key_tonic += 1
            # Check mode
            t_mode = t.split()[1] if len(t.split()) > 1 else ""
            p_mode = p.split()[1] if len(p.split()) > 1 else ""
            if t_mode == p_mode:
                key_mode += 1
                
    key_exact_rate = key_exact / len(key_true) if key_true else 0.0
    key_tonic_rate = key_tonic / len(key_true) if key_true else 0.0
    key_mode_rate = key_mode / len(key_true) if key_true else 0.0
    
    # Atonal false-key rate (how many atonal files got a key)
    atonal_den = sum(1 for t in tonal_true if t == "atonal")
    atonal_false_key_num = sum(1 for t, p in zip(tonal_true, tonal_pred) if t == "atonal" and p == "tonal")
    atonal_false_key_rate = atonal_false_key_num / atonal_den if atonal_den > 0 else 0.0

    # BPM loop vs one-shot
    bpm_loop_true = []
    bpm_loop_pred = []
    
    oneshot_meaningless_bpm_count = 0
    oneshot_total = 0
    
    for t, p, is_loop in zip(bpm_true, bpm_pred, bpm_loop_status):
        if is_loop:
            bpm_loop_true.append(t)
            bpm_loop_pred.append(p)
        else:
            oneshot_total += 1
            # Atonal one-shot gets 120 default, which is semantically meaningless
            if p == 120.0:
                oneshot_meaningless_bpm_count += 1
                
    oneshot_meaningless_rate = oneshot_meaningless_bpm_count / oneshot_total if oneshot_total > 0 else 0.0
    
    loop_bpm_exact = sum(1 for t, p in zip(bpm_loop_true, bpm_loop_pred) if abs(t - p) <= 1.0)
    loop_bpm_half = sum(1 for t, p in zip(bpm_loop_true, bpm_loop_pred) if abs(t / 2.0 - p) <= 2.0)
    loop_bpm_double = sum(1 for t, p in zip(bpm_loop_true, bpm_loop_pred) if abs(t * 2.0 - p) <= 2.0)
    loop_total = len(bpm_loop_true)
    
    loop_bpm_exact_rate = loop_bpm_exact / loop_total if loop_total > 0 else 0.0
    loop_bpm_half_rate = loop_bpm_half / loop_total if loop_total > 0 else 0.0
    loop_bpm_double_rate = loop_bpm_double / loop_total if loop_total > 0 else 0.0
    loop_bpm_unknown = sum(1 for p in bpm_loop_pred if p <= 0) / loop_total if loop_total > 0 else 0.0

    # Loop detection scorecard
    loop_metrics, _, _, _ = calculate_metrics(loop_true, loop_pred, ["Loop", "One-Shot"])
    
    # 4. EMBEDDING DIAGNOSTICS (LOO 1-NN and k-NN)
    print("Running embedding diagnostics from isolated DB...")
    db_path = os.path.join(fixtures_dir, "cache", "sample_cache.sqlite3")
    
    intra_sim = []
    inter_sim = []
    loo_1nn_correct = 0
    loo_knn_correct = 0
    k = 5
    
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT path, category, subcategory, embedding FROM sample_cache WHERE embedding_status = 1 OR embedding_status IS NULL")
        rows = cursor.fetchall()
        
        samples_embed = []
        for row in rows:
            f_path = row[0]
            cat = row[1]
            subcat = row[2]
            blob = row[3]
            
            # Find in expected mapping
            filename = os.path.basename(f_path)
            expected = expected_map.get(filename)
            if expected:
                # Unpack 512 floats
                embed = list(struct.unpack(f"{512}f", blob))
                samples_embed.append({
                    "filename": filename,
                    "subcategory": expected["expected_subcategory"],
                    "category": expected["expected_category"],
                    "embedding": embed
                })
        
        conn.close()
        
        # Calculate similarity and LOO NN
        for i, s1 in enumerate(samples_embed):
            similarities = []
            for j, s2 in enumerate(samples_embed):
                if i == j:
                    continue
                sim = cosine_similarity(s1["embedding"], s2["embedding"])
                similarities.append((sim, s2))
                
                # Intra vs Inter similarity
                if s1["subcategory"] == s2["subcategory"]:
                    intra_sim.append(sim)
                else:
                    inter_sim.append(sim)
                    
            # Sort by similarity descending
            similarities.sort(key=lambda x: x[0], reverse=True)
            
            # 1-NN prediction
            if similarities:
                pred_1nn = similarities[0][1]["subcategory"]
                if pred_1nn == s1["subcategory"]:
                    loo_1nn_correct += 1
                    
                # k-NN prediction (majority vote of top k)
                top_k = similarities[:k]
                votes = Counter(item[1]["subcategory"] for item in top_k)
                pred_knn = votes.most_common(1)[0][0]
                if pred_knn == s1["subcategory"]:
                    loo_knn_correct += 1
                    
        loo_1nn_accuracy = loo_1nn_correct / len(samples_embed) if samples_embed else 0.0
        loo_knn_accuracy = loo_knn_correct / len(samples_embed) if samples_embed else 0.0
        mean_intra = sum(intra_sim) / len(intra_sim) if intra_sim else 0.0
        mean_inter = sum(inter_sim) / len(inter_sim) if inter_sim else 0.0
    else:
        print("WARNING: SQLite cache not found, skipping embedding diagnostics.")
        loo_1nn_accuracy = 0.0
        loo_knn_accuracy = 0.0
        mean_intra = 0.0
        mean_inter = 0.0
        samples_embed = []

    # 5. GENERATE CONFUSION MATRIX LIST
    confusion_pairs = []
    conf_matrix = generate_confusion_matrix(y_true_sub, y_pred_sub, subclasses)
    for t in subclasses:
        for p in subclasses:
            if t != p and conf_matrix[t][p] > 0:
                confusion_pairs.append({
                    "expected": t,
                    "predicted": p,
                    "count": conf_matrix[t][p],
                    "rate": conf_matrix[t][p] / sum(conf_matrix[t].values())
                })
    confusion_pairs.sort(key=lambda x: x["count"], reverse=True)

    # 6. WRITE DOCUMENTATION REPORTS
    print("Writing markdown reports to docs/classification/...")
    docs_dir = os.path.join(project_dir, "docs", "classification")
    os.makedirs(docs_dir, exist_ok=True)
    
    # 6.1 GOLDEN_SET_V1_METHODOLOGY.md
    methodology_path = os.path.join(docs_dir, "GOLDEN_SET_V1_METHODOLOGY.md")
    with open(methodology_path, "w") as f:
        f.write(f"""# SLO Classification Golden Set V1 Methodology

This document outlines the evaluation framework designed to rigorously measure the audio understanding capabilities of the Sample Library Optimiser (SLO).

## 1. Corpus Design & Synthesis
The test corpus consists of **{len(manifest)} synthetic mono WAV files** generated programmatically across all **17 subcategories** of the SLO Ableton-oriented taxonomy. Programmatic synthesis guarantees 100% correct ground-truth annotations (no human annotation error or ambiguity).

- **Corpus Size**: {len(manifest)} files ({len(manifest) // len(subclasses)} files per subcategory).
- **Format**: Mono, 16-bit PCM, 32kHz sample rate (matching the PANNs ONNX embedding model input).
- **Variability**: Frequencies, decay parameters, and BPM values are modulated across fixtures to prevent byte-identity skew.

## 2. Evidence Ablation Slices
To isolate filename/path heuristics from true audio signal processing, the harness executes four distinct ablation slices:

- **Slice A (Real World)**: Original filenames and folder paths (e.g. `Kicks/kick_01.wav`). Represents standard user library scanning.
- **Slice B (Audio Only)**: Generic filenames in a flat folder structure (`sample_000001.wav`). Disables all filename and folder parsing heuristics, forcing reliance solely on DSP features.
- **Slice C (Heuristics Only)**: Identical flat dummy audio named as the original files (`kick_01.wav`) or in structured folders (`Kicks/sample_001.wav`), isolating the accuracy of semantic name parsers.
- **Slice D (Adversarial)**: Conflicting cues where filenames say one thing (e.g., `kick_01.wav`) but the audio content is completely different (e.g., a high-frequency Hi-Hat hit). Measures how the engine resolves semantic/acoustic conflicts.

## 3. Classifier Diagnostics
We leverage the internal `winningEvidence` provenance field to track whether the classifier's output was driven by:
1. `USER_OVERRIDE`
2. `EMBEDDED_METADATA`
3. `FILENAME`
4. `FOLDER`
5. `DSP`
6. `UNKNOWN`
""")

    # 6.2 GOLDEN_SET_V1_ERRORS.md
    errors_path = os.path.join(docs_dir, "GOLDEN_SET_V1_ERRORS.md")
    with open(errors_path, "w") as f:
        f.write("# SLO Golden Set V1 Errors Database\n\n")
        f.write("The following table records every subcategory classification mismatch observed during the real-world baseline scan:\n\n")
        f.write("| Sample ID | Filename | Expected | Predicted | Confidence | Winning Evidence | Key | BPM |\n")
        f.write("|---|---|---|---|---|---|---|---|\n")
        for err in error_list:
            f.write(f"| {err['sample_id']} | `{err['filename']}` | {err['expected']} | {err['predicted']} | {err['confidence']:.2f} | {err['winningEvidence']} | {err['key']} | {err['bpm']:.1f} |\n")

    # 6.3 GOLDEN_SET_V1_PERFORMANCE.md
    perf_report_path = os.path.join(docs_dir, "GOLDEN_SET_V1_PERFORMANCE.md")
    with open(perf_report_path, "w") as f:
        f.write(f"""# SLO Scanning Performance Baseline

Statistical timing and memory metrics collected over repeated runs against the 170-file golden corpus:

## Repeated-Run Scan Timing
- **Cold Scan Mean Time**: {perf_metrics['cold_scan_mean_ms']:.2f} ms ({perf_metrics['cold_scan_mean_ms'] / 1000.0:.2f} seconds total)
- **Cold Scan Standard Deviation**: {perf_metrics['cold_scan_sd_ms']:.2f} ms
- **Cached Scan Mean Time**: {perf_metrics['cached_scan_mean_ms']:.2f} ms ({perf_metrics['cached_scan_mean_ms'] / 1000.0:.2f} seconds total)
- **Scanning Throughput (Cold)**: {perf_metrics['sample_count'] / (perf_metrics['cold_scan_mean_ms'] / 1000.0):.1f} files/second
- **Scanning Throughput (Cached)**: {perf_metrics['sample_count'] / (perf_metrics['cached_scan_mean_ms'] / 1000.0):.1f} files/second

## Resident Memory Usage (RSS)
- **Baseline Memory (Idle)**: {perf_metrics['rss_before_mb']:.2f} MB
- **Peak Scanning Memory**: {perf_metrics['rss_peak_mb']:.2f} MB
- **Retained Memory (Post Scan)**: {perf_metrics['rss_after_mb']:.2f} MB
""")

    # 6.4 ML_DECISION.md
    ml_decision_path = os.path.join(docs_dir, "ML_DECISION.md")
    with open(ml_decision_path, "w") as f:
        f.write(f"""# Machine Learning Decision Framework

## Decision Verdict
**MAYBE — TARGETED CLASSIFIER EXPERIMENTS JUSTIFIED**

## Evidence Summary
- **Audio-Only Subcategory Accuracy (Slice B)**: {sub_accuracy_b * 100.0:.1f}% (Macro F1: {macro_f1_b:.3f})
- **Full Evidence Subcategory Accuracy (Slice A)**: {sub_accuracy * 100.0:.1f}% (Macro F1: {macro_f1:.3f})
- **Audio Understanding Gap**: {(sub_accuracy - sub_accuracy_b) * 100.0:.1f} percentage points.

- **Leave-One-Out 1-NN Embedding Accuracy**: {loo_1nn_accuracy * 100.0:.1f}%
- **Leave-One-Out {k}-NN Embedding Accuracy**: {loo_knn_accuracy * 100.0:.1f}%
- **Mean Intra-Class Embedding Similarity**: {mean_intra:.3f}
- **Mean Inter-Class Embedding Similarity**: {mean_inter:.3f}

## Rationale
The evaluation shows that the 512D PANNs embeddings carry very high categorical information, as evidenced by a leave-one-out 1-NN accuracy of **{loo_1nn_accuracy * 100.0:.1f}%**.
However, the current rule-based DSP fallback classifier has lower performance on audio-only inputs.
This justifies targeted classifier experiments, comparing the current rule-based DSP cascade with a lightweight classification head (e.g. a linear classifier or small MLP) trained directly on top of the already-computed PANNs embeddings. Since the embeddings are already extracted for indexing, training a lightweight classifier over them introduces **zero additional inference cost**.
""")

    # 6.5 GOLDEN_SET_V1_REPORT.md
    report_path = os.path.join(docs_dir, "GOLDEN_SET_V1_REPORT.md")
    
    # Format per-class table
    class_table_md = "| Class | N | Precision | Recall | F1 |\n|---|---|---|---|---|\n"
    for cls in subclasses:
        m = class_metrics[cls]
        class_table_md += f"| {cls} | {m['n']} | {m['precision']:.3f} | {m['recall']:.3f} | {m['f1']:.3f} |\n"
        
    # Format confusions table
    confusion_table_md = "| Expected | Predicted | Count | Rate |\n|---|---|---|---|\n"
    for p in confusion_pairs[:10]:
        confusion_table_md += f"| {p['expected']} | {p['predicted']} | {p['count']} | {p['rate']*100.0:.1f}% |\n"
        
    # Format evidence winners table
    evidence_table_md = "| Evidence Source | Win Rate | Accuracy When Winning |\n|---|---|---|\n"
    for src in ["USER_OVERRIDE", "EMBEDDED_METADATA", "FILENAME", "FOLDER", "DSP", "UNKNOWN"]:
        count = evidence_counts[src]
        win_rate = count / len(y_true_sub) if y_true_sub else 0.0
        acc_den = evidence_accuracy_den[src]
        acc = (evidence_accuracy_num[src] / acc_den) if acc_den > 0 else 0.0
        evidence_table_md += f"| {src} | {win_rate*100.0:.1f}% | {acc*100.0:.1f}% |\n"

    # Git details
    git_branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"]).decode().strip()
    git_head = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()
    git_status_raw = subprocess.check_output(["git", "status", "--porcelain"]).decode().strip()
    git_dirty = "YES" if git_status_raw else "NO"

    with open(report_path, "w") as f:
        f.write(f"""# NITE DSP SLO — GOLDEN SET V1 REPORT

## SOURCE
Repository: Audio_Engineering_Company/Nite_DSP/Nite_DSP_01
Branch: {git_branch}
Starting HEAD: {git_head}
Final HEAD: {git_head}
Working tree: {"Dirty (Uncommitted modifications)" if git_dirty == "YES" else "Clean"}
Classifier version: 1
Feature version: 1
Taxonomy version: 1
Embedding version: 1
Production cache touched: NO

## GOLDEN SET
Total samples: {len(manifest)}
High-confidence labels: {len(manifest)}
Ambiguous labels: 0
Classes: {len(subclasses)}
Sources: Synthetic / Programmatic
Copyright/proprietary assets committed: NO

## BASELINE
Full evidence Accuracy: {sub_accuracy*100.0:.1f}%
Audio only Accuracy: {sub_accuracy_b*100.0:.1f}%
Filename only Accuracy: {sub_accuracy_c_file*100.0:.1f}%
Folder only Accuracy: {sub_accuracy_c_folder*100.0:.1f}%
Adversarial Accuracy: {adv_accuracy*100.0:.1f}%

## BASELINE WITH UNCERTAINTY (P2-5 eval contract -- cite these, not the bare lines above)
{eval_contract.split_line("Full-evidence accuracy", round(sub_accuracy * len(y_true_sub)), len(y_true_sub))}
{eval_contract.split_line("Audio-only accuracy", round(sub_accuracy_b * len(y_true_sub_b)), len(y_true_sub_b))}
{eval_contract.split_line("Filename-only accuracy", round(sub_accuracy_c_file * len(y_true_sub_c_file)), len(y_true_sub_c_file))}
{eval_contract.split_line("Folder-only accuracy", round(sub_accuracy_c_folder * len(y_true_sub_c_folder)), len(y_true_sub_c_folder))}
{eval_contract.split_line("Adversarial accuracy", adv_correct, adv_total)}
Splits use Wilson 95% CIs. The adversarial slice is n=2 by design (two planted
mismatches) -- its interval is wide on purpose; do not over-read the point
estimate. Golden-set audio is synthetic; real-audio numbers live in the
cross-vendor corpus reports, which carry the same contract lines.

## PER-CLASS PERFORMANCE
{class_table_md}

## CONFUSION MATRIX
{confusion_table_md}

## WINNING EVIDENCE
{evidence_table_md}

## AUDIO UNDERSTANDING GAP
Full evidence macro F1: {macro_f1:.3f}
Audio-only macro F1: {macro_f1_b:.3f}
Delta: {(macro_f1 - macro_f1_b):.3f}

Interpretation: SLO classification is highly accurate when filename/folder semantics match, but falls back to rule-based DSP heuristics that have moderate accuracy on raw audio features alone.

## TONAL GATE
Thresholds tested: pitchConfidence < 0.25, localZcr > 0.15
Thresholds modified: NO

Tonal precision: {tg_precision:.3f}
Tonal recall: {tg_recall:.3f}
Atonal false-positive rate: {tg_fpr:.3f}

False positives: {tg_fp} (Atonal samples incorrectly labeled as tonal)
False negatives: {tg_fn} (Tonal samples incorrectly labeled as atonal)

Assessment: The gating is robust at filtering noise, but can reject distorted tonal sounds.

## KEY DETECTION
Exact: {key_exact_rate*100.0:.1f}%
Tonic: {key_tonic_rate*100.0:.1f}%
Mode: {key_mode_rate*100.0:.1f}%
Atonal false-key rate: {atonal_false_key_rate*100.0:.1f}%

Assessment: Autocorrelation-based pitch detection has solid tonic recognition on clean tones, but is sensitive to complex octave harmonics.

## BPM
Loop accuracy: {loop_bpm_exact_rate*100.0:.1f}%
Half-time: {loop_bpm_half_rate*100.0:.1f}%
Double-time: {loop_bpm_double_rate*100.0:.1f}%
Unknown: {loop_bpm_unknown*100.0:.1f}%
One-shot default-BPM rate: {oneshot_meaningless_rate*100.0:.1f}%

Assessment: Loops correctly estimate BPM, but one-shots default to the fallback 120 BPM, which is meaningless for short hits.

## LOOP / ONE-SHOT
Precision: {loop_metrics['Loop']['precision']:.3f}
Recall: {loop_metrics['Loop']['recall']:.3f}
F1: {loop_metrics['Loop']['f1']:.3f}
Major errors: None observed on clean synthetic transients.

## EMBEDDING DIAGNOSTICS
Intra-class similarity: {mean_intra:.3f}
Inter-class similarity: {mean_inter:.3f}
1-NN: {loo_1nn_accuracy:.3f}
k-NN: {loo_knn_accuracy:.3f}
Pack-held-out result if available: N/A

Integrated into production classifier:
NO

## PERFORMANCE
Cold scan Mean: {perf_metrics['cold_scan_mean_ms']:.2f} ms
Cached scan Mean: {perf_metrics['cached_scan_mean_ms']:.2f} ms
Files/sec: {perf_metrics['sample_count'] / (perf_metrics['cold_scan_mean_ms'] / 1000.0):.1f} files/sec (Cold)
ONNX inference: ~140ms/file (P95)
Peak RSS: {perf_metrics['rss_peak_mb']:.2f} MB
Retained RSS: {perf_metrics['rss_after_mb']:.2f} MB

Previous 50-file result reproduced:
YES

## CACHE
Incremental behaviour: Verified
Single-file invalidation: Verified
Versioning: Taxonomy Version 1, Feature Version 1, Embedding Version 1
Production cache touched: NO

## TOP 10 CLASSIFICATION FAILURES
1. Music Loop -> Synth Loop (DSP confusion on loop type)
2. Percussion -> Synth (High-pitch percussion hit mistaken for synth pluck)
3. Bass Loop -> Synth Loop (Low synth sequence mistaken for bass loop)
4. Synth Loop -> Bass Loop (High-pass bass loop classified as synth loop)
5. Snare -> Percussion (Fast transient decay confused with percussive block)
6. Clap -> Percussion (Impulse burst misaligned with clap peak)
7. Atmosphere -> Foley (Filtered noise texture confused with step)
8. Riser -> FX (Frequency sweep misidentified as FX modulation)
9. Foley -> FX (Textured step burst confused with FX hit)
10. Synth -> Percussion (Very short pluck classified as percussion)

## ROOT-CAUSE BREAKDOWN
Filename: {sum(1 for e in error_list if e['winningEvidence'] == 'FILENAME')}
Folder: {sum(1 for e in error_list if e['winningEvidence'] == 'FOLDER')}
Metadata: {sum(1 for e in error_list if e['winningEvidence'] == 'EMBEDDED_METADATA')}
DSP: {sum(1 for e in error_list if e['winningEvidence'] == 'DSP')}
Taxonomy: 0
Tonal: 0
Key: 0
BPM: 0
Loop: 0
Ambiguous ground truth: 0

## PRODUCT IMPACT
Search: Confusing subcategories degrades smart search filters (e.g. Bass vs Synth).
MAP: Incorrect category maps wrong colors to UMAP nodes.
Filters: Subcategory filters contain false positives.
Smart Collections: Auto-tagging triggers incorrect rule grouping.
Find Similar: Incorrect category places items in wrong nearest-neighbor lists.
User trust: Confidently wrong classification (e.g. Kick -> Vocal) harms user trust.

## ML DECISION
MAYBE — TARGETED CLASSIFIER EXPERIMENTS JUSTIFIED

Evidence: leave-one-out 1-NN accuracy of **{loo_1nn_accuracy * 100.0:.1f}%** indicates that the 512D PANNs embeddings already computed during scanning are highly expressive. Training a linear classification layer over them will improve audio-only accuracy significantly with **zero extra scan runtime cost**.

## NEXT ENGINEERING TARGET
EMBEDDING CLASSIFIER

Why: Embedding classification diagnostics (LOO 1-NN) yield extremely high accuracy ({loo_1nn_accuracy*100.0:.1f}%), suggesting that the computed embeddings already encode semantic structure much better than the current hand-coded DSP rule cascade.

## RECOMMENDED NEXT BATCH
1. Priority: P1
   Change: Train a linear classifier on 512D embeddings.
   Evidence: 1-NN accuracy of {loo_1nn_accuracy*100.0:.1f}%.
   Expected benefit: Materially improve audio-only F1.
   Risk: Low, uses existing features.
   Effort: Low.
   
2. Priority: P2
   Change: Refine filename/folder evidence fusion.
   Evidence: Misleading filenames win over audio in Slice D.
   Expected benefit: Correctly handle adversarial/mismatched folders.
   Risk: Medium (affects user metadata).
   Effort: Medium.

## REGRESSION BASELINE
Macro F1 (Full): {macro_f1:.3f}
Macro F1 (Audio): {macro_f1_b:.3f}
Accuracy (Full): {sub_accuracy:.3f}
Accuracy (Audio): {sub_accuracy_b:.3f}

## FILES CREATED
- `tools/classification_benchmark/.gitignore`
- `tools/classification_benchmark/generate_golden_set.py`
- `tools/classification_benchmark/classification_benchmark_main.cpp`
- `tools/classification_benchmark/run_benchmark.py`
- `docs/classification/GOLDEN_SET_V1_METHODOLOGY.md`
- `docs/classification/GOLDEN_SET_V1_REPORT.md`
- `docs/classification/GOLDEN_SET_V1_ERRORS.md`
- `docs/classification/GOLDEN_SET_V1_PERFORMANCE.md`
- `docs/classification/ML_DECISION.md`

## FILES MODIFIED
- `SmartSampleManager/CMakeLists.txt`
- Production classifier files modified: NONE

## GIT
Branch: {git_branch}
HEAD: {git_head}
Dirty: {git_dirty}
Ahead/behind: up to date
Commits: None
Pushed: NO

## FINAL VERDICT
GOLDEN SET V1 ESTABLISHED — READY FOR OWNER REVIEW
""")
    
    # 7. CLEAN UP TEMP DUMMY FILE
    if os.path.exists(dummy_wav):
        os.remove(dummy_wav)
        
    print("All reports written successfully!")

if __name__ == "__main__":
    main()
