# Reference Track Profile Analysis

Type: AutoMix analysis tooling
Tags: reference track, tonal balance, spectral analysis, high-to-low ratio, mixing reference, genre calibration
Status: Approved
Source: scripts/eval/analyze_reference_tracks.py (7-band fingerprint + high-to-low ratio), analysis_core/dsp_metrics.py (log_band_ratios_track_average), analysis_core/genre_profiles.py (map_40_to_7_bands)
Reviewed: 2026-07-18

Short answer:
Every audio file under `reference_tracks/` can be measured with the same 7-band tonal-balance fingerprint (sub/bass/low_mids/mids/presence/sibilance/air) and a single "high-to-low ratio" (presence+sibilance+air energy divided by sub+bass+low_mids energy) that AutoMix's own mixes are scored against. This turns "how bright/dark is this reference track" from an ear judgment into a real number, and gives KENN something concrete to ground an answer in when asked about a specific reference track's character.

Try this — real measured values from this codebase's actual reference_tracks/ folder (2026-07-18, `scripts/eval/analyze_reference_tracks.py`):
- Stromae/Pomme ("Ma Meilleure Ennemie"): high-to-low ratio 1.05 — close to balanced, slightly low-leaning. This is the reference this session's low-shelf correction work was calibrated against.
- The Weeknd (Ninetys x HUCCI remix): 1.28 — similarly close to balanced, a touch brighter.
- "poisonous waters": 0.70 — low-leaning, warmer overall balance.
- Jess Benko: 0.56 — the warmest/darkest of the full mixes measured.
- 070 Shake (Studio Acapella): 4.63 — a clear outlier, and correctly so: this is a vocal-only acapella file with little to no bass content, not a full mix, so a high ratio here reflects the file type, not a "bright" mixing choice.

Why it matters:
A single reference track's ratio is not a universal target — comparing a mix to Stromae/Pomme's 1.05 makes sense for that specific calibration exercise, but a genre with legitimately different conventions (or, as the acapella case shows, a file that isn't even a full mix) would give a misleading target if used blindly. Always check what kind of file is being used as "the reference" before treating its number as a goal.

Common mistakes:
- Treating an acapella, stem, or isolated element's measured ratio as if it were a full-mix target — a vocal-only file has no reason to carry meaningful low-frequency energy, so its ratio says nothing about mix balance.
- Assuming one reference track's ratio generalizes across genres — level-match and compare against two or three references in the same style before drawing a conclusion, same guidance as the general spectral-slope note.
- Confusing this ratio with the fuller 0-100 tonal-balance score (`compute_tonal_balance_score`) used elsewhere — the ratio is a simple, single-number high-vs-low summary; the full score does a genuine band-by-band comparison against a specific target track and is the number actually used to validate corrections like the low-shelf fix.

When this does not apply:
- This is a read-only analysis tool, not a correction — it doesn't change anything about a mix or a reference track, just measures and reports.
- Profiles are computed from whatever files currently exist in `reference_tracks/`; if that folder's contents change, the specific numbers above are stale and `analyze_reference_tracks.py` should be re-run.

Related questions:
- How bright or dark is this reference track compared to my mix?
- What's a typical high-to-low energy ratio for a well-balanced master?
- Why does an acapella file measure so differently from a full mix on a tonal-balance analysis?
