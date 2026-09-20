#!/usr/bin/env python3
"""Train a logistic regression classifier on turn engagement signals and output topic multipliers."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
import numpy as np
from sklearn.linear_model import LogisticRegression

KENN_DIR = Path(__file__).resolve().parent.parent
DB_PATH = KENN_DIR / "chats" / "kenn.db"
OUTPUT_PATH = KENN_DIR / "artifacts" / "calibrated_confidence_multipliers.json"


def train_calibrator() -> dict:
    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH}. Returning empty multipliers.")
        return {}

    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT turn_id, explicit_rating, dwell_seconds, has_followup, followup_interval_seconds, route, topics FROM session_feedback"
        ).fetchall()
        conn.close()
    except Exception as e:
        print(f"Failed to query database: {e}")
        return {}

    if not rows:
        print("No feedback data collected yet.")
        return {}

    X = []
    y = []
    valid_rows = []

    for row in rows:
        rating = row["explicit_rating"]
        dwell = row["dwell_seconds"]
        has_followup = bool(row["has_followup"]) if row["has_followup"] is not None else False
        interval = row["followup_interval_seconds"]

        # Implicit label synthesis rule
        label = None
        if rating is not None:
            if int(rating) == 1:
                label = 1
            elif int(rating) == -1:
                label = 0
        else:
            if dwell is not None:
                if float(dwell) > 12.0 and not has_followup:
                    label = 1
                elif float(dwell) < 5.0 and has_followup:
                    label = 0

        if label is not None:
            f_dwell = float(dwell) if dwell is not None else 0.0
            f_followup = 1.0 if has_followup else 0.0
            f_interval = float(interval) if interval is not None else 0.0

            X.append([f_dwell, f_followup, f_interval])
            y.append(label)
            valid_rows.append(row)

    print(f"Found {len(X)} turns with clear helpfulness signals.")

    # Model training requirement
    if len(X) < 5 or len(set(y)) < 2:
        print("Insufficient training data or class imbalance. Skipping model fit and using frequency heuristics.")
        route_stats = {}
        topic_stats = {}
        for row, label in zip(valid_rows, y):
            route = row["route"]
            topics_json = row["topics"]
            
            if route:
                stats = route_stats.setdefault(route, {"good": 0, "total": 0})
                stats["total"] += 1
                if label == 1:
                    stats["good"] += 1
            
            if topics_json:
                try:
                    topics = json.loads(topics_json)
                    if isinstance(topics, list):
                        for t in topics:
                            stats = topic_stats.setdefault(t, {"good": 0, "total": 0})
                            stats["total"] += 1
                            if label == 1:
                                stats["good"] += 1
                except Exception:
                    pass

        multipliers = {"routes": {}, "topics": {}}
        for route, stats in route_stats.items():
            ratio = stats["good"] / stats["total"] if stats["total"] > 0 else 0.5
            multipliers["routes"][route] = round(0.8 + ratio * 0.4, 3)

        for topic, stats in topic_stats.items():
            ratio = stats["good"] / stats["total"] if stats["total"] > 0 else 0.5
            multipliers["topics"][topic] = round(0.8 + ratio * 0.4, 3)

        save_multipliers(multipliers)
        return multipliers

    # Fit Logistic Regression classifier
    X_arr = np.array(X)
    y_arr = np.array(y)
    
    clf = LogisticRegression(max_iter=1000)
    clf.fit(X_arr, y_arr)

    probs = clf.predict_proba(X_arr)[:, 1]

    route_probs = {}
    topic_probs = {}

    for row, prob in zip(valid_rows, probs):
        route = row["route"]
        topics_json = row["topics"]
        
        if route:
            probs_list = route_probs.setdefault(route, [])
            probs_list.append(prob)
            
        if topics_json:
            try:
                topics = json.loads(topics_json)
                if isinstance(topics, list):
                    for t in topics:
                        probs_list = topic_probs.setdefault(t, [])
                        probs_list.append(prob)
            except Exception:
                pass

    multipliers = {"routes": {}, "topics": {}}
    for route, p_list in route_probs.items():
        p_avg = sum(p_list) / len(p_list)
        mult = 1.0 + (p_avg - 0.5) * 0.6
        multipliers["routes"][route] = round(max(0.7, min(1.3, mult)), 3)

    for topic, p_list in topic_probs.items():
        p_avg = sum(p_list) / len(p_list)
        mult = 1.0 + (p_avg - 0.5) * 0.6
        multipliers["topics"][topic] = round(max(0.7, min(1.3, mult)), 3)

    save_multipliers(multipliers)
    return multipliers


def save_multipliers(multipliers: dict) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w") as f:
        json.dump(multipliers, f, indent=2)
    print(f"Exported calibrated confidence multipliers to {OUTPUT_PATH}")


if __name__ == "__main__":
    train_calibrator()
