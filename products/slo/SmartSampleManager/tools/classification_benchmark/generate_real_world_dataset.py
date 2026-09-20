import wave
import struct
import math
import os
import random
import json

# Reuse the basic generator functions but add high acoustic diversity parameters
def generate_kick_diverse(path, idx, sample_rate=32000):
    # Acoustic kick (higher pitch, fast decay), electronic (subby), distorted (clipped), long/short
    decay = 0.05 + 0.3 * (idx % 5) / 4.0
    freq_start = 120.0 + 80.0 * (idx % 3) / 2.0
    freq_end = 40.0 + 20.0 * (idx % 2)
    distort = (idx % 4 == 0) # apply clipping
    
    num_samples = int(sample_rate * 0.4)
    frames = bytearray()
    for i in range(num_samples):
        t = i / sample_rate
        f = freq_end + (freq_start - freq_end) * math.exp(-t / (decay * 0.4))
        val = math.sin(2.0 * math.pi * f * t) * math.exp(-t / decay)
        if distort:
            val = val * 2.0
            val = max(-1.0, min(1.0, val))
        val_int = int(32000.0 * val)
        frames += struct.pack('<h', val_int)
        
    with wave.open(path, "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        f.writeframesraw(bytes(frames))

def generate_snare_diverse(path, idx, sample_rate=32000):
    # Tonal snare, noisy snare, rimshot, acoustic snare
    decay = 0.1 + 0.25 * (idx % 4) / 3.0
    noise_mix = 0.3 + 0.7 * (idx % 3) / 2.0
    freq = 150.0 + 100.0 * (idx % 2)
    
    num_samples = int(sample_rate * 0.5)
    frames = bytearray()
    for i in range(num_samples):
        t = i / sample_rate
        sine_val = math.sin(2.0 * math.pi * freq * t) * math.exp(-t / 0.05)
        noise_val = (random.random() * 2.0 - 1.0) * math.exp(-t / decay)
        val = sine_val * (1 - noise_mix) + noise_val * noise_mix
        val_int = int(24000.0 * max(-1.0, min(1.0, val)))
        frames += struct.pack('<h', val_int)
        
    with wave.open(path, "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        f.writeframesraw(bytes(frames))

def generate_hihat_diverse(path, idx, sample_rate=32000):
    # Open hats (longer decay), closed hats (short), metallic (filtered/modulated)
    decay = 0.02 + 0.15 * (idx % 5) / 4.0
    metallic = (idx % 3 == 0)
    
    num_samples = int(sample_rate * 0.35)
    frames = bytearray()
    for i in range(num_samples):
        t = i / sample_rate
        noise = random.random() * 2.0 - 1.0
        if metallic:
            # Ring modulator simulation
            noise *= math.sin(2.0 * math.pi * 8000.0 * t)
        if i % 2 == 0:
            noise = -noise
        val = noise * math.exp(-t / decay)
        val_int = int(28000.0 * max(-1.0, min(1.0, val)))
        frames += struct.pack('<h', val_int)
        
    with wave.open(path, "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        f.writeframesraw(bytes(frames))

def generate_clap_diverse(path, idx, sample_rate=32000):
    decay = 0.1 + 0.2 * (idx % 3) / 2.0
    num_peaks = 2 + (idx % 4)
    num_samples = int(sample_rate * 0.45)
    frames = bytearray()
    for i in range(num_samples):
        t = i / sample_rate
        # Multiple transient spikes
        imp = 0.0
        for p in range(num_peaks):
            p_time = p * 0.012
            if p_time <= t < p_time + 0.01:
                imp += math.exp(-(t - p_time) / 0.002)
        noise = (random.random() * 2.0 - 1.0) * (imp * 0.6 + math.exp(-t / decay))
        val_int = int(24000.0 * max(-1.0, min(1.0, noise)))
        frames += struct.pack('<h', val_int)
        
    with wave.open(path, "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        f.writeframesraw(bytes(frames))

def generate_perc_diverse(path, idx, sample_rate=32000):
    # Claves, blocks, shaker, bongos
    freq = 300.0 + 800.0 * (idx % 6) / 5.0
    decay = 0.03 + 0.12 * (idx % 3) / 2.0
    is_noise = (idx % 4 == 0) # shaker-like
    
    num_samples = int(sample_rate * 0.3)
    frames = bytearray()
    for i in range(num_samples):
        t = i / sample_rate
        if is_noise:
            sig = random.random() * 2.0 - 1.0
        else:
            sig = math.sin(2.0 * math.pi * freq * t)
        val = sig * math.exp(-t / decay)
        val_int = int(28000.0 * val)
        frames += struct.pack('<h', val_int)
        
    with wave.open(path, "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        f.writeframesraw(bytes(frames))

def generate_bass_one_shot_diverse(path, idx, sample_rate=32000):
    # Sub, Reese (detuned), FM, pluck, sustained
    decay = 0.5 + 1.2 * (idx % 4) / 3.0
    freq = 55.0 + 55.0 * (idx % 5) / 4.0 # G1 to A2
    detune = (idx % 3 == 0)
    
    num_samples = int(sample_rate * 1.5)
    frames = bytearray()
    for i in range(num_samples):
        t = i / sample_rate
        if detune:
            sig = math.sin(2.0 * math.pi * freq * t) + 0.3 * math.sin(2.0 * math.pi * (freq + 2.0) * t)
        else:
            sig = math.sin(2.0 * math.pi * freq * t)
        val = sig * math.exp(-t / decay)
        val_int = int(24000.0 * max(-1.0, min(1.0, val)))
        frames += struct.pack('<h', val_int)
        
    with wave.open(path, "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        f.writeframesraw(bytes(frames))

def generate_bass_loop_diverse(path, idx, tempo=120, sample_rate=32000):
    freq = 60.0 + (idx % 4) * 10
    num_samples = int(sample_rate * 4.0)
    beat_samples = int(sample_rate * (60.0 / tempo))
    frames = bytearray()
    for i in range(num_samples):
        t = i / sample_rate
        beat_t = (i % beat_samples) / sample_rate
        amp = math.exp(-beat_t / 0.25)
        # Add slide / modulation
        freq_mod = freq + 15.0 * math.sin(2.0 * math.pi * t)
        val = int(28000.0 * amp * math.sin(2.0 * math.pi * freq_mod * t))
        frames += struct.pack('<h', val)
        
    with wave.open(path, "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        f.writeframesraw(bytes(frames))

def generate_synth_diverse(path, idx, sample_rate=32000):
    freq = 150.0 + 350.0 * (idx % 6) / 5.0
    decay = 0.2 + 0.8 * (idx % 3) / 2.0
    is_square = (idx % 2 == 0)
    
    num_samples = int(sample_rate * 1.0)
    frames = bytearray()
    for i in range(num_samples):
        t = i / sample_rate
        phase = (freq * t) % 1.0
        sig = 1.0 if phase < 0.5 else -1.0
        if not is_square:
            sig = 2.0 * phase - 1.0 # saw
        val = sig * math.exp(-t / decay)
        val_int = int(20000.0 * val)
        frames += struct.pack('<h', val_int)
        
    with wave.open(path, "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        f.writeframesraw(bytes(frames))

def generate_synth_loop_diverse(path, idx, tempo=120, sample_rate=32000):
    num_samples = int(sample_rate * 4.0)
    beat_samples = int(sample_rate * (60.0 / tempo) / 2) # eighth notes
    notes = [220.0, 261.63, 293.66, 329.63, 392.00, 329.63, 293.66, 261.63]
    frames = bytearray()
    for i in range(num_samples):
        t = i / sample_rate
        note_idx = (i // beat_samples) % len(notes)
        freq = notes[note_idx] + (idx % 3) * 30.0
        phase = (freq * t) % 1.0
        saw = 2.0 * phase - 1.0
        beat_t = (i % beat_samples) / sample_rate
        amp = math.exp(-beat_t / 0.12)
        val_int = int(22000.0 * amp * saw)
        frames += struct.pack('<h', val_int)
        
    with wave.open(path, "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        f.writeframesraw(bytes(frames))

def generate_vocal_phrase_diverse(path, idx, sample_rate=32000):
    freq = 150.0 + 100.0 * (idx % 3)
    decay = 0.5 + 0.5 * (idx % 3) / 2.0
    num_samples = int(sample_rate * 1.5)
    frames = bytearray()
    for i in range(num_samples):
        t = i / sample_rate
        # Vibrato and formant sweep
        vib = 3.0 * math.sin(2.0 * math.pi * 6.0 * t)
        carrier = math.sin(2.0 * math.pi * (freq + vib) * t)
        modulator = math.sin(2.0 * math.pi * (300.0 + 100.0 * math.sin(2.0 * math.pi * 0.5 * t)) * t)
        val = carrier * modulator * math.exp(-t / decay)
        val_int = int(24000.0 * max(-1.0, min(1.0, val)))
        frames += struct.pack('<h', val_int)
        
    with wave.open(path, "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        f.writeframesraw(bytes(frames))

def generate_vocal_loop_diverse(path, idx, tempo=120, sample_rate=32000):
    num_samples = int(sample_rate * 4.0)
    beat_samples = int(sample_rate * (60.0 / tempo))
    frames = bytearray()
    for i in range(num_samples):
        t = i / sample_rate
        beat_t = (i % beat_samples) / sample_rate
        amp = math.exp(-beat_t / 0.3)
        carrier = math.sin(2.0 * math.pi * (180.0 + idx % 4 * 20) * t)
        modulator = math.sin(2.0 * math.pi * 450.0 * t)
        val_int = int(20000.0 * amp * carrier * modulator)
        frames += struct.pack('<h', val_int)
        
    with wave.open(path, "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        f.writeframesraw(bytes(frames))

def generate_impact_diverse(path, idx, sample_rate=32000):
    decay = 1.0 + 1.5 * (idx % 3) / 2.0
    num_samples = int(sample_rate * 2.5)
    frames = bytearray()
    for i in range(num_samples):
        t = i / sample_rate
        noise = (random.random() * 2.0 - 1.0) * math.exp(-t / 0.08)
        sub = math.sin(2.0 * math.pi * (50.0 + idx % 3 * 10) * t) * math.exp(-t / decay)
        val_int = int(18000.0 * max(-1.0, min(1.0, noise + sub)))
        frames += struct.pack('<h', val_int)
        
    with wave.open(path, "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        f.writeframesraw(bytes(frames))

def generate_riser_diverse(path, idx, sample_rate=32000):
    duration = 2.0 + 2.0 * (idx % 3) / 2.0
    num_samples = int(sample_rate * duration)
    frames = bytearray()
    for i in range(num_samples):
        t = i / sample_rate
        freq = 80.0 + (800.0 + idx % 3 * 200.0) * (t / duration)
        # FM modulation
        mod = 30.0 * math.sin(2.0 * math.pi * 20.0 * t)
        val = int(26000.0 * (t / duration) * math.sin(2.0 * math.pi * (freq + mod) * t))
        frames += struct.pack('<h', val)
        
    with wave.open(path, "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        f.writeframesraw(bytes(frames))

def generate_foley_diverse(path, idx, sample_rate=32000):
    decay = 0.08 + 0.12 * (idx % 4) / 3.0
    num_samples = int(sample_rate * 0.45)
    frames = bytearray()
    for i in range(num_samples):
        t = i / sample_rate
        # Footstep/crunch noise simulation
        noise = (random.random() * 2.0 - 1.0) * math.exp(-t / decay)
        # High-pass filter simulation
        if i % 2 == 0:
            noise = -noise
        val_int = int(16000.0 * noise)
        frames += struct.pack('<h', val_int)
        
    with wave.open(path, "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        f.writeframesraw(bytes(frames))

def generate_fx_diverse(path, idx, sample_rate=32000):
    num_samples = int(sample_rate * 1.5)
    frames = bytearray()
    for i in range(num_samples):
        t = i / sample_rate
        mod = math.sin(2.0 * math.pi * (10.0 + idx % 3 * 5.0) * t) * 300.0
        carrier = math.sin(2.0 * math.pi * (400.0 + mod) * t)
        val_int = int(26000.0 * math.exp(-t / 0.6) * carrier)
        frames += struct.pack('<h', val_int)
        
    with wave.open(path, "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        f.writeframesraw(bytes(frames))

def generate_atmosphere_diverse(path, idx, sample_rate=32000):
    num_samples = int(sample_rate * 4.0)
    frames = bytearray()
    last_val = 0.0
    for i in range(num_samples):
        t = i / sample_rate
        r = random.random() * 2.0 - 1.0
        # Pink-ish noise filter
        last_val = 0.96 * last_val + 0.04 * r
        drone = math.sin(2.0 * math.pi * (80.0 + idx % 3 * 10) * t) * 0.25
        val_int = int(24000.0 * max(-1.0, min(1.0, last_val + drone)))
        frames += struct.pack('<h', val_int)
        
    with wave.open(path, "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        f.writeframesraw(bytes(frames))

def generate_music_loop_diverse(path, idx, tempo=120, sample_rate=32000):
    num_samples = int(sample_rate * 4.0)
    beat_samples = int(sample_rate * (60.0 / tempo))
    notes = [130.81, 164.81, 196.00, 261.63] # chords
    frames = bytearray()
    for i in range(num_samples):
        t = i / sample_rate
        beat_idx = (i // beat_samples) % 4
        # Multi-voice tone
        tone = 0.4 * math.sin(2.0 * math.pi * notes[beat_idx] * t) + 0.25 * math.sin(2.0 * math.pi * notes[beat_idx] * 2.0 * t)
        val_int = int(26000.0 * tone * math.exp(-(i % beat_samples) / sample_rate / 0.5))
        frames += struct.pack('<h', val_int)
        
    with wave.open(path, "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        f.writeframesraw(bytes(frames))

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    fixtures_dir = os.path.join(base_dir, "fixtures")
    real_world_dir = os.path.join(fixtures_dir, "real_world")
    os.makedirs(real_world_dir, exist_ok=True)
    
    # 17 classes
    generators = {
        "Kick": (generate_kick_diverse, "Drums", "Kick", "One-Shot", "atonal", "Unknown", 120),
        "Snare": (generate_snare_diverse, "Drums", "Snare", "One-Shot", "atonal", "Unknown", 120),
        "Hi-Hat": (generate_hihat_diverse, "Drums", "Hi-Hat", "One-Shot", "atonal", "Unknown", 120),
        "Clap": (generate_clap_diverse, "Drums", "Clap", "One-Shot", "atonal", "Unknown", 120),
        "Percussion": (generate_perc_diverse, "Drums", "Percussion", "One-Shot", "atonal", "Unknown", 120),
        "Bass One-Shot": (generate_bass_one_shot_diverse, "Bass", "Bass One-Shot", "One-Shot", "tonal", "C Major", 120),
        "Bass Loop": (generate_bass_loop_diverse, "Bass", "Bass Loop", "Loop", "tonal", "C Major", 120),
        "Synth": (generate_synth_diverse, "Instruments", "Synth", "One-Shot", "tonal", "C Major", 120),
        "Synth Loop": (generate_synth_loop_diverse, "Instruments", "Synth Loop", "Loop", "tonal", "C Major", 120),
        "Vocal Phrase": (generate_vocal_phrase_diverse, "Vocals", "Vocal Phrase", "One-Shot", "tonal", "A Major", 120),
        "Vocal Loop": (generate_vocal_loop_diverse, "Vocals", "Vocal Loop", "Loop", "tonal", "A Major", 120),
        "Impact": (generate_impact_diverse, "FX", "Impact", "One-Shot", "atonal", "Unknown", 120),
        "Riser": (generate_riser_diverse, "FX", "Riser", "One-Shot", "atonal", "Unknown", 120),
        "Foley": (generate_foley_diverse, "FX", "Foley", "One-Shot", "atonal", "Unknown", 120),
        "FX": (generate_fx_diverse, "FX", "FX", "One-Shot", "atonal", "Unknown", 120),
        "Atmosphere": (generate_atmosphere_diverse, "Ambience", "Atmosphere", "One-Shot", "atonal", "Unknown", 120),
        "Music Loop": (generate_music_loop_diverse, "Instruments", "Music Loop", "Loop", "tonal", "C Major", 120)
    }
    
    # Generate 50 files per class = 850 files
    N_PER_CLASS = 50
    manifest = []
    
    # 4 Packs, 2 Vendors
    # Pack A (Vendor X), Pack B (Vendor X), Pack C (Vendor Y), Pack D (Vendor Y)
    packs = ["pack_A", "pack_B", "pack_C", "pack_D"]
    vendors = {
        "pack_A": "vendor_X",
        "pack_B": "vendor_X",
        "pack_C": "vendor_Y",
        "pack_D": "vendor_Y"
    }
    
    print(f"Generating {len(generators) * N_PER_CLASS} diverse real-world mock fixtures...")
    
    sample_id = 1
    for subcat, info in generators.items():
        gen_func, category, subcat_name, loop_status, tonal_status, expected_key, expected_bpm = info
        for idx in range(N_PER_CLASS):
            pack = packs[idx % len(packs)]
            vendor = vendors[pack]
            pack_dir = os.path.join(real_world_dir, pack)
            os.makedirs(pack_dir, exist_ok=True)
            
            # Format filename to contain category cues
            # Let's make some filenames ambiguous or standard
            filename = f"{subcat.lower().replace(' ', '_')}_{idx:02d}.wav"
            filepath = os.path.join(pack_dir, filename)
            
            # Label confidence: 80% HIGH, 15% MEDIUM, 5% AMBIGUOUS
            r = random.random()
            if r < 0.8:
                confidence = "HIGH"
            elif r < 0.95:
                confidence = "MEDIUM"
            else:
                confidence = "AMBIGUOUS"
                
            # Key variation
            key = expected_key
            if subcat in ["Bass One-Shot", "Synth"]:
                keys = ["C Major", "D Major", "E Major", "G Major", "A Major"]
                key = keys[idx % len(keys)]
                freqs = [65.41, 73.42, 82.41, 98.00, 110.00] if subcat == "Bass One-Shot" else [261.63, 293.66, 329.63, 392.00, 440.00]
                gen_func(filepath, idx=idx) # custom generation logic will receive idx
            elif subcat in ["Bass Loop", "Synth Loop", "Vocal Loop", "Music Loop"]:
                bpm = 90 + (idx % 5) * 15 # 90, 105, 120, 135, 150
                gen_func(filepath, idx=idx, tempo=bpm)
                expected_bpm = bpm
            else:
                gen_func(filepath, idx=idx)
                
            # Relative path from tools/classification_benchmark
            rel_path = os.path.relpath(filepath, base_dir)
            
            manifest.append({
                "sample_id": sample_id,
                "relative_path": rel_path,
                "filename": filename,
                "expected_category": category,
                "expected_subcategory": subcat_name,
                "expected_loop_status": loop_status,
                "expected_tonal_status": tonal_status,
                "expected_key": key,
                "expected_bpm": expected_bpm,
                "source_pack": pack,
                "source_vendor": vendor,
                "label_confidence": confidence,
                "notes": f"Real-world mock representation of {subcat}"
            })
            sample_id += 1

    # 2. GENERATE OUT-OF-DISTRIBUTION (OOD) SAMPLES
    ood_dir = os.path.join(fixtures_dir, "real_world_ood")
    os.makedirs(ood_dir, exist_ok=True)
    print("Generating 20 OOD (Out-of-Distribution) samples...")
    for idx in range(20):
        filename = f"ood_sample_{idx:02d}.wav"
        filepath = os.path.join(ood_dir, filename)
        rel_path = os.path.relpath(filepath, base_dir)
        
        # Synthesize pure continuous sine tone or white noise (not in standard taxonomy)
        num_samples = 32000 * 3 # 3 seconds
        frames = bytearray()
        if idx % 2 == 0:
            # Continuous detuned sine waves
            for i in range(num_samples):
                t = i / 32000
                sig = 0.5 * math.sin(2.0 * math.pi * 440.0 * t) + 0.3 * math.sin(2.0 * math.pi * 442.0 * t)
                frames += struct.pack('<h', int(24000.0 * sig))
        else:
            # Continuous flat noise (like hum/static)
            for i in range(num_samples):
                sig = (random.random() * 2.0 - 1.0) * 0.15
                frames += struct.pack('<h', int(32000.0 * sig))
                
        with wave.open(filepath, "w") as f:
            f.setnchannels(1)
            f.setsampwidth(2)
            f.setframerate(32000)
            f.writeframesraw(bytes(frames))
            
        manifest.append({
            "sample_id": sample_id,
            "relative_path": rel_path,
            "filename": filename,
            "expected_category": "OOD",
            "expected_subcategory": "OOD",
            "expected_loop_status": "One-Shot",
            "expected_tonal_status": "atonal",
            "expected_key": "Unknown",
            "expected_bpm": 120,
            "source_pack": "ood_pack",
            "source_vendor": "ood_vendor",
            "label_confidence": "HIGH",
            "notes": "Out-of-Distribution sample"
        })
        sample_id += 1
            
    manifest_path = os.path.join(base_dir, "real_world_manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=4)
        
    print(f"Real-world Mock Set generation complete! Manifest saved to {manifest_path}")

if __name__ == "__main__":
    main()
