#!/usr/bin/env python3
"""Pure inference helper for full_taxonomy_model_v1.npz."""
from __future__ import annotations

import json
import os

import numpy as np

SD = os.path.dirname(os.path.abspath(__file__))
MODEL = os.path.join(SD, "full_taxonomy_model_v1.npz")
META = os.path.join(SD, "full_taxonomy_model_v1.json")


def load_model(model_path=MODEL):
    z = np.load(model_path, allow_pickle=True)
    classes = np.asarray(z["classes"]).astype(str)
    return {
        "mean": np.asarray(z["mean"], dtype=np.float32),
        "scale": np.asarray(z["scale"], dtype=np.float32),
        "centroids": np.asarray(z["centroids"], dtype=np.float32),
        "classes": classes,
        "confidence_gate_90": float(z["confidence_gate_90"]),
        "confidence_gate_95": float(z["confidence_gate_95"]),
        "confidence_gate_98": float(z["confidence_gate_98"]),
        "similarity_gate_95": float(z["similarity_gate_95"]),
    }


def predict(embeddings, model=None):
    """Return labels, confidence, cosine similarity and accepted@95 mask."""
    m = model or load_model()
    X = np.asarray(embeddings, dtype=np.float32)
    if X.ndim != 2 or X.shape[1] != len(m["mean"]):
        raise ValueError(f"expected [n,{len(m['mean'])}] embeddings, got {X.shape}")
    Z = (X - m["mean"]) / (m["scale"] + 1e-9)
    Z /= np.linalg.norm(Z, axis=1, keepdims=True) + 1e-9
    sims = Z @ m["centroids"].T
    idx = sims.argmax(axis=1)
    logits = (sims - sims.max(axis=1, keepdims=True)) * 8.0
    probs = np.exp(logits - logits.max(axis=1, keepdims=True))
    probs /= probs.sum(axis=1, keepdims=True)
    conf = probs.max(axis=1)
    labels = m["classes"][idx]
    accepted = (conf >= m["confidence_gate_95"]) & \
               (sims.max(axis=1) >= m["similarity_gate_95"])
    return labels, conf, sims.max(axis=1), accepted


def metadata():
    with open(META) as f:
        return json.load(f)
