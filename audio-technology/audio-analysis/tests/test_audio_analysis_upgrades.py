import gzip
import math
import xml.etree.ElementTree as ET

from audio_analysis.analysis_core.audio_characterizer import characterize_audio
from audio_analysis.analysis_core.reference_matching import (
    compute_eq_matching_curve,
    generate_eq8_preset_xml,
    export_eq8_preset_adv,
    export_pro_q3_preset,
    generate_pro_q3_preset_xml,
)

def test_audio_characterizer_impulse():
    # Create a synthetic impulse signal
    sample_rate = 44100
    # Silent header, quick rise, and silent tail
    samples = [0.0] * 1000 + [0.1, 0.3, 0.8, 1.0] + [0.0] * 1000
    
    char = characterize_audio(samples, sample_rate)
    
    assert char["peak_amp"] == 1.0
    assert char["attack_time_ms"] > 0.0
    # Rise time from index 1000 (0.1) to index 1003 (1.0) -> 3 samples -> 3/44100 * 1000 = ~0.068 ms
    assert char["attack_time_ms"] < 1.0 
    assert char["crest_factor_db"] > 10.0 # high transient presence

def test_audio_characterizer_sine():
    sample_rate = 44100
    # Generate 4096 samples of a 1000 Hz sine wave
    samples = [math.sin(2.0 * math.pi * 1000.0 * i / sample_rate) for i in range(4096)]
    
    char = characterize_audio(samples, sample_rate)
    
    assert char["peak_amp"] > 0.99
    # Sine wave crest factor is 3 dB (20 * log10(1 / 0.707) = ~3 dB)
    assert 2.5 <= char["crest_factor_db"] <= 3.5
    # Spectral centroid should be close to 1000 Hz
    assert 900.0 <= char["spectral_centroid_hz"] <= 1100.0

def test_audio_characterizer_decay():
    sample_rate = 44100
    # Generate a decaying low frequency sub tone (50 Hz)
    samples = []
    for i in range(8000):
        # decaying envelope
        env = math.exp(-i / 1000.0)
        samples.append(env * math.sin(2.0 * math.pi * 50.0 * i / sample_rate))
        
    char = characterize_audio(samples, sample_rate)
    
    assert char["low_freq_decay_ms"] > 0.0
    # decay to 10% with 1-pole lowpass filter inertia lag
    assert 20.0 <= char["low_freq_decay_ms"] <= 70.0

def test_reference_matching_curve():
    mix_bands = {"sub": 0.1, "bass": 0.2, "low_mids": 0.2, "mids": 0.3, "presence": 0.1, "sibilance": 0.05, "air": 0.05}
    ref_bands = {"sub": 0.1, "bass": 0.3, "low_mids": 0.1, "mids": 0.3, "presence": 0.1, "sibilance": 0.05, "air": 0.05}
    
    gains = compute_eq_matching_curve(mix_bands, ref_bands)
    
    # ref has more bass (0.3 vs 0.2) -> gain should be positive
    assert gains["bass"] > 0.0
    # ref has less low_mids (0.1 vs 0.2) -> gain should be negative
    assert gains["low_mids"] < 0.0
    # identical mids -> gain should be 0.0
    assert gains["mids"] == 0.0
    # Clamping tests
    assert all(-6.0 <= val <= 6.0 for val in gains.values())

def test_eq8_preset_serialization():
    gains = {"sub": 1.5, "bass": -2.0, "low_mids": 0.5, "mids": 0.0, "presence": -1.2, "sibilance": 3.0, "air": -0.8}
    
    xml_str = generate_eq8_preset_xml(gains)
    
    # Verify XML structure
    root = ET.fromstring(xml_str)
    assert root.tag == "Ableton"
    eq8 = root.find("Eq8")
    assert eq8 is not None
    
    bands = eq8.find("Bands")
    assert bands is not None
    
    eq8bands = bands.findall("Eq8Band")
    assert len(eq8bands) == 8
    
    # Verify that Band 3 (Id=2) matches the bass gain (-2.0)
    band3 = [b for b in eq8bands if b.find("Id").attrib["Value"] == "2"][0]
    assert band3.find("Gain").attrib["Value"] == "-2.0"
    
    # Test gzip compression export
    adv_bytes = export_eq8_preset_adv(gains)
    unzipped_xml = gzip.decompress(adv_bytes).decode("utf-8")
    assert "<Eq8>" in unzipped_xml


def test_pro_q3_parametric_preset_serialization():
    solved = [
        {"freq": 80.0, "gain": 2.5, "q": 0.7},
        {"freq": 350.0, "gain": -1.5, "q": 1.2},
        {"freq": 3000.0, "gain": 1.0, "q": 2.0},
        {"freq": 12000.0, "gain": -0.5, "q": 0.5},
    ]
    xml = generate_pro_q3_preset_xml(solved)
    root = ET.fromstring(xml)
    assert root.tag == "FabFilterPreset"
    assert root.attrib["Product"] == "Pro-Q 3"
    assert len(root.find("Bands").findall("Band")) == 4
    assert export_pro_q3_preset(solved).startswith(b"<?xml")
