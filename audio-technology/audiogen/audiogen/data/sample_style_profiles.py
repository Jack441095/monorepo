# data/sample_style_profiles.py
# Sample-pack / arrangement style presets (dict-based).

from copy import deepcopy


STYLE_PROFILES = {
    "default": {},
    "ambient": {
        "sample_pack": "ambient",
        "composition": {
            "default_tempo": 56.0,
            "arranged_song_mode": "ambient",
            "melody_amount_scale": 0.62,
        },
        "audio": {
            "reverb_wet": 0.50,
            "reverb_rt60": 12.0,
        },
    },
    "dark": {
        "sample_pack": "dark",
        "composition": {
            "default_tempo": 52.0,
            "arranged_song_mode": "ambient",
            "melody_amount_scale": 0.58,
        },
        "audio": {
            "reverb_wet": 0.32,
            "reverb_rt60": 8.0,
        },
    },
}


def get_style_profiles():
    return deepcopy(STYLE_PROFILES)
