import sys
import random
sys.path.append("/Volumes/Jack_Gandy_1TB_SSD/Audio_Engineering_Company/Audio_Too/studio/audiogen/audiogen")

from audiogen_core.config import CONFIG
from audiogen_core.song_upgrade_profile import apply_legacy_composition_profile
from composition.engine import CompositionGenerator
from data.music_data import EMOTIONS
from tests.audiogen.test_section_generation_snapshots import _fingerprint_section_events, _EXPECTED_ADMIRATION_999001

CONFIG.set_performance_mode("balanced")
CONFIG.conversation_presets["__test_empty_conversation__"] = {}
CONFIG.set_conversation_preset("__test_empty_conversation__")
apply_legacy_composition_profile(CONFIG)
CONFIG.composition.section_k_samples = 1
random.seed(13371337)

gen = CompositionGenerator(enable_perf_monitoring=False)
gen.reseed(999001)
evs = gen.generate_section(
    EMOTIONS[0],
    root_note=60,
    bars=4,
    temperature=0.5,
    target_notes_per_bar=4.0,
    melody_style="auto",
    humanization_scale=0.0,
    section_index=0,
)
actual = _fingerprint_section_events(evs)
expected = _EXPECTED_ADMIRATION_999001

print("--- ACTUAL ---")
for i, x in enumerate(actual):
    print(f"{i}: {x}")

print("--- EXPECTED ---")
for i, x in enumerate(expected):
    print(f"{i}: {x}")

print("--- DIFFERENCES ---")
for i in range(max(len(actual), len(expected))):
    a = actual[i] if i < len(actual) else None
    e = expected[i] if i < len(expected) else None
    if a != e:
        print(f"Index {i}:")
        print(f"  Actual:   {a}")
        print(f"  Expected: {e}")
