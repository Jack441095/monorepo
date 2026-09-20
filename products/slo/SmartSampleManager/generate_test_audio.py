import wave
import struct
import math
import os

def main():
    sample_rate = 44100.0
    duration = 1.0 # 1 second
    num_samples = int(sample_rate * duration)

    output_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(output_dir, "test_kick.wav")

    print(f"Generating test WAV file at {output_path}...")
    with wave.open(output_path, "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2) # 16-bit
        f.setframerate(int(sample_rate))
        for i in range(num_samples):
            # 100 Hz sine wave
            val = int(32767.0 * math.sin(2.0 * math.pi * 100.0 * i / sample_rate))
            data = struct.pack('<h', val)
            f.writeframesraw(data)
    print("Generation complete!")

if __name__ == "__main__":
    main()
