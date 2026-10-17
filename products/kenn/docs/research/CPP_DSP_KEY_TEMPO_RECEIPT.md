# Native key and tempo, 17 Oct 2026

Key and tempo moved from librosa (`chroma_cqt`, `beat_track`) to the C++
extension: `key_tempo_features` in
[key_tempo_bindings.cpp](../../tooling/native/dsp_core/key_tempo_bindings.cpp).
`sample_library.analyze_sample_audio` is its only caller. The app bundle ships
without librosa, so before this change the shipped app abstained on every
sample BPM/key request.

## What it computes

- Chroma: a 32768-point Hann STFT at 44.1 kHz (scaled with the rate), quarter
  hop, C1 to B7. Each note is the triangular-weighted mean of the FFT bins
  within half a semitone of it, then notes fold into 12 pitch classes. Frames
  60 dB under the loudest are skipped. Each frame is normalised to its peak
  before summing.
- Tempo: a 40-band log spectral-flux onset envelope at 512-sample hops,
  autocorrelated over 8 s windows, then a log-normal prior centred on 120 BPM,
  searched from 30 to 300 BPM. A lag is a candidate only where the
  correlation peaks and at least two pairs of onsets (envelope peaks rising
  4 dB or more) are that far apart. Returns None otherwise (see "Review
  fixes" below).
- Sample BPM/key: the tonic is the best Krumhansl-Kessler major or minor
  profile match. The chroma peak is no longer used. The mode is not reported.

We did not try to reproduce librosa's CQT, so there is no parity number.
Accuracy is scored against labels instead.

## Labelled set

The labels come from sample-pack filenames under
`Audio-Assets/SLO-Testing`, skipping `testing_track_stems`:

- A tempo label is "NNN BPM" between 50 and 220.
- A key label is an explicit mode only, such as "Am", "C# minor" or "Ebmaj".
  Bare notes (one-shots) and chord names are excluded.

There are 1746 BPM labels and 1163 key labels, of which 1110 are minor. With
`random.seed(17)` we drew 250 of each, giving 488 distinct files.

We split that set by SHA-256 of the path:

- tune half: 241 files;
- held-out test half: 247 files.

Only the chroma half-width was tuned, and only on the tune half: 0.25
semitone scored 49/119 exact keys and 0.5 scored 53/119. The scripts and
results are kept in the session scratchpad, not in git. Owner audio is data.

Tempo is right (acc1) when it is within 4% of the label. Octave errors (x2,
x1/2, x3, x1/3, x3/2, x2/3) are counted separately. One arm64 Mac was used
throughout, with nothing else heavy running.

## Results

**Full key and tempo**, with major/minor scored by the same profile match on
both chromas:

| Held-out half | librosa | native |
| --- | --- | --- |
| Exact key | 51/131 | 48/131 |
| Tempo acc1 | 26/129 | 29/129 |
| Tempo wrong | 46 | 42 |
| Time | 22.8 s | 5.1 s |

**The `analyze_sample_audio` contract**: tonic pitch class plus BPM, decoded
with `librosa.load(sr=None, mono=True, duration=60)` for both columns:

| Set | Old: librosa argmax | Native argmax | Native profile tonic |
| --- | --- | --- | --- |
| All 488, pitch class | 106/250 | 100/250 | 142/250 |
| Held-out, pitch class | 57/131 | 55/131 | 71/131 |
| All 488, BPM acc1 | 54/258 | 60/258 | — |
| Time, all 488 | 44.1 s (load + features) | 7.2 s (features only) | — |

The two times are not like for like: the librosa column includes
`librosa.load`, the native one does not. The end-to-end figure below is the
fair comparison. These columns predate the onset gate; old librosa returned
no tempo on 6 files, native then returned one on all of them.

The new `analyze_sample_audio` was then run end to end on all 488 files,
including the native WAV decode. Before the review fixes it gave 142/250
pitch classes, 60/258 BPM within 4% and no abstentions in 10.1 s. After
all three review rounds:

- 142/250 pitch classes right (unchanged);
- 50/258 BPM within 4%, 82 octave errors, 48 wrong, 78 with no BPM;
- held-out half: 71/131 pitch classes, 25/129 BPM, 31 with no BPM;
- 10.5 s in total.

**Portable scalar build.** We built with `-DKENN_USE_ACCELERATE=OFF` and ran
it on the first 30 files of the set:

- chroma within 4e-13 of the Accelerate build;
- tempo within 3e-13 BPM;
- 3.02 s against 0.31 s.

About 0.1 s per file is fine for a one-file, on-demand request. So unlike
masking, key/tempo needs no backend gate.

## Reading it

- **Speed:** the whole request, decode included, takes 10.5 s on 488 files
  against about 44 s for librosa load plus features, and no longer needs
  librosa.
- **Full key:** native and librosa are equivalent within noise. Both are
  mediocre in absolute terms. Most errors are fifths and relative or parallel
  keys, which is why the mode is not reported.
- **Pitch class:** using the profile tonic instead of the chroma peak is the
  real gain, from 106 to 142 of 250. It holds on the held-out half.
- **Tempo:** about a fifth of files land within 4%. Most of the rest are
  octave errors or abstentions. Treat BPM as a hint, not a measurement.

## Review fixes, 17 Oct

The first adversary review found five problems. All are fixed, each with a test:

- **Held tones got a BPM.** An 8 s 220 Hz sine read 112 BPM at strength
  0.955, as did a swelling pad and white noise; librosa said none. A sine's
  onset envelope has a real periodic ripple from spectral leakage, but it is
  tiny, with a mean rise of 0.06 dB per band and a peak of 0.19.
  - Tempo now needs at least two onsets: envelope peaks rising 4 dB or more.
  - Peaks reached 0.2–1.8 dB on held sines, chords, pads and a saw, under
    4 dB on noise and on a vibrato tone, and a single kick gives one onset.
    All of these now report no BPM. A 120 BPM click still reads 120.1.
  - At 3 dB, noise passed; at 5 dB, more loops were lost.
  - The cost is 41 labelled loops left with no BPM, 7 of which had been
    right (60 to 53); 34 of the 41 had been wrong. We would rather say
    nothing on a pad than print a confident wrong tempo.
  - Candidate lags must also be autocorrelation peaks. On its own this did
    not fix the sine, but it removes the prior-only answer.
- **A 2 Hz header looped forever** with the GIL released. The kernel now
  refuses rates under 8 kHz, and `analyze_sample_audio` abstains first.
- **A stale extension** without `key_tempo_features` raised TypeError. It now
  abstains with "out of date".
- **One NaN sample** reported a confident "C". Non-finite audio now abstains.
- **The speed table** compared librosa load plus features against native
  features only. It is now labelled, and the summary quotes end to end.

The re-review found no blockers and two should-fixes:

- **The onset window depended on the sample rate.** It was rounded up to a
  power of two: 46 ms at 44.1 kHz, 85 ms at 48 kHz. It is now always four
  hops (46 ms), zero-padded to the FFT size.
- **A few isolated hits got a BPM** read off the length of one hit. Two kicks
  read 148 BPM whatever their spacing, because a kick cut off at 0.4 s makes
  an attack and click pair of onsets. A candidate lag now needs at least two
  onset pairs that far apart, so one spacing is never a tempo. Two kicks,
  one-shots and a few sparse vocal chops now report none (12 or more random
  hits can still form two matching gaps by chance; see "Known limits" below).
- **Labelled set after round 2:** 54/258 within 4% (53 before that round),
  wrong down from 68 to 52, 66 with no BPM.
- **Real files after round 2:** on 300 one-shots, pads and FX from the sample
  packs, 35 got a BPM: 0/39 one-shots, 2/111 pads, and 33/150 FX, mostly
  flutters and rhythmic FX.

### Third review

A fresh reviewer found one blocker and three should-fixes:

- **Held low tones still got a BPM.** Below about 45 Hz the 46 ms onset
  window holds under two periods, so a held saw's band levels swing up and
  down with phase on alternate frames: 30 saws got a BPM (an E1 saw read
  112 BPM, a 40 Hz saw read 120 BPM at strength 0.94), along with 10 squares
  (129, 151 and 171 Hz read 120.1).
  - Each band's rise is now measured from the loudest of its previous 4
    frames (`kOnsetReferenceFrames = 4`, one 46 ms window), not from the
    frame before. Against the 4-frame maximum the repeating phase swing
    cancels and held saws from 30 to 45 Hz peak at 1.3 dB.
  - Held tones getting a BPM across a 1020-tone sweep drops from 61 to 4 at
    44.1 kHz, and 0 of 1020 at 48 kHz. The 4 left at 44.1 kHz are aliased
    naive squares and a naive saw at 150–194 Hz, whose folded harmonics beat.
  - A 3-frame reference left an aliased 129 Hz square through and scored
    practically the same on loops (51/258 within 4%, 47 wrong, 76 none). A
    median threshold did nothing and was dropped.
  - **Labelled set:** 50/258 within 4% (54 before), 82 octave errors, 48
    wrong (52 before), 78 with no BPM (66 before). Pitch class is unchanged
    at 142/250. End-to-end time is 10.5 s (11.0–11.5 s under load).
  - **Real files:** 0/39 one-shots, 2/111 pads and 15/150 FX get a BPM (down
    from 33 FX).
- **Upper sample-rate limit.** A corrupt 60 MHz WAV header allocated about
  5 GB of FFT buffers. Both `key_tempo_features` and `analyze_sample_audio`
  now refuse sample rates above 768 kHz.
- **Stale-extension and 48 kHz tests.** The stale-extension test now
  monkeypatches `native_fft._load` to return a module without
  `key_tempo_features`, exercising the `getattr` fallback. The sample-rate
  click-track test is renamed and commented for what it actually verifies.

Known limits:

- A kick cut off hard and repeated still reads about 148 BPM, because its
  attack and click pair recurs.
- 12 randomly placed hits read 53.2 BPM when two pairs happen to share a lag.
- Resampling 60 labelled loops to 22.05, 44.1, 48 and 96 kHz:
  - 9 of 60 loops change between 44.1 and 48 kHz: 2 flip between a BPM and
    none, and 7 switch octave-related picks. These loops have two near-equal
    correlation peaks, so a small change in bin spacing tips the prior.

The scalar build compiles and reads the click track at 120.1 at 44.1 and
48 kHz, the same as Accelerate. Parity was not re-measured: the changes are
control flow and window length, not FFT arithmetic.

## What changed beside it

- `loudness_analysis.estimate_key_and_tempo` is deleted, along with its test.
  No route called it (KENN_PLAN noted this on 16 Oct), and it was librosa-only.
- `analyze_sample_audio` reads WAV through the native decoder, at most the
  first 64 MiB, and analyses the first 60 s.
- AIFF still decodes through librosa when it is installed and abstains
  otherwise.
- Mono and stereo 16/24/32-bit PCM and float are supported. Other WAVs
  abstain.
