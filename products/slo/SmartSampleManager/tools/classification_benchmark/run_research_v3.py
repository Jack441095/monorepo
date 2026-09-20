import os
import sys
import argparse
import json
import shutil
import sqlite3
import struct
import math
import random
import hashlib
from collections import defaultdict, Counter
import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, precision_recall_curve, auc, confusion_matrix
import torch
import torch.nn as nn
import torch.optim as optim


DEFAULT_ABSTENTION_THRESHOLD = 0.75
ABSTENTION_THRESHOLDS = (0.50, 0.60, 0.70, 0.75, 0.80, 0.90)
CACHE_EMBEDDING_DIM = 512

MANIFEST_NAME_FIELDS = ("filename", "original_filename", "audio_only_filename")
MANIFEST_PATH_FIELDS = (
    "path",
    "source_path",
    "local_relative_path",
    "relative_path",
    "full_evidence_relpath",
)


def build_manifest_lookup(manifest):
    """Index manifest identities without silently collapsing duplicate names."""
    by_name = defaultdict(list)
    for item in manifest:
        for field in MANIFEST_NAME_FIELDS:
            value = item.get(field)
            if value:
                bucket = by_name[str(value)]
                if not any(existing is item for existing in bucket):
                    bucket.append(item)
    return {name: items for name, items in by_name.items()}


def build_manifest_hash_lookup(manifest):
    """Index declared content hashes without silently collapsing collisions."""
    by_hash = defaultdict(list)
    for item in manifest:
        value = str(item.get("sha256", "")).strip().lower()
        if value:
            by_hash[value].append(item)
    return dict(by_hash)


def sha256_file(path):
    """Return a file's SHA-256 for identity fallback in research only."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_manifest_item(
    db_path,
    lookup,
    reject_ambiguous_basename=True,
    allow_basename_fallback=True,
    content_hash_lookup=None,
):
    """Resolve a cache row to one manifest item, or fail closed if ambiguous.

    Basenames are not globally unique across vendors. Prefer an exact or
    suffix path match against any known manifest path field; use a basename
    only when it maps to exactly one item. An ambiguous basename is a data
    integrity error, not a reason to guess a label. Callers scanning a
    superset cache should set ``allow_basename_fallback=False`` so an
    out-of-scope row is ignored unless its path identity matches; declared
    manifest rows are still required by ``validate_manifest_coverage``.
    """
    normalized_db_path = os.path.normpath(os.path.abspath(db_path))
    basename = os.path.basename(normalized_db_path)
    candidates = lookup.get(basename, [])

    path_matches = []
    seen_item_ids = set()
    for item_candidates in lookup.values():
        for item in item_candidates:
            if id(item) in seen_item_ids:
                continue
            seen_item_ids.add(id(item))
            for field in MANIFEST_PATH_FIELDS:
                value = item.get(field)
                if not value:
                    continue
                normalized_value = os.path.normpath(str(value))
                if normalized_db_path == normalized_value or normalized_db_path.endswith(
                    os.sep + normalized_value.lstrip(os.sep)
                ):
                    path_matches.append(item)
                    break

    if len(path_matches) == 1:
        return path_matches[0]
    if len(path_matches) > 1:
        raise RuntimeError(
            f"Manifest identity ambiguity for cache path {db_path!r}: "
            f"{len(path_matches)} path matches"
        )

    # Some qualification manifests intentionally use a fixture-relative path
    # or a privacy-preserving filename rather than the absolute path recorded
    # by the native cache.  A declared SHA-256 is a stronger identity than a
    # basename; use it only when the caller explicitly supplies a hash index,
    # and fail closed when the manifest contains a duplicate hash.
    if content_hash_lookup is not None and os.path.isfile(db_path):
        content_hash = sha256_file(db_path)
        hash_matches = content_hash_lookup.get(content_hash, [])
        if len(hash_matches) == 1:
            return hash_matches[0]
        if len(hash_matches) > 1:
            raise RuntimeError(
                f"Manifest content-hash ambiguity for cache path {db_path!r}: "
                f"{len(hash_matches)} rows share {content_hash}"
            )

    if allow_basename_fallback and len(candidates) == 1:
        return candidates[0]
    if allow_basename_fallback and len(candidates) > 1:
        if not reject_ambiguous_basename:
            return None
        raise RuntimeError(
            f"Manifest basename ambiguity for cache path {db_path!r}: "
            f"{len(candidates)} manifest rows share {basename!r}; "
            "add a path identity"
        )
    return None


def validate_manifest_coverage(manifest, matched_item_ids):
    """Reject a scorecard whose declared manifest is only partially cached."""
    missing = [
        item for item in manifest
        if id(item) not in matched_item_ids
    ]
    if missing:
        examples = [
            item.get("filename")
            or item.get("original_filename")
            or item.get("audio_only_filename")
            or item.get("local_relative_path")
            for item in missing[:5]
        ]
        raise RuntimeError(
            f"Manifest/cache coverage failure: {len(missing)} declared rows "
            f"have no usable cache embedding; examples={examples}"
        )


def validate_cache_schema(conn, db_path):
    """Require the current cache table before reading research inputs."""
    try:
        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(sample_cache)").fetchall()
        }
    except sqlite3.Error as exc:
        raise RuntimeError(
            f"Cache contract failure for {db_path!r}: cannot inspect SQLite schema"
        ) from exc

    required = {"path", "embedding", "embedding_status"}
    if not columns:
        raise RuntimeError(
            f"Cache contract failure for {db_path!r}: missing sample_cache table"
        )
    missing = sorted(required - columns)
    if missing:
        raise RuntimeError(
            f"Cache contract failure for {db_path!r}: sample_cache is missing "
            f"columns {missing}"
        )


def decode_cache_embedding(blob, cache_path):
    """Decode and validate one current-contract float32 embedding."""
    if not blob:
        return None

    try:
        raw = bytes(blob)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(
            f"Cache embedding contract failure for {cache_path!r}: embedding is not bytes"
        ) from exc

    expected_bytes = CACHE_EMBEDDING_DIM * struct.calcsize("f")
    if len(raw) != expected_bytes:
        raise RuntimeError(
            f"Cache embedding contract failure for {cache_path!r}: expected "
            f"{CACHE_EMBEDDING_DIM} float32 values ({expected_bytes} bytes), "
            f"got {len(raw)} bytes"
        )

    embed = np.asarray(
        struct.unpack(f"{CACHE_EMBEDDING_DIM}f", raw),
        dtype=np.float32,
    )
    norm = np.linalg.norm(embed)
    if not np.isfinite(embed).all() or not np.isfinite(norm) or norm <= 0.0:
        raise RuntimeError(
            f"Cache embedding contract failure for {cache_path!r}: embedding "
            "must be finite and nonzero"
        )
    return embed

def cosine_similarity_np(a, b):
    norm_a = np.linalg.norm(a, axis=1, keepdims=True)
    norm_b = np.linalg.norm(b, axis=1, keepdims=True)
    norm_a[norm_a == 0] = 1e-9
    norm_b[norm_b == 0] = 1e-9
    return np.dot(a, b.T) / np.dot(norm_a, norm_b.T)

def calculate_ece(y_true_indices, y_prob, n_bins=10):
    ece = 0.0
    confidences = np.max(y_prob, axis=1)
    predictions = np.argmax(y_prob, axis=1)
    for i in range(n_bins):
        bin_lower = i / n_bins
        bin_upper = (i + 1) / n_bins
        in_bin = (confidences >= bin_lower) & (confidences < bin_upper)
        prop_in_bin = np.mean(in_bin)
        if prop_in_bin > 0:
            accuracy_in_bin = np.mean(predictions[in_bin] == y_true_indices[in_bin])
            avg_confidence_in_bin = np.mean(confidences[in_bin])
            ece += prop_in_bin * np.abs(avg_confidence_in_bin - accuracy_in_bin)
    return ece

def calculate_brier_score(y_true_onehot, y_prob):
    return np.mean(np.sum((y_prob - y_true_onehot)**2, axis=1))

def calculate_fpr_at_95_tpr(y_true, scores):
    # y_true: 1 for In-distribution, 0 for OOD
    from sklearn.metrics import roc_curve
    fpr, tpr, thresholds = roc_curve(y_true, scores)
    for f, t in zip(fpr, tpr):
        if t >= 0.95:
            return f
    return 1.0


def calculate_energy(logits, temperature):
    """Return the research-only energy score for a batch of classifier logits.

    Energy is defined as ``-T * logsumexp(logits / T)``. Lower energy is
    expected for in-distribution samples, so callers should negate this value
    when they need the existing convention of a higher-is-more-known OOD
    score. This function deliberately does not alter the production
    classifier or its centroid OOD gate.
    """
    values = np.asarray(logits, dtype=np.float64)
    if values.ndim != 2:
        raise ValueError("energy logits must be a two-dimensional array")
    if not np.isfinite(values).all():
        raise ValueError("energy logits must be finite")
    if not np.isfinite(temperature) or temperature <= 0.0:
        raise ValueError("energy temperature must be finite and positive")
    if values.shape[0] == 0:
        return np.empty(0, dtype=np.float64)

    scaled = values / float(temperature)
    row_max = np.max(scaled, axis=1, keepdims=True)
    stable_logsumexp = row_max[:, 0] + np.log(
        np.sum(np.exp(scaled - row_max), axis=1)
    )
    return -float(temperature) * stable_logsumexp

def calculate_f1_score(y_true, y_pred, labels):
    metrics = {}
    macro_f1 = 0.0
    for label in labels:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == label and p == label)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != label and p == label)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == label and p != label)
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2.0 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        metrics[label] = {"precision": precision, "recall": recall, "f1": f1}
        macro_f1 += f1
    macro_f1 /= len(labels) if len(labels) > 0 else 1.0
    accuracy = sum(1 for t, p in zip(y_true, y_pred) if t == p) / len(y_true) if len(y_true) > 0 else 0.0
    return accuracy, macro_f1, metrics


def build_abstention_rows(
    known_predictions,
    known_labels,
    known_confidences,
    ood_confidences,
    thresholds,
):
    """Build leakage-safe known/OOD acceptance measurements for each threshold."""
    rows = []
    for threshold in thresholds:
        known_accepted = known_confidences >= threshold
        ood_accepted = ood_confidences >= threshold
        accepted_count = int(np.sum(known_accepted))
        rows.append({
            "threshold": threshold,
            "known_count": int(len(known_labels)),
            "accepted_known_count": accepted_count,
            "coverage": float(np.mean(known_accepted)),
            "abstention_count": int(len(known_labels) - accepted_count),
            "abstention_rate": float(np.mean(~known_accepted)),
            "accepted_known_accuracy": float(
                np.mean(known_predictions[known_accepted] == known_labels[known_accepted])
            ) if accepted_count else 0.0,
            "mean_known_confidence": float(np.mean(known_confidences)),
            "mean_accepted_known_confidence": float(
                np.mean(known_confidences[known_accepted])
            ) if accepted_count else 0.0,
            "ood_count": int(len(ood_confidences)),
            "false_known_ood_count": int(np.sum(ood_accepted)),
            "false_known_ood_rate": float(np.mean(ood_accepted)) if len(ood_confidences) else None,
        })
    return rows


def validate_research_metadata(labels, families, vendors, ood_vendors, expected_classes):
    """Reject research metadata that cannot support the L-05 claims."""
    errors = []
    label_set = set(labels)
    missing = sorted(set(expected_classes) - label_set)
    unexpected = sorted(label_set - set(expected_classes))
    if missing or unexpected:
        errors.append(f"taxonomy coverage incomplete: missing={missing}, unexpected={unexpected}")
    if len(set(vendors)) < 2:
        errors.append("known evaluation set must contain at least two vendors")
    if len(set(ood_vendors)) < 2:
        errors.append("OOD evaluation set must contain at least two vendors")

    class_families = defaultdict(set)
    labels_by_family = defaultdict(set)
    for label, family in zip(labels, families):
        if not family:
            errors.append(f"known sample for {label} is missing source_family")
            continue
        class_families[label].add(family)
        labels_by_family[family].add(label)
    insufficient = {
        label: len(class_families[label])
        for label in expected_classes
        if len(class_families[label]) < 5
    }
    if insufficient:
        errors.append(f"classes lack five source families: {insufficient}")
    mixed = {
        family: sorted(labels_for_family)
        for family, labels_for_family in labels_by_family.items()
        if len(labels_for_family) > 1
    }
    if mixed:
        errors.append(f"source families carry mixed labels: {list(mixed)[:5]}")
    if errors:
        raise RuntimeError("Cannot run L-05 research qualification: " + "; ".join(errors))

class TemperatureScaler(nn.Module):
    def __init__(self):
        super().__init__()
        # Optimize an unconstrained raw value but expose a strictly positive
        # temperature.  A zero/negative scale would invalidate confidence and
        # OOD measurements and could reverse the logits' ordering.
        initial_raw = math.log(math.expm1(1.0))
        self.raw_temperature = nn.Parameter(torch.tensor([initial_raw]))

    @property
    def temperature(self):
        return torch.nn.functional.softplus(self.raw_temperature).clamp_min(1e-6)

    def forward(self, logits):
        return logits / self.temperature


def build_argument_parser():
    parser = argparse.ArgumentParser(description="Run leakage-controlled SLO classification research")
    parser.add_argument("--db-path", help="SQLite cache to read; defaults to the candidate fixture cache")
    parser.add_argument("--manifest-path", help="Dataset manifest to read; defaults to the candidate manifest")
    parser.add_argument(
        "--output-dir",
        help=(
            "Directory for generated qualification artifacts; defaults outside "
            "the SmartSampleManager source tree"
        ),
    )
    parser.add_argument(
        "--weights-output",
        help="Explicit output path for generated runtime weights; omitted by default to protect the frozen runtime header",
    )
    return parser


def resolve_output_dir(base_dir, project_dir, requested_output_dir=None):
    """Resolve generated artifacts outside the product source tree."""
    default_dir = os.path.join(project_dir, "..", "_artifacts", "classification_benchmark_v3")
    output_dir = os.path.realpath(requested_output_dir or default_dir)
    source_root = os.path.realpath(project_dir)
    if os.path.commonpath([output_dir, source_root]) == source_root:
        raise ValueError(
            "qualification output must be outside the SmartSampleManager source tree: "
            f"{output_dir}"
        )
    return output_dir


def main(argv=None):
    args = build_argument_parser().parse_args(argv)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(os.path.dirname(base_dir))
    try:
        output_dir = resolve_output_dir(base_dir, project_dir, args.output_dir)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    os.makedirs(output_dir, exist_ok=True)
    
    db_path = args.db_path or os.path.join(project_dir, "fixtures", "cache", "sample_cache.sqlite3")
    manifest_path = args.manifest_path or os.path.join(base_dir, "dataset_manifest.json")
    
    with open(manifest_path, "r") as f:
        manifest = json.load(f)
    shutil.copy2(manifest_path, os.path.join(output_dir, "dataset_manifest.json"))
        
    manifest_lookup = build_manifest_lookup(manifest)
    manifest_hash_lookup = build_manifest_hash_lookup(manifest)

    try:
        conn = sqlite3.connect(db_path)
        validate_cache_schema(conn, db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT path, category, subcategory, embedding FROM sample_cache WHERE embedding_status = 1 OR embedding_status IS NULL")
        rows = cursor.fetchall()
    except sqlite3.Error as exc:
        raise RuntimeError(
            f"Cache contract failure for {db_path!r}: cannot read sample_cache"
        ) from exc
    finally:
        if "conn" in locals():
            conn.close()
    
    real_embeddings = []
    real_labels = []
    real_packs = []
    real_vendors = []
    real_filenames = []
    real_families = []
    
    ood_embeddings = []
    ood_filenames = []
    ood_vendors = []
    matched_manifest_ids = set()
    
    for row in rows:
        db_path_str = row[0]
        filename = os.path.basename(db_path_str)
        blob = row[3]
        if not blob:
            continue
        embed = decode_cache_embedding(blob, db_path_str)
        
        # The native scan may intentionally cover a larger source root than
        # the labelled evaluation manifest. Only path/name identities that
        # resolve into the declared manifest belong in the scorecard; an
        # unmatched ambiguous basename is an out-of-scope row, not permission
        # to guess a label. Declared rows remain fail-closed via coverage
        # validation below.
        item = find_manifest_item(
            db_path_str,
            manifest_lookup,
            reject_ambiguous_basename=False,
            allow_basename_fallback=False,
            content_hash_lookup=manifest_hash_lookup,
        )
        if item:
            matched_manifest_ids.add(id(item))
            if item["expected_subcategory"] == "OOD":
                ood_embeddings.append(embed)
                ood_filenames.append(filename)
                ood_vendors.append(item.get("vendor_id"))
            else:
                real_embeddings.append(embed)
                real_labels.append(item["expected_subcategory"])
                real_packs.append(item["pack_id"])
                real_vendors.append(item["vendor_id"])
                real_filenames.append(filename)
                real_families.append(item["source_family"])
                
    conn.close()
    validate_manifest_coverage(manifest, matched_manifest_ids)
    
    X = np.array(real_embeddings)
    y = np.array(real_labels)
    packs = np.array(real_packs)
    vendors = np.array(real_vendors)
    filenames = np.array(real_filenames)
    families = np.array(real_families)
    
    print(f"Loaded {len(X)} real-world samples.")
    print(f"Loaded {len(ood_embeddings)} OOD samples.")
    
    # 1. DEDUPLICATION (LEAKAGE CONTROL)
    print("Running leakage control deduplication...")
    sim_matrix = cosine_similarity_np(X, X)
    np.fill_diagonal(sim_matrix, 0.0)
    
    keep_mask = np.ones(len(X), dtype=bool)
    duplicate_groups = []
    for i in range(len(X)):
        if not keep_mask[i]:
            continue
        duplicates = np.where(sim_matrix[i] > 0.995)[0]
        if len(duplicates) > 0:
            group = [filenames[i]] + [filenames[d] for d in duplicates]
            duplicate_groups.append(group)
            for d in duplicates:
                keep_mask[d] = False
                
    X_clean = X[keep_mask]
    y_clean = y[keep_mask]
    
    expected_taxonomy_classes = {
        "Kick", "Snare", "Hi-Hat", "Clap", "Percussion", "Bass One-Shot",
        "Bass Loop", "Synth", "Synth Loop", "Vocal Phrase", "Vocal Loop",
        "Impact", "Riser", "Foley", "FX", "Atmosphere", "Music Loop"
    }
    validate_research_metadata(
        y,
        families,
        vendors,
        ood_vendors,
        expected_taxonomy_classes,
    )
    classes = sorted(list(set(y_clean)))
    missing_classes = sorted(expected_taxonomy_classes.difference(classes))
    unexpected_classes = sorted(set(classes).difference(expected_taxonomy_classes))
    if missing_classes or unexpected_classes:
        raise RuntimeError(
            "Qualification dataset does not cover exactly the frozen 17-class "
            f"taxonomy; missing={missing_classes}, unexpected={unexpected_classes}"
        )
    class_to_idx = {c: i for i, c in enumerate(classes)}
    y_idx_clean = np.array([class_to_idx[l] for l in y_clean])
    
    families_clean = families[keep_mask]
    filenames_clean = filenames[keep_mask]
    
    print(f"Removed {len(X) - len(X_clean)} duplicates. {len(X_clean)} clean samples remaining across {len(classes)} classes.")
    
    # Write duplicate groups
    with open(os.path.join(output_dir, "duplicate_groups.json"), "w") as f:
        json.dump(duplicate_groups, f, indent=4)

    # 2. FLAT VS FACTORIZED MODELING
    # Setup Content & Temporal labels
    subcat_to_content = {
        "Kick": "Kick", "Snare": "Snare", "Hi-Hat": "Hi-Hat", "Clap": "Clap", "Percussion": "Percussion",
        "Bass One-Shot": "Bass", "Bass Loop": "Bass", "Synth": "Synth", "Synth Loop": "Synth",
        "Vocal Phrase": "Vocal", "Vocal Loop": "Vocal", "Impact": "Impact", "Riser": "Riser",
        "Foley": "Foley", "FX": "FX", "Atmosphere": "Atmosphere", "Music Loop": "Music"
    }
    subcat_to_temporal = {
        "Kick": "One-Shot", "Snare": "One-Shot", "Hi-Hat": "One-Shot", "Clap": "One-Shot", "Percussion": "One-Shot",
        "Bass One-Shot": "One-Shot", "Bass Loop": "Loop", "Synth": "One-Shot", "Synth Loop": "Loop",
        "Vocal Phrase": "Phrase", "Vocal Loop": "Loop", "Impact": "One-Shot", "Riser": "One-Shot",
        "Foley": "One-Shot", "FX": "One-Shot", "Atmosphere": "One-Shot", "Music Loop": "Loop"
    }
    
    content_labels = sorted(list(set(subcat_to_content.values())))
    temporal_labels = sorted(list(set(subcat_to_temporal.values())))
    content_to_idx = {c: i for i, c in enumerate(content_labels)}
    temporal_to_idx = {t: i for i, t in enumerate(temporal_labels)}
    
    y_content = np.array([content_to_idx[subcat_to_content[l]] for l in y_clean])
    y_temporal = np.array([temporal_to_idx[subcat_to_temporal[l]] for l in y_clean])
    OOD = np.array(ood_embeddings)

    # Published scorecards must use predictions made without fitting on the
    # scored sample.  The full-data model below is only for runtime-weight
    # export and review-queue generation.
    oof_logits = np.full((len(X_clean), len(classes)), np.nan, dtype=np.float64)
    oof_predictions = np.full(len(X_clean), -1, dtype=np.int64)
    ood_fold_logits = []

    # 5-Fold stratified, group-aware CV.  source_family is the leakage
    # boundary: related exports/variants must never be split between train
    # and test.  Keep this fail-closed; silently falling back to ordinary
    # StratifiedKFold would make the resulting scorecard look stronger than
    # the evaluation actually is.
    sgkf = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=42)
    
    flat_accs = []
    flat_macro_f1s = []
    
    fact_accs = []
    fact_macro_f1s = []
    
    all_class_indices = set(range(len(classes)))
    for fold_number, (train_idx, test_idx) in enumerate(
        sgkf.split(X_clean, y_idx_clean, groups=families_clean), start=1
    ):
        train_groups = set(families_clean[train_idx])
        test_groups = set(families_clean[test_idx])
        overlap = train_groups.intersection(test_groups)
        if overlap:
            raise RuntimeError(
                "Leakage-control failure: source_family appears in both train "
                f"and test folds: {sorted(overlap)[:5]}"
            )
        train_classes = set(y_idx_clean[train_idx])
        test_classes = set(y_idx_clean[test_idx])
        if train_classes != all_class_indices or test_classes != all_class_indices:
            raise RuntimeError(
                "Qualification dataset has insufficient per-fold support for "
                f"the frozen 17-class taxonomy in fold {fold_number}; "
                f"missing_train={sorted(all_class_indices - train_classes)}, "
                f"missing_test={sorted(all_class_indices - test_classes)}"
            )
        X_tr, X_te = X_clean[train_idx], X_clean[test_idx]
        y_tr, y_te = y_idx_clean[train_idx], y_idx_clean[test_idx]
        
        # Flat model
        lr_flat = LogisticRegression(multi_class='multinomial', solver='lbfgs', C=1.0, max_iter=200)
        lr_flat.fit(X_tr, y_tr)
        fold_logits = lr_flat.decision_function(X_te)
        pred_flat = lr_flat.predict(X_te)
        oof_logits[test_idx] = fold_logits
        oof_predictions[test_idx] = pred_flat
        if len(OOD) > 0:
            ood_fold_logits.append(lr_flat.decision_function(OOD))
        acc_f, f1_f, _ = calculate_f1_score(y_te, pred_flat, range(len(classes)))
        flat_accs.append(acc_f)
        flat_macro_f1s.append(f1_f)
        
        # Factorized Content & Temporal
        lr_c = LogisticRegression(multi_class='multinomial', solver='lbfgs', C=1.0, max_iter=200)
        lr_c.fit(X_tr, y_content[train_idx])
        pred_c = lr_c.predict(X_te)
        
        lr_t = LogisticRegression(multi_class='multinomial', solver='lbfgs', C=1.0, max_iter=200)
        lr_t.fit(X_tr, y_temporal[train_idx])
        pred_t = lr_t.predict(X_te)
        
        pred_fact = []
        for c_idx, t_idx in zip(pred_c, pred_t):
            c_lbl = content_labels[c_idx]
            t_lbl = temporal_labels[t_idx]
            
            # Map back to flat subcategory
            if c_lbl == "Bass" and t_lbl == "One-Shot":
                pred_fact.append(class_to_idx["Bass One-Shot"])
            elif c_lbl == "Bass" and t_lbl == "Loop":
                pred_fact.append(class_to_idx["Bass Loop"])
            elif c_lbl == "Synth" and t_lbl == "One-Shot":
                pred_fact.append(class_to_idx["Synth"])
            elif c_lbl == "Synth" and t_lbl == "Loop":
                pred_fact.append(class_to_idx["Synth Loop"])
            elif c_lbl == "Vocal" and t_lbl == "Phrase":
                pred_fact.append(class_to_idx["Vocal Phrase"])
            elif c_lbl == "Vocal" and t_lbl == "Loop":
                pred_fact.append(class_to_idx["Vocal Loop"])
            elif c_lbl == "Music" and t_lbl == "Loop":
                pred_fact.append(class_to_idx["Music Loop"])
            else:
                match_sub = None
                for sub in classes:
                    if subcat_to_content[sub] == c_lbl:
                        match_sub = sub
                        break
                pred_fact.append(class_to_idx[match_sub] if match_sub else 0)
                
        acc_fa, f1_fa, _ = calculate_f1_score(y_te, pred_fact, range(len(classes)))
        fact_accs.append(acc_fa)
        fact_macro_f1s.append(f1_fa)

    if np.isnan(oof_logits).any() or np.any(oof_predictions < 0):
        raise RuntimeError("Leakage-control failure: incomplete out-of-fold predictions")
    if len(OOD) > 0 and len(ood_fold_logits) != 5:
        raise RuntimeError("Leakage-control failure: incomplete cross-fitted OOD predictions")
        
    print(f"Flat Clean CV Accuracy: {np.mean(flat_accs)*100.0:.1f}%, Macro F1: {np.mean(flat_macro_f1s):.3f}")
    print(f"Factorized Clean CV Accuracy: {np.mean(fact_accs)*100.0:.1f}%, Macro F1: {np.mean(fact_macro_f1s):.3f}")

    # Train final classifier
    lr_final = LogisticRegression(multi_class='multinomial', solver='lbfgs', C=1.0, max_iter=300)
    lr_final.fit(X_clean, y_idx_clean)
    
    # 3. TEMPERATURE CALIBRATION
    # Calibrate the out-of-fold predictions, not the in-sample predictions
    # from lr_final.  This keeps the published confidence/OOD evidence tied
    # to the same leakage-controlled known-sample evaluation.
    logits_oof = oof_logits
    val_targets = torch.tensor(y_idx_clean, dtype=torch.long)
    val_logits = torch.tensor(logits_oof, dtype=torch.float32)
    
    scaler = TemperatureScaler()
    optimizer = optim.LBFGS(scaler.parameters(), lr=0.01, max_iter=50)
    def eval_loss():
        optimizer.zero_grad()
        loss = nn.CrossEntropyLoss()(scaler(val_logits), val_targets)
        loss.backward()
        return loss
    optimizer.step(eval_loss)
    T = scaler.temperature.item()
    
    probs_before = nn.Softmax(dim=1)(val_logits).numpy()
    probs_after = nn.Softmax(dim=1)(val_logits / T).numpy()

    # Keep acceptance/abstention measurements tied to the same OOF known
    # predictions used for the published scorecard.  This is measurement-only
    # and does not change the runtime classifier contract.
    known_predictions = np.argmax(probs_after, axis=1)
    known_confidences = np.max(probs_after, axis=1)
    
    y_true_onehot = np.zeros_like(probs_before)
    y_true_onehot[np.arange(len(y_idx_clean)), y_idx_clean] = 1.0
    
    ece_before = calculate_ece(y_idx_clean, probs_before)
    ece_after = calculate_ece(y_idx_clean, probs_after)
    brier_before = calculate_brier_score(y_true_onehot, probs_before)
    brier_after = calculate_brier_score(y_true_onehot, probs_after)
    
    # Save calibration report
    calibration_data = {
        "temperature": float(T),
        "ece_before": float(ece_before),
        "ece_after": float(ece_after),
        "brier_before": float(brier_before),
        "brier_after": float(brier_after)
    }
    with open(os.path.join(output_dir, "calibration.json"), "w") as f:
        json.dump(calibration_data, f, indent=4)

    # 4. OOD BENCHMARKING
    # Score OOD with each fold model and average the logits.  The known side
    # below is also out-of-fold, so the AUROC/FPR comparison is not between a
    # memorised known set and an unseen OOD set.
    logits_ood = np.mean(np.stack(ood_fold_logits), axis=0) if len(OOD) > 0 else np.empty((0, len(classes)))
    probs_ood = nn.Softmax(dim=1)(torch.tensor(logits_ood, dtype=torch.float32) / T).numpy()
    ood_confidences = np.max(probs_ood, axis=1) if len(OOD) > 0 else np.empty(0)

    abstention_rows = build_abstention_rows(
        known_predictions,
        y_idx_clean,
        known_confidences,
        ood_confidences,
        ABSTENTION_THRESHOLDS,
    )

    default_abstention = next(
        row for row in abstention_rows
        if row["threshold"] == DEFAULT_ABSTENTION_THRESHOLD
    )
    with open(os.path.join(output_dir, "abstention_metrics.json"), "w") as f:
        json.dump({
            "evaluation_provenance": "out_of_fold_predictions",
            "thresholds": abstention_rows,
            "default_threshold": DEFAULT_ABSTENTION_THRESHOLD,
        }, f, indent=4)
    
    # Evaluate OOD rejection metrics (1 for In-distribution, 0 for OOD)
    y_ood_eval = np.concatenate([np.ones(len(X_clean)), np.zeros(len(OOD))])
    
    # Methods: MSP, Entropy, Margin, and research-only Energy. Energy is
    # calculated from the same cross-fitted logits and calibrated temperature;
    # it is a measurement signal, not a production OOD-policy change.
    msp_scores = np.concatenate([np.max(probs_after, axis=1), np.max(probs_ood, axis=1)])
    
    ent_in = -np.sum(probs_after * np.log(probs_after + 1e-9), axis=1)
    ent_ood = -np.sum(probs_ood * np.log(probs_ood + 1e-9), axis=1)
    ent_scores = np.concatenate([-ent_in, -ent_ood]) # Higher entropy is OOD, so negative for TPR/FPR
    
    sorted_in = np.sort(probs_after, axis=1)
    margin_in = sorted_in[:, -1] - sorted_in[:, -2]
    sorted_ood = np.sort(probs_ood, axis=1)
    margin_ood = sorted_ood[:, -1] - sorted_ood[:, -2]
    margin_scores = np.concatenate([margin_in, margin_ood])

    energy_in = calculate_energy(logits_oof, T)
    energy_ood = calculate_energy(logits_ood, T)
    energy_scores = np.concatenate([-energy_in, -energy_ood])
    
    auroc_msp = roc_auc_score(y_ood_eval, msp_scores)
    auroc_ent = roc_auc_score(y_ood_eval, ent_scores)
    auroc_margin = roc_auc_score(y_ood_eval, margin_scores)
    auroc_energy = roc_auc_score(y_ood_eval, energy_scores)
    
    fpr_msp = calculate_fpr_at_95_tpr(y_ood_eval, msp_scores)
    fpr_ent = calculate_fpr_at_95_tpr(y_ood_eval, ent_scores)
    fpr_margin = calculate_fpr_at_95_tpr(y_ood_eval, margin_scores)
    fpr_energy = calculate_fpr_at_95_tpr(y_ood_eval, energy_scores)
    
    # Precision-Recall AUPR
    p_msp, r_msp, _ = precision_recall_curve(y_ood_eval, msp_scores)
    aupr_msp = auc(r_msp, p_msp)
    
    p_ent, r_ent, _ = precision_recall_curve(y_ood_eval, ent_scores)
    aupr_ent = auc(r_ent, p_ent)
    
    p_margin, r_margin, _ = precision_recall_curve(y_ood_eval, margin_scores)
    aupr_margin = auc(r_margin, p_margin)

    p_energy, r_energy, _ = precision_recall_curve(y_ood_eval, energy_scores)
    aupr_energy = auc(r_energy, p_energy)
    
    ood_results = {
        "MSP": {"AUROC": float(auroc_msp), "AUPR": float(aupr_msp), "FPR@95": float(fpr_msp)},
        "Entropy": {"AUROC": float(auroc_ent), "AUPR": float(aupr_ent), "FPR@95": float(fpr_ent)},
        "Margin": {"AUROC": float(auroc_margin), "AUPR": float(aupr_margin), "FPR@95": float(fpr_margin)},
        "Energy": {"AUROC": float(auroc_energy), "AUPR": float(aupr_energy), "FPR@95": float(fpr_energy), "definition": "-T*logsumexp(logits/T); research-only"},
        "acceptance_policy": {
            "threshold": DEFAULT_ABSTENTION_THRESHOLD,
            "known_coverage": default_abstention["coverage"],
            "known_false_unknown_rate": default_abstention["abstention_rate"],
            "ood_false_known_count": default_abstention["false_known_ood_count"],
            "ood_false_known_rate": default_abstention["false_known_ood_rate"],
        },
    }
    with open(os.path.join(output_dir, "ood_results.json"), "w") as f:
        json.dump(ood_results, f, indent=4)
        
    # Write OOD Failure Database (High-confidence OOD errors: false accepts)
    # Filter OOD samples accepted with confidence >= 0.75
    error_list = []
    for idx, (filename, prob_dist) in enumerate(zip(ood_filenames, probs_ood)):
        max_p = np.max(prob_dist)
        pred_idx = np.argmax(prob_dist)
        pred_lbl = classes[pred_idx]
        
        if max_p >= 0.75:
            error_list.append({
                "sample_id": idx + 1,
                "filename": filename,
                "predicted_class": pred_lbl,
                "confidence": float(max_p),
                "notes": "OOD sample falsely accepted as known class with high confidence"
            })
            
    df_err = pd.DataFrame(error_list)
    df_err.to_csv(os.path.join(output_dir, "error_database.csv"), index=False)

    # 5. EVIDENCE FUSION SIMULATION
    # Simulate virtual adversarial filename corpus
    # Filename says "Kick" but audio is Snare, etc.
    # We measure accuracy under override threshold
    correct_fusion = 0
    total_fusion = 0
    conflict_overrides = 0
    
    for sample_idx, (true_lbl, filename) in enumerate(zip(y_clean, filenames_clean)):
        # Generate misleading filename cue
        misleading_cue = "Kick" if true_lbl != "Kick" else "Snare"
        
        # Use the leakage-controlled out-of-fold classifier output for this
        # published adversarial measurement, not the full-data fit.
        probs = probs_after[sample_idx]
        pred_idx = np.argmax(probs)
        pred_lbl = classes[pred_idx]
        conf = probs[pred_idx]
        
        # Precedence Rule: if acoustic confidence > 0.75, override misleading filename
        if conf > 0.75:
            final_pred = pred_lbl
            conflict_overrides += 1
        else:
            final_pred = misleading_cue
            
        if final_pred == true_lbl:
            correct_fusion += 1
        total_fusion += 1
        
    fusion_acc = (correct_fusion / total_fusion) if total_fusion > 0 else 0.0
    print(f"Fusion Adversarial Accuracy (Override @ 0.75): {fusion_acc*100.0:.1f}%")

    # 6. EXPORT WEIGHTS & PARITY
    weights = lr_final.coef_
    biases = lr_final.intercept_
    
    classes_cpp = ", ".join(f"\"{c}\"" for c in classes)
    
    # Format weights for C++ constexpr representation
    weight_str_list = []
    for cls_w in weights:
        w_vals = ", ".join(f"{w}f" for w in cls_w)
        weight_str_list.append(f"    {{ {w_vals} }}")
        
    weights_cpp = ",\n".join(weight_str_list)
    biases_cpp = ", ".join(f"{b}f" for b in biases)
    
    if args.weights_output:
        weight_header_path = os.path.abspath(args.weights_output)
        os.makedirs(os.path.dirname(weight_header_path), exist_ok=True)
        with open(weight_header_path, "w") as f:
            f.write(f"""#pragma once

// Automated weights export for Nite DSP SLO AcousticClassifier V3.
// Generated from training on deduplicated KSHMR dataset.
// DO NOT EDIT MANUALLY.

namespace AcousticWeights
{{
    constexpr int modelVersion = 3;
    constexpr int embeddingVersion = 1;
    constexpr int taxonomyVersion = 1;
    constexpr int numClasses = {len(classes)};
    constexpr int embeddingDim = 512;
    constexpr float temperature = {T}f;

    const char* const classNames[numClasses] = {{ {classes_cpp} }};

    constexpr float weights[numClasses][embeddingDim] = {{
{weights_cpp}
    }};

    constexpr float biases[numClasses] = {{ {biases_cpp} }};
}}
""")
        print(f"Exported model weights to explicit path: {weight_header_path}")
    else:
        print("Skipped runtime weight export; pass --weights-output for an explicit experiment output path.")

    # Export parity references
    parity_list = []
    for idx in range(10):
        embed = X_clean[idx]
        expected_logits = np.dot(weights, embed) + biases
        expected_logits_t = expected_logits / T
        exp_logits_t_exp = np.exp(expected_logits_t - np.max(expected_logits_t))
        expected_probs = exp_logits_t_exp / np.sum(exp_logits_t_exp)
        sorted_probs = np.sort(expected_probs)
        margin = float(sorted_probs[-1] - sorted_probs[-2])
        
        parity_list.append({
            "filename": filenames_clean[idx],
            "embedding": [float(v) for v in embed],
            "expected_logits": [float(v) for v in expected_logits],
            "expected_probs": [float(v) for v in expected_probs],
            "predicted_subcategory": classes[np.argmax(expected_probs)],
            "probability": float(np.max(expected_probs)),
            "margin": margin
        })
        
    with open(os.path.join(output_dir, "parity_references.json"), "w") as f:
        json.dump(parity_list, f, indent=4)
        
    # Write standard CSV metrics
    # Per class metrics
    flat_pred_oof = oof_predictions
    _, _, class_f1_dict = calculate_f1_score(y_idx_clean, flat_pred_oof, range(len(classes)))
    
    per_class_rows = []
    default_accepted = known_confidences >= DEFAULT_ABSTENTION_THRESHOLD
    for c_idx, c_name in enumerate(classes):
        m = class_f1_dict[c_idx]
        class_mask = y_idx_clean == c_idx
        per_class_rows.append({
            "class": c_name,
            "support": int(np.sum(class_mask)),
            "precision": m["precision"],
            "recall": m["recall"],
            "f1": m["f1"],
            "coverage": float(np.mean(default_accepted[class_mask])) if np.any(class_mask) else 0.0,
            "abstention_rate": float(np.mean(~default_accepted[class_mask])) if np.any(class_mask) else 0.0,
            "mean_confidence": float(np.mean(known_confidences[class_mask])) if np.any(class_mask) else 0.0,
            "accepted_count": int(np.sum(default_accepted & class_mask)),
        })
    pd.DataFrame(per_class_rows).to_csv(os.path.join(output_dir, "per_class_metrics.csv"), index=False)
    
    # Confusion matrix
    conf_mat = confusion_matrix(y_idx_clean, flat_pred_oof, labels=range(len(classes)))
    pd.DataFrame(conf_mat, index=classes, columns=classes).to_csv(os.path.join(output_dir, "confusion_matrix.csv"))
    
    # Write metrics.json
    overall_acc, overall_f1, _ = calculate_f1_score(y_idx_clean, flat_pred_oof, range(len(classes)))
    metrics_summary = {
        "overall_accuracy": float(overall_acc),
        "overall_macro_f1": float(overall_f1),
        "evaluation_provenance": "out_of_fold_predictions",
        "group_key": "source_family",
        "taxonomy_class_count": len(classes),
        "abstention_threshold": DEFAULT_ABSTENTION_THRESHOLD,
        "coverage": default_abstention["coverage"],
        "confidence_mean": default_abstention["mean_known_confidence"],
        "false_unknown_rate": default_abstention["abstention_rate"],
        "abstention_rate": default_abstention["abstention_rate"],
        "false_known_ood_rate": default_abstention["false_known_ood_rate"],
        "cv_fold_accuracy_mean": float(np.mean(flat_accs)),
        "cv_fold_macro_f1_mean": float(np.mean(flat_macro_f1s)),
        "fusion_adversarial_accuracy": float(fusion_acc),
        "dataset_size_clean": len(X_clean),
        "ood_size": len(OOD)
    }
    with open(os.path.join(output_dir, "metrics.json"), "w") as f:
        json.dump(metrics_summary, f, indent=4)

    # 7. OWNER REVIEW QUEUE
    # Identify top 50 files for review (conflicts, rare classes, borderline margin)
    review_queue = []
    for idx, (embed, true_lbl, filename) in enumerate(zip(X_clean, y_clean, filenames_clean)):
        logits = np.dot(lr_final.coef_, embed) + lr_final.intercept_
        probs = nn.Softmax(dim=0)(torch.tensor(logits / T)).numpy()
        pred_idx = np.argmax(probs)
        pred_lbl = classes[pred_idx]
        conf = probs[pred_idx]
        
        # Confused or low margin
        sorted_probs = np.sort(probs)
        margin = float(sorted_probs[-1] - sorted_probs[-2])
        
        if pred_lbl != true_lbl or margin < 0.20:
            review_queue.append({
                "sample_id": idx + 1,
                "relative_path": f"fixtures/scan_subset/{filename}",
                "proposed_class": pred_lbl,
                "proposed_temporal_class": subcat_to_temporal[pred_lbl],
                "winning_evidence": "ACOUSTIC_CLASSIFIER",
                "confidence": float(conf),
                "ambiguity_reason": "Low classification margin or package classification mismatch" if pred_lbl == true_lbl else "Acoustic category conflict",
                "duplicate_group": "None",
                "source_family": families_clean[idx],
                "review_priority": "HIGH" if pred_lbl != true_lbl else "MEDIUM"
            })
            
    # Take top 50 prioritized
    review_queue.sort(key=lambda x: x["confidence"])
    review_queue = review_queue[:50]
    pd.DataFrame(review_queue).to_csv(os.path.join(output_dir, "owner_review_queue.csv"), index=False)
    print("Owner review queue generated.")

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2) from None
