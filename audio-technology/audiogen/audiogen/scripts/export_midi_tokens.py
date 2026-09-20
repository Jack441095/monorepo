#!/usr/bin/env python3
"""Dataset exporter for Phase D sequence model training."""

from __future__ import annotations
import json
import sys
from pathlib import Path

def main():
    root_dir = Path(__file__).resolve().parent.parent
    dataset_dir = root_dir / "artifacts" / "datasets"
    
    # Try finding the v006 arranged joint dataset first, then fallback
    input_path = dataset_dir / "arranged_joint" / "v006" / "arranged_joint_training.jsonl"
    if not input_path.exists():
        # Search for any arranged_joint_training.jsonl
        candidates = list(dataset_dir.glob("**/arranged_joint_training.jsonl"))
        if candidates:
            input_path = candidates[0]
        else:
            print("Error: arranged_joint_training.jsonl not found in artifacts/datasets.")
            sys.exit(1)
            
    print(f"Reading from {input_path}")
    
    # Collect all unique emotions
    emotions = set()
    rows = []
    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            rows.append(row)
            if "emotion" in row:
                emotions.add(row["emotion"])
                
    emotion_list = sorted(list(emotions))
    emotion_to_idx = {name: idx for idx, name in enumerate(emotion_list)}
    print(f"Found {len(emotion_list)} unique emotions: {emotion_list}")
    
    SEQ_LEN = 16
    examples = []
    
    for row in rows:
        emotion = row.get("emotion")
        root_note = row.get("root_note", 60)
        lead = row.get("lead", {})
        midi_notes = lead.get("midi")
        
        if not emotion or not midi_notes or not isinstance(midi_notes, list):
            continue
            
        emotion_idx = emotion_to_idx[emotion]
        
        # Convert midi notes to tokens
        tokens = []
        for note in midi_notes:
            if not isinstance(note, list) or len(note) < 2:
                continue
            pitch, duration_beats = note[0], note[1]
            
            # Rest token logic
            if pitch is None or not isinstance(pitch, (int, float)) or pitch < 0:
                pitch_delta = 12 # 12 represents a rest
            else:
                pitch_delta = int(pitch - root_note) % 12
                
            # Duration ticks (1 beat = 4 ticks, so sixteenth note = 1 tick)
            try:
                ticks = int(float(duration_beats) * 4)
            except (ValueError, TypeError):
                ticks = 4 # default to 1 beat
            ticks = max(1, min(64, ticks))
            
            tokens.append((pitch_delta, ticks))
            
        # Create sliding window sequences
        if len(tokens) < SEQ_LEN + 1:
            continue
            
        for i in range(len(tokens) - SEQ_LEN):
            seq = tokens[i : i + SEQ_LEN]
            target = tokens[i + SEQ_LEN]
            
            x_pitch = [t[0] for t in seq]
            x_duration = [t[1] for t in seq]
            y_pitch = target[0]
            y_duration = target[1]
            
            examples.append({
                "x_pitch": x_pitch,
                "x_duration": x_duration,
                "y_pitch": y_pitch,
                "y_duration": y_duration,
                "emotion_idx": emotion_idx
            })
            
    out_dir = dataset_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "neural_phrases.json"
    
    output_data = {
        "emotions": emotion_list,
        "examples": examples
    }
    
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2)
        
    print(f"Exported {len(examples)} sequence examples to {out_path}")

if __name__ == "__main__":
    main()
