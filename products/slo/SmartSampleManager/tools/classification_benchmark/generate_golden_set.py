import wave
import struct
import math
import os
import random
import json

def generate_kick(path, freq_start=150.0, freq_end=50.0, decay=0.2, sample_rate=32000):
    # Short low frequency sweep (low energy ratio high, zcr low)
    num_samples = int(sample_rate * 0.5)
    frames = bytearray()
    for i in range(num_samples):
        t = i / sample_rate
        # Exponential frequency sweep
        f = freq_end + (freq_start - freq_end) * math.exp(-t / (decay * 0.5))
        phase = 2.0 * math.pi * f * t
        # Exponential amplitude envelope
        amp = math.exp(-t / decay)
        val = int(32000.0 * amp * math.sin(phase))
        frames += struct.pack('<h', val)
    
    with wave.open(path, "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        f.writeframesraw(bytes(frames))

def generate_snare(path, freq=180.0, decay=0.25, sample_rate=32000):
    # Noise mixed with low frequency sine
    num_samples = int(sample_rate * 0.6)
    frames = bytearray()
    for i in range(num_samples):
        t = i / sample_rate
        sine_val = math.sin(2.0 * math.pi * freq * t) * math.exp(-t / 0.08)
        noise_val = (random.random() * 2.0 - 1.0) * math.exp(-t / decay)
        val = int(16000.0 * (sine_val + noise_val))
        val = max(-32768, min(32767, val))
        frames += struct.pack('<h', val)
        
    with wave.open(path, "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        f.writeframesraw(bytes(frames))

def generate_hihat(path, decay=0.06, sample_rate=32000):
    # Short high-frequency noise (high zcr, high energy ratio high)
    num_samples = int(sample_rate * 0.3)
    frames = bytearray()
    for i in range(num_samples):
        t = i / sample_rate
        # Generate simple white noise
        noise_val = random.random() * 2.0 - 1.0
        # High pass filter simulation (alternating signs to shift energy high)
        if i % 2 == 0:
            noise_val = -noise_val
        amp = math.exp(-t / decay)
        val = int(32000.0 * amp * noise_val)
        frames += struct.pack('<h', val)
        
    with wave.open(path, "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        f.writeframesraw(bytes(frames))

def generate_clap(path, decay=0.2, sample_rate=32000):
    # Multiple transients followed by noise decay
    num_samples = int(sample_rate * 0.5)
    frames = bytearray()
    for i in range(num_samples):
        t = i / sample_rate
        # 3 initial impulse peaks
        imp = 0.0
        if 0 <= t < 0.015:
            imp = math.exp(-(t % 0.005) / 0.001)
        noise_val = (random.random() * 2.0 - 1.0) * (imp * 0.8 + math.exp(-t / decay))
        val = int(24000.0 * noise_val)
        val = max(-32768, min(32767, val))
        frames += struct.pack('<h', val)
        
    with wave.open(path, "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        f.writeframesraw(bytes(frames))

def generate_perc(path, freq=700.0, decay=0.08, sample_rate=32000):
    # Tonal hit in mid frequency
    num_samples = int(sample_rate * 0.4)
    frames = bytearray()
    for i in range(num_samples):
        t = i / sample_rate
        val = int(32000.0 * math.exp(-t / decay) * math.sin(2.0 * math.pi * freq * t))
        frames += struct.pack('<h', val)
        
    with wave.open(path, "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        f.writeframesraw(bytes(frames))

def generate_bass_one_shot(path, freq=80.0, decay=1.0, sample_rate=32000):
    # Steady low frequency tone (duration > 1s, decay > 0.6)
    num_samples = int(sample_rate * 1.5)
    frames = bytearray()
    for i in range(num_samples):
        t = i / sample_rate
        val = int(32000.0 * math.exp(-t / decay) * math.sin(2.0 * math.pi * freq * t))
        frames += struct.pack('<h', val)
        
    with wave.open(path, "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        f.writeframesraw(bytes(frames))

def generate_bass_loop(path, tempo=120, num_samples=32000 * 4, sample_rate=32000):
    # Rhythmic low frequency pattern
    frames = bytearray()
    beat_samples = int(sample_rate * (60.0 / tempo))
    for i in range(num_samples):
        t = i / sample_rate
        beat_idx = (i // beat_samples) % 4
        # Change frequency per beat to make it musical
        freq = 80.0 if beat_idx % 2 == 0 else 100.0
        # Rhythmic amplitude envelope
        beat_t = (i % beat_samples) / sample_rate
        amp = math.exp(-beat_t / 0.3)
        val = int(30000.0 * amp * math.sin(2.0 * math.pi * freq * t))
        frames += struct.pack('<h', val)
        
    with wave.open(path, "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        f.writeframesraw(bytes(frames))

def generate_synth_one_shot(path, freq=300.0, decay=0.5, sample_rate=32000):
    # Sawtooth/square wave tonal pluck
    num_samples = int(sample_rate * 1.0)
    frames = bytearray()
    for i in range(num_samples):
        t = i / sample_rate
        # Simple sawtooth approximation: mod phase to [-1, 1]
        phase = (freq * t) % 1.0
        saw = 2.0 * phase - 1.0
        val = int(24000.0 * math.exp(-t / decay) * saw)
        frames += struct.pack('<h', val)
        
    with wave.open(path, "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        f.writeframesraw(bytes(frames))

def generate_synth_loop(path, tempo=120, num_samples=32000 * 4, sample_rate=32000):
    # Repeating melodic synth loop
    frames = bytearray()
    beat_samples = int(sample_rate * (60.0 / tempo) / 2) # eighth notes
    notes = [261.63, 293.66, 329.63, 392.00, 440.00, 392.00, 329.63, 293.66]
    for i in range(num_samples):
        t = i / sample_rate
        note_idx = (i // beat_samples) % len(notes)
        freq = notes[note_idx]
        phase = (freq * t) % 1.0
        saw = 2.0 * phase - 1.0
        beat_t = (i % beat_samples) / sample_rate
        amp = math.exp(-beat_t / 0.15)
        val = int(20000.0 * amp * saw)
        frames += struct.pack('<h', val)
        
    with wave.open(path, "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        f.writeframesraw(bytes(frames))

def generate_vocal_phrase(path, freq=220.0, decay=0.8, sample_rate=32000):
    # Tonal formant sweep
    num_samples = int(sample_rate * 1.5)
    frames = bytearray()
    for i in range(num_samples):
        t = i / sample_rate
        # Formant simulation by modulating two frequencies
        carrier = math.sin(2.0 * math.pi * freq * t)
        modulator = math.sin(2.0 * math.pi * 500.0 * t + 2.0 * math.sin(2.0 * math.pi * 5.0 * t))
        val = int(24000.0 * math.exp(-t / decay) * carrier * modulator)
        frames += struct.pack('<h', val)
        
    with wave.open(path, "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        f.writeframesraw(bytes(frames))

def generate_vocal_loop(path, tempo=120, num_samples=32000 * 4, sample_rate=32000):
    # Repeating vocal sweeps
    frames = bytearray()
    beat_samples = int(sample_rate * (60.0 / tempo))
    for i in range(num_samples):
        t = i / sample_rate
        beat_idx = (i // beat_samples) % 4
        freq = 150.0 + beat_idx * 30.0
        carrier = math.sin(2.0 * math.pi * freq * t)
        modulator = math.sin(2.0 * math.pi * 400.0 * t)
        beat_t = (i % beat_samples) / sample_rate
        amp = math.exp(-beat_t / 0.4)
        val = int(20000.0 * amp * carrier * modulator)
        frames += struct.pack('<h', val)
        
    with wave.open(path, "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        f.writeframesraw(bytes(frames))

def generate_impact(path, decay=2.0, sample_rate=32000):
    # Loud transient + low frequency tail
    num_samples = int(sample_rate * 3.0)
    frames = bytearray()
    for i in range(num_samples):
        t = i / sample_rate
        noise = (random.random() * 2.0 - 1.0) * math.exp(-t / 0.1)
        sub = math.sin(2.0 * math.pi * 60.0 * t) * math.exp(-t / decay)
        val = int(16000.0 * (noise + sub))
        val = max(-32768, min(32767, val))
        frames += struct.pack('<h', val)
        
    with wave.open(path, "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        f.writeframesraw(bytes(frames))

def generate_riser(path, duration=4.0, sample_rate=32000):
    # Frequency sweep upwards
    num_samples = int(sample_rate * duration)
    frames = bytearray()
    for i in range(num_samples):
        t = i / sample_rate
        # Linear sweep 100Hz to 1200Hz
        freq = 100.0 + (1100.0 * (t / duration))
        val = int(32000.0 * (t / duration) * math.sin(2.0 * math.pi * freq * t))
        frames += struct.pack('<h', val)
        
    with wave.open(path, "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        f.writeframesraw(bytes(frames))

def generate_foley(path, decay=0.15, sample_rate=32000):
    # Footstep-like noise burst
    num_samples = int(sample_rate * 0.4)
    frames = bytearray()
    for i in range(num_samples):
        t = i / sample_rate
        noise = (random.random() * 2.0 - 1.0) * math.exp(-t / decay)
        val = int(12000.0 * noise)
        frames += struct.pack('<h', val)
        
    with wave.open(path, "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        f.writeframesraw(bytes(frames))

def generate_fx(path, sample_rate=32000):
    # Frequency modulation weird sound
    num_samples = int(sample_rate * 2.0)
    frames = bytearray()
    for i in range(num_samples):
        t = i / sample_rate
        mod = math.sin(2.0 * math.pi * 15.0 * t) * 200.0
        carrier = math.sin(2.0 * math.pi * (300.0 + mod) * t)
        val = int(30000.0 * math.exp(-t / 0.8) * carrier)
        frames += struct.pack('<h', val)
        
    with wave.open(path, "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        f.writeframesraw(bytes(frames))

def generate_atmosphere(path, duration=5.0, sample_rate=32000):
    # Continuous noise / drone
    num_samples = int(sample_rate * duration)
    frames = bytearray()
    # Simple low pass filtered noise simulation
    last_val = 0.0
    for i in range(num_samples):
        t = i / sample_rate
        r = random.random() * 2.0 - 1.0
        # Filter: y[n] = 0.95 * y[n-1] + 0.05 * x[n]
        last_val = 0.95 * last_val + 0.05 * r
        # Add a low drone
        drone = math.sin(2.0 * math.pi * 90.0 * t) * 0.3
        val = int(32000.0 * (last_val + drone) * 0.5)
        val = max(-32768, min(32767, val))
        frames += struct.pack('<h', val)
        
    with wave.open(path, "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        f.writeframesraw(bytes(frames))

def generate_music_loop(path, tempo=120, num_samples=32000 * 4, sample_rate=32000):
    # Bass + Synth melody loop
    frames = bytearray()
    beat_samples = int(sample_rate * (60.0 / tempo))
    notes = [261.63, 329.63, 392.00, 523.25]
    for i in range(num_samples):
        t = i / sample_rate
        beat_idx = (i // beat_samples) % 4
        # Bass tone
        bass_f = 65.41 if beat_idx % 2 == 0 else 82.41
        bass_val = math.sin(2.0 * math.pi * bass_f * t) * 0.5
        # Melody tone
        mel_f = notes[beat_idx]
        mel_val = math.sin(2.0 * math.pi * mel_f * t) * 0.3
        
        val = int(30000.0 * (bass_val + mel_val) * math.exp(-(i % beat_samples) / sample_rate / 0.4))
        frames += struct.pack('<h', val)
        
    with wave.open(path, "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        f.writeframesraw(bytes(frames))

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    fixtures_dir = os.path.join(base_dir, "fixtures")
    os.makedirs(fixtures_dir, exist_ok=True)
    
    # Define generating subcategories
    generators = {
        "Kick": (generate_kick, "Drums", "Kick", "One-Shot", "atonal", "Unknown", 120),
        "Snare": (generate_snare, "Drums", "Snare", "One-Shot", "atonal", "Unknown", 120),
        "Hi-Hat": (generate_hihat, "Drums", "Hi-Hat", "One-Shot", "atonal", "Unknown", 120),
        "Clap": (generate_clap, "Drums", "Clap", "One-Shot", "atonal", "Unknown", 120),
        "Percussion": (generate_perc, "Drums", "Percussion", "One-Shot", "atonal", "Unknown", 120),
        "Bass One-Shot": (generate_bass_one_shot, "Bass", "Bass One-Shot", "One-Shot", "tonal", "C Major", 120),
        "Bass Loop": (generate_bass_loop, "Bass", "Bass Loop", "Loop", "tonal", "C Major", 120),
        "Synth": (generate_synth_one_shot, "Instruments", "Synth", "One-Shot", "tonal", "C Major", 120),
        "Synth Loop": (generate_synth_loop, "Instruments", "Synth Loop", "Loop", "tonal", "C Major", 120),
        "Vocal Phrase": (generate_vocal_phrase, "Vocals", "Vocal Phrase", "One-Shot", "tonal", "A Major", 120),
        "Vocal Loop": (generate_vocal_loop, "Vocals", "Vocal Loop", "Loop", "tonal", "A Major", 120),
        "Impact": (generate_impact, "FX", "Impact", "One-Shot", "atonal", "Unknown", 120),
        "Riser": (generate_riser, "FX", "Riser", "One-Shot", "atonal", "Unknown", 120),
        "Foley": (generate_foley, "FX", "Foley", "One-Shot", "atonal", "Unknown", 120),
        "FX": (generate_fx, "FX", "FX", "One-Shot", "atonal", "Unknown", 120),
        "Atmosphere": (generate_atmosphere, "Ambience", "Atmosphere", "One-Shot", "atonal", "Unknown", 120),
        "Music Loop": (generate_music_loop, "Instruments", "Music Loop", "Loop", "tonal", "C Major", 120)
    }
    
    # We will generate 10 files per class
    N_PER_CLASS = 10
    manifest = []
    
    print(f"Generating {len(generators) * N_PER_CLASS} synthetic WAV fixtures...")
    
    sample_id = 1
    for subcat, info in generators.items():
        gen_func, category, subcat_name, loop_status, tonal_status, expected_key, expected_bpm = info
        for idx in range(N_PER_CLASS):
            filename = f"{subcat.lower().replace(' ', '_')}_{idx:02d}.wav"
            filepath = os.path.join(fixtures_dir, filename)
            
            # Generate the wave file
            # Vary frequency slightly so they differ acoustically
            if subcat == "Percussion":
                gen_func(filepath, freq=700.0 + idx * 30.0)
            elif subcat == "Bass One-Shot":
                # Make some keys different
                key = "C Major" if idx % 2 == 0 else "D Major"
                freq = 65.41 if idx % 2 == 0 else 73.42 # C2 or D2
                gen_func(filepath, freq=freq)
                expected_key = key
            elif subcat == "Synth":
                key = "C Major" if idx % 2 == 0 else "E Major"
                freq = 261.63 if idx % 2 == 0 else 329.63
                gen_func(filepath, freq=freq)
                expected_key = key
            elif subcat == "Vocal Phrase":
                # 440 Hz = A4 = A Major
                gen_func(filepath, freq=440.0)
            elif subcat in ["Bass Loop", "Synth Loop", "Vocal Loop", "Music Loop"]:
                # Vary BPM
                bpm = 100 + (idx % 4) * 20 # 100, 120, 140, 160
                gen_func(filepath, tempo=bpm)
                expected_bpm = bpm
            else:
                gen_func(filepath)
                
            manifest.append({
                "sample_id": sample_id,
                "source_fixture": filename,
                "expected_category": category,
                "expected_subcategory": subcat_name,
                "expected_loop_status": loop_status,
                "expected_tonal_status": tonal_status,
                "expected_key": expected_key,
                "expected_bpm": expected_bpm,
                "expected_secondary_tags": [loop_status],
                "label_confidence": "HIGH-CONFIDENCE LABEL",
                "notes": f"Programmatic synthesis of {subcat}"
            })
            sample_id += 1
            
    manifest_path = os.path.join(base_dir, "golden_manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=4)
        
    print(f"Golden Set generation complete! Manifest saved to {manifest_path}")

if __name__ == "__main__":
    main()
