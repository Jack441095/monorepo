# Real stem Mix Review check — 2026-09-10

This is a read-only diagnostic check against five user-supplied,
time-aligned stems from one real song: kick, hi-hat, bass, piano, and lead
vocal. The source audio was used only for this analysis, was not copied into
the repository, and was removed from the temporary remote workspace after
the run.

## Result

- Analyzer: `kenn.mix_review_masking_analysis.v1`
- Shared sample rate: 44.1 kHz
- Shared analyzed duration: 239.41 seconds
- Stems: 5
- Findings: 5

The strongest candidate was:

- **Bass ↔ piano, 80–250 Hz:** comparable simultaneous energy for **45.4%**
  of the shared playing time; medium-severity listening check.

Additional lower-confidence candidates were:

- **Bass ↔ lead vocal, 80–250 Hz:** **26.7%** of shared time.
- **Piano ↔ lead vocal, 80–250 Hz:** **26.9%** of shared time.
- **Piano ↔ lead vocal, 250–500 Hz:** **21.2%** of shared time.
- **Piano ↔ lead vocal, 500–2,000 Hz:** **23.1%** of shared time.

## Interpretation boundary

These are measured energy-competition candidates, not psychoacoustic masking
 diagnoses. They do not account for transient timing, stereo placement,
relative mix levels, arrangement intent, or listener perception. The correct
next step is to audition the named pair and band, then decide whether a
complementary EQ, level, arrangement, or no change is appropriate. This check
does not qualify the Mix Reviewer or claim that any track requires EQ.
