# utils/midi_to_melody_data.py
# Project module `midi_to_melody_data` (utils).

# midi_to_melody_data.py
#//////////////////////////////////////////////////////////////////
# This module provides functions to convert monophonic MIDI files into sequences of (degree, duration) 
# tokens suitable for training melody generation models.
# It uses the mido library to parse MIDI files, extracts note events, 
# quantizes durations to a predefined set of allowed values, 
# and maps MIDI pitches to scale degrees based on a specified root and scale intervals.
# The main function, `midi_to_degree_duration`, 
# processes a single MIDI file, while `process_emotion_folder` can be used to process all MIDI files in a folder

import os
import pickle
from typing import List, Tuple

import mido

# Allowed durations (must match DURATIONS in markov.py)
DURATIONS = [0.25, 0.5, 1.0, 2.0, 4.0]

def midi_to_degree_duration(midi_path: str,
                            scale_intervals: List[int],
                            root_midi: int = 60,
                            ticks_per_beat: int = 480) -> List[Tuple[int, float]]:
    """
    Convert a monophonic MIDI file to (degree, duration) tokens.
    Returns empty list if unsuccessful.
    """
    mid = mido.MidiFile(midi_path)
    notes = []  # (start_tick, end_tick, pitch)

    for track in mid.tracks:
        abs_time = 0
        pending = {}
        for msg in track:
            abs_time += msg.time
            if msg.type == 'note_on' and msg.velocity > 0:
                pending[msg.note] = abs_time
            elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                if msg.note in pending:
                    start = pending.pop(msg.note)
                    notes.append((start, abs_time, msg.note))

    if not notes:
        return []

    notes.sort(key=lambda x: x[0])

    # Convert ticks to beats
    def ticks_to_beats(t):
        return t / ticks_per_beat

    sequence = []
    for start, end, pitch in notes:
        ticks_to_beats(start)
        dur_beats = ticks_to_beats(end - start)

        # Quantize duration to nearest allowed value
        dur_beats = min(DURATIONS, key=lambda d: abs(d - dur_beats))

        # Convert pitch to scale degree
        rel_pitch = pitch - root_midi
        pc = rel_pitch % 12

        # Find closest scale degree
        degree = min(range(len(scale_intervals)), key=lambda i: abs(scale_intervals[i] - pc))

        sequence.append((degree, dur_beats))

    return sequence


def process_emotion_folder(folder_path: str,
                          emotion_name: str,
                          scale_intervals: List[int],
                          root_midi: int = 60) -> List[List[Tuple[int, float]]]:
    """
    Process all MIDI files in a folder and return list of melody sequences.
    """
    sequences = []
    for file in os.listdir(folder_path):
        if file.endswith('.mid') or file.endswith('.midi'):
            path = os.path.join(folder_path, file)
            seq = midi_to_degree_duration(path, scale_intervals, root_midi)
            if len(seq) >= 4:  # ignore very short melodies
                sequences.append(seq)
                print(f"  Loaded {file}: {len(seq)} notes")
    return sequences


if __name__ == "__main__":
    # Example usage – adjust paths as needed
    from data.music_data import EMOTION_BY_NAME

    base_dir = "data/midi"
    output_file = "melody_training_data.pkl"

    all_data = {}

    for emotion_name in EMOTION_BY_NAME.keys():
        folder = os.path.join(base_dir, emotion_name)
        if not os.path.isdir(folder):
            continue

        emotion = EMOTION_BY_NAME[emotion_name]
        print(f"Processing {emotion_name}...")
        seqs = process_emotion_folder(folder, emotion_name, emotion.scale_intervals)
        if seqs:
            all_data[emotion_name] = seqs
            print(f"  -> {len(seqs)} melodies loaded")

    with open(output_file, 'wb') as f:
        pickle.dump(all_data, f)

    print(f"\nSaved training data to {output_file}")