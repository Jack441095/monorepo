# Native sample-embedding WAV/AIFF decode and 32 kHz resampler, 17 Oct 2026

Audio loading and resampling in
[sample_embeddings.py](../../apps/backend/src/kenn/core/sample_embeddings.py)
moved from `librosa.load(path, sr=32000, mono=True, duration=5.0)` and
`np.pad` to the C++ extension: `decode_pcm` and `resample_mono_window` in
[kenn_dsp_native.cpp](../../tooling/native/dsp_core/kenn_dsp_native.cpp),
wrapped by `native_fft.resample_mono_window` in
[native_fft.py](../../apps/backend/src/kenn/core/native_fft.py).
Both `sample_embeddings.py` and `sample_library.py` now decode `.wav`, `.aif`,
and `.aiff` files in C++ via `native_fft.decode_pcm(payload, allow_aiff=is_aiff)`,
removing `import librosa` from KENN completely.

## What it computes

- **Bounded WAV and AIFF/AIFC decode:** reads at most the first 32 MiB of a
  `.wav`, `.aif`, or `.aiff` file (`_MAX_WAV_READ_BYTES`, covering >5.0 s of
  stereo 32-bit float up to 768 kHz) and decodes mono/stereo 16/24/32-bit PCM
  or 32-bit float (`FORM` `AIFF` and uncompressed `AIFC` `NONE`/`twos`/`sowt`/`fl32`/`FL32`
  with 80-bit IEEE 754 extended sample rates) via `native_fft.decode_pcm`. Across
  all 4 real `.aif` files in `Audio-Assets/SLO-Testing/sample_pack_testing`,
  C++ `decode_pcm(allow_aiff=True)` matches `libsndfile` (`soundfile`) with
  `0.000e+00` max abs float32 difference.
- **Rate and finiteness guards:** refuses sample rates outside `8000..768000 Hz`
  and any `NaN`/`Inf` sample with an honest abstention message rather than
  allocating multi-gigabyte filter buffers or passing non-finite tensors to
  ONNX Runtime.
- **Mono fold and 5.0 s window:** crops the input to at most `round(160000 * sr / 32000)`
  frames (5.0 s), averages channels in `double`, resamples to `32000 Hz`, and
  returns a contiguous `160,000`-sample `float32` 1D buffer (zero-padded when
  shorter than 5.0 s).
- **Kaiser-windowed polyphase FIR:** for all rational pairs with
  `max(up, down) <= 2048` (`up = 32000 / gcd(32000, sr)`, `down = sr / gcd(32000, sr)`,
  which covers every standard rate from 8 kHz to 768 kHz), builds the exact
  `scipy.signal.resample_poly` Kaiser (`beta = 5.0`, `half_len = 10 * max_rate`)
  filter transposed into `up` contiguous phase rows. Coprime rates with
  `max(up, down) > 2048` (e.g. `44101 Hz`) evaluate the continuous-time
  Kaiser-windowed sinc directly so filter memory stays bounded.

## Parity and latency on 25 real sample-pack WAVs

Measured on 25 evenly spaced WAV samples across
`Audio-Assets/SLO-Testing/sample_pack_testing` (`MAX_CANDIDATES = 25`), using
the PANNs Cnn10 512D ONNX model on one arm64 Mac:

| Quantity | Value | Notes |
| --- | --- | --- |
| Waveform diff vs `scipy.signal.resample_poly` | `2.328e-10` max abs | `float32` rounding only across all 25 files |
| PANNs 512D embedding cosine similarity vs `librosa.load` | `0.999951` min, `0.999993` mean, `1.000000` median | Across all 25 512D vectors |
| Top-1 nearest-neighbour agreement (`25 x 24` pairs) | `25 / 25` (`100%`) | Every query selects the exact same nearest sample |
| Decode + 32 kHz resample time (25 files) | `792.2 ms` → `61.9 ms` | `12.8x` speedup for the audio load/resample stage |
| End-to-end `extract_embedding` time (25 files, incl. ONNX Cnn10) | `2.144 s` → `1.153 s` | `1.86x` end-to-end speedup |

## Portable scalar build

Built with `-DKENN_USE_ACCELERATE=OFF` and with Accelerate enabled: all 12
tests in `test_sample_embeddings.py` pass on both builds (7 pass and 5
model-dependent tests skip cleanly when `KENN_PANNS_MODEL_DIR` is unset), and
the full KENN suite is 6412 passed, 48 skipped, 3 pre-existing failures
(`test_mixing_doctor.py` x2, `test_fixed_session_grounded_benchmark_qualifies`).

