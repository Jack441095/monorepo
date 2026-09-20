# data/sample_packs.py
# Project module `sample_packs` (data).

SAMPLE_PACKS = {
    "default": {
        "bass": {"file_path": "samples/default/bass.wav", "root_midi": 29},
        "chords": {"file_path": "samples/default/chords.wav", "root_midi": 60},
        "melody": {"file_path": "samples/default/melody.wav", "root_midi": 60},
        "arp": {"file_path": "samples/default/arp.wav", "root_midi": 60},
        "drone": {"file_path": "samples/default/drone.wav", "root_midi": 60},
        "counter_melody": {"file_path": "samples/default/melody.wav", "root_midi": 60},
    },
    "shimmer": {
        "bass": {"root_midi": 29},
        "chords": {"root_midi": 60},
        "melody": {"root_midi": 60},
        "arp": {"root_midi": 60},
        "drone": {"root_midi": 60},
        "counter_melody": {"root_midi": 60},
    },
    "percussive": {
        "bass": {"root_midi": 29},
        "chords": {"root_midi": 60},
        "melody": {"root_midi": 60},
        "arp": {"root_midi": 60},
        "drone": {"root_midi": 60},
        "counter_melody": {"root_midi": 60},
    },
    "dark": {
        "bass": {"file_path": "samples/dark/bass.wav", "root_midi": 29},
        "chords": {"file_path": "samples/dark/chords.wav", "root_midi": 60},
        "melody": {"file_path": "samples/dark/melody.wav", "root_midi": 60},
        "arp": {"root_midi": 60},
        "drone": {"file_path": "samples/dark/drone.wav", "root_midi": 60},
        "counter_melody": {"file_path": "samples/dark/melody.wav", "root_midi": 60},
    },
    "eurphoric": {
        "bass": {"file_path": "samples/eurphoric/bass.wav", "root_midi": 29},
        "chords": {"file_path": "samples/eurphoric/chords.wav", "root_midi": 60},
        "melody": {"file_path": "samples/eurphoric/melody.wav", "root_midi": 60},
        "arp": {"root_midi": 60},
        "drone": {"file_path": "samples/eurphoric/drone.wav", "root_midi": 60},
        "counter_melody": {"file_path": "samples/eurphoric/melody.wav", "root_midi": 60},
    },
    # Alias: same assets as ``default`` (no separate ``samples/ambient/`` tree required).
    "ambient": {
        "bass": {"file_path": "samples/default/bass.wav", "root_midi": 29},
        "chords": {"file_path": "samples/default/chords.wav", "root_midi": 60},
        "melody": {"file_path": "samples/default/melody.wav", "root_midi": 60},
        "arp": {"file_path": "samples/default/arp.wav", "root_midi": 60},
        "drone": {"file_path": "samples/default/drone.wav", "root_midi": 60},
        "counter_melody": {"file_path": "samples/default/melody.wav", "root_midi": 60},
    },
}
