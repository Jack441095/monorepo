# EBU Tech 3342 Loudness Range (LRA) Calculation

Type: Advanced metering reference
Tags: ebu tech 3342, loudness range, lra, dynamics, ebu r 128, relative gate, absolute gate, loudness unit, lu, statistics
Status: Approved
Source: EBU Tech 3342 — Loudness Range: A descriptor to supplement loudness normalisation in accordance with EBU R 128 (ebu-tech-3342-lra.pdf)
Reviewed: 2026-07-06

Short answer:
Loudness Range (LRA) measures the statistical variation of loudness over time within a track or programme. It uses a double-gated method (an absolute threshold at -70 LKFS and a relative sliding gate at -20 LU relative to the ungated level) to ignore silent sections and determine the spread of the middle 85% of loudness levels.

Try this:
1. Insert an EBU R 128 compliant loudness meter on your master fader or group bus.
2. Measure the LRA over a complete playback of your song from start to finish; brief sweeps do not yield correct statistical LRA values.
3. Understand the gating thresholds: the meter ignores audio below -70 LKFS (absolute gate) and also ignores quiet passages that fall more than 20 LU below the average level (relative sliding gate).
4. Evaluate LRA based on genre: highly dynamic music (like classical or jazz) typically has an LRA above 12 LU; standard pop/rock mixes target 5–9 LU; heavily limited or squashed club tracks often have an LRA below 4 LU.
5. Use LRA to guide downstream processing: if your master's LRA is too wide for target streaming or mobile listening environments, apply gentle bus compression to control macro-dynamics rather than crushing transient peaks with a brickwall limiter.

Why it matters:
LRA provides a standardized, objective measure of dynamic range that is independent of the overall volume level. It helps you design mixes that fit specific distribution targets (like streaming vs. cinema vs. broadcast) without relying on inaccurate peak-to-RMS ratios.

Common mistakes:
- Confusing LRA with dynamic range measured by crest factor (peak-to-RMS). Crest factor measures short-term transient peaks, whereas LRA measures macro-dynamics (such as verse-to-chorus volume changes) over the entire track.
- Relying on short-term or momentary LRA readings, which are statistically invalid. LRA requires the entire program duration to build its cumulative distribution curve.

When this does not apply:
- Very short audio clips (less than 3 seconds), as there is insufficient data to calculate a meaningful statistical distribution.

Related questions:
- How is Loudness Range (LRA) calculated?
- What are the absolute and relative gates in LRA?
- What is a good LRA target for streaming music?
- How does LRA differ from crest factor?
