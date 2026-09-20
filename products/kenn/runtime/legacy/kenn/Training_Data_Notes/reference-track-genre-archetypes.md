# Reference-Track Genre Archetype Classification

Type: AutoMix / Mix Review analysis tooling
Tags: genre classification, tonal balance, spectral archetype, reference track, genre envelope, mix style, confidence score
Status: Approved
Source: studio/audio_analysis/audio_analysis/analysis_core/genre_profiles.py (GENRE_SEED_PROFILES, classify_reference_profile), studio/audio_analysis/audio_analysis/mix_review/mix_style_classifier.py (classify_genre)
Reviewed: 2026-08-06

Short answer:
`GENRE_SEED_PROFILES` is a fixed table of 21 genre spectral archetypes (Pop, Hip Hop/Rap, Rock, EDM, Jazz, Classical/Orchestral, Acoustic, Cinematic, Lo-Fi, Club/Techno, Podcast, Pop Rap, Metal, Folk, Blues, Ambient, Synthwave, Reggae, Latin, Techno/House, Premaster Target), each with a programmatically generated 40-band log-spaced spectral profile (from a slope + bass-boost + mids-boost + highs-rolloff shape) plus expected crest factor, max LUFS, min loudness range, and stereo correlation. `classify_reference_profile()` compares any mix's measured 40-band spectrum against all 21 archetypes (spectral RMS distance in dB, plus a small penalty for crest-factor and LUFS mismatch) and returns the closest match with a 0-1 confidence score. `mix_style_classifier.py::classify_genre()` wires this into every Mix Review report as `report["mix_style"]["genre"]`.

Try this — real archetype parameters from this codebase's actual `GENRE_SEED_PROFILES` table (2026-08-06):
1. Pop: spectral slope -3.5 dB/octave, +1.0 dB bass boost (60-150 Hz), crest factor target 8.0 dB, LUFS ceiling -10.0, stereo correlation 0.85.
2. Hip Hop/Rap: slope -4.5 dB/octave, +4.0 dB bass boost, -12 dB highs rolloff above 15kHz, crest factor 9.0 dB, LUFS ceiling -9.0.
3. EDM/Dance: slope -4.0 dB/octave, +3.0 dB bass boost, crest factor 7.5 dB (tightly controlled dynamics), LUFS ceiling -8.0, stereo correlation 0.88 (widest of the common genres).
4. Jazz/Blues: slope -3.5 dB/octave, +1.0 dB mids boost, crest factor 11.0 dB (the most dynamic of the "commercial" genres, well above the loudness-war zone), LUFS ceiling -14.0.
5. Lo-Fi Beats: slope -5.0 dB/octave (the darkest overall tilt), +2.5 dB bass boost, -18 dB highs rolloff (steepest of any genre), crest factor 8.0 dB.
6. Classical/Orchestral: crest factor 14.0 dB and LRA minimum 12.0 dB — the most dynamic archetype in the table by a wide margin, reflecting real orchestral mastering practice rather than a "loud" commercial target.

Why it matters:
This gives KENN a real, numeric basis for saying "your mix classifies as Pop-leaning at 82% confidence" instead of guessing from genre metadata or an LLM's impression of the audio — the confidence score is a direct function of measured spectral distance (in dB) plus crest-factor/LUFS mismatch, not a model's subjective read. It answers a genuinely different question than the per-reference-track EQ move list: classification says "which commercial convention does this mix resemble," while the EQ moves (`comparison.eq_bands`, from `solve_parametric_eq`) say "what's the spectral difference between this specific mix and this specific uploaded reference file." The two are computed by completely different code paths and should not be conflated — a mix can classify confidently as Pop while still needing EQ moves to match one particular Pop reference track, and vice versa.

Common mistakes:
- Treating the classified genre's archetype curve as the source of the concrete "Boost/Reduce X dB around Y Hz" EQ moves shown in a reference-track comparison. It is not — those moves are always solved against the actual uploaded reference file's measured spectrum (`ref_log_bands`), never against a genre archetype. Grounding an EQ-move recommendation in a genre note would misrepresent where the number actually came from.
- Assuming a low classification confidence means the mix is bad. It only means the mix's spectral shape doesn't closely resemble any of the 21 coded archetypes — a legitimate outcome for genre-blending, experimental, or simply unconventional mixes.
- Confusing `classify_genre()`'s confidence score with `compute_tonal_balance_envelope_score()`'s 0-100 score. The former is "how close is this mix to the nearest genre archetype, as a distance-based 0-1 confidence"; the latter is "how far outside a genre's mean±std envelope does each band fall," a different, separately-computed 0-100 scale used when a genre (rather than a specific reference file) is the mix target.

When this does not apply:
- A mix with fewer than 40 measured spectral bands (`log_bands_40` missing or malformed) cannot be classified; `classify_genre()` returns `{"genre_key": "", "genre_name": "Uncategorised", "confidence": 0.0}` rather than guessing.
- This says nothing about loudness-war participation or vintage/modern mastering character — those are separate, independently-computed classifiers in the same `mix_style_classifier.py` module (`classify_loudness_war`, `classify_vintage_or_modern`), combined into `report["mix_style"]` alongside genre but not derived from it.

Related questions:
- What genre does my mix's spectral balance most resemble?
- How confident is KENN's genre classification for this mix?
- Why does my mix classify as one genre when I intended a different one?
- What's the difference between genre classification and the reference-track EQ move list?
