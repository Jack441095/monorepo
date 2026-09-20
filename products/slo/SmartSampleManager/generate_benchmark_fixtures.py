"""
Generates N short synthetic mono WAV files (varied frequency/duration so
they're not byte-identical, avoiding an artificial 100%-duplicate-rate
skew) into a target directory, for PERFORMANCE_BASELINE.md's benchmark.
Not part of the shipped product -- dev tooling only, mirrors the existing
generate_test_audio.py pattern.

    python3 generate_benchmark_fixtures.py <output_dir> <count>
"""
import wave
import struct
import math
import os
import sys


def generate_one(path: str, freq: float, duration: float, sample_rate: int = 44100) -> None:
    num_samples = int(sample_rate * duration)
    with wave.open(path, "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        frames = bytearray()
        for i in range(num_samples):
            val = int(32000.0 * math.sin(2.0 * math.pi * freq * i / sample_rate))
            frames += struct.pack('<h', val)
        f.writeframesraw(bytes(frames))


def main() -> None:
    output_dir = sys.argv[1]
    count = int(sys.argv[2])
    os.makedirs(output_dir, exist_ok=True)
    for i in range(count):
        freq = 80.0 + (i % 400) * 3.0  # vary 80Hz-1280Hz so files differ acoustically
        duration = 0.5 + (i % 5) * 0.3  # vary 0.5s-1.7s
        path = os.path.join(output_dir, f"bench_{i:06d}.wav")
        generate_one(path, freq, duration)
        if i % 100 == 0:
            print(f"  generated {i}/{count}")
    print(f"Done: {count} files in {output_dir}")


if __name__ == "__main__":
    main()
