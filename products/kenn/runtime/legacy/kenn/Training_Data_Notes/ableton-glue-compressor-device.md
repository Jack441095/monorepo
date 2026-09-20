# Ableton Glue Compressor Device

Type: Ableton device workflow
Tags: ableton, glue compressor, compression, bus compression, analog, ssl, soft clip, range control, dry wet, sidechain
Status: Approved
Source: Ableton Live 12 Reference Manual (live12-manual-en.pdf)
Reviewed: 2026-07-06

Short answer:
Glue Compressor is an analog-modeled transistor-based bus compressor developed in collaboration with Cytomic. Emulating classic 1980s SSL bus compressors, it features a dynamic Range control, a built-in sidechain highpass filter, and an integrated Soft Clip peak limiter.

Try this:
1. Insert Glue Compressor on your master fader or group bus (such as drums or instruments).
2. Set Ratio to 2:1 for transparent leveling, or 4:1 for tighter, punchier glue.
3. Adjust Attack time: use slow settings (10–30 ms) to let transients pass through, or fast settings (0.01–0.3 ms) to catch sharp peaks immediately.
4. Adjust Release time: select Auto for program-dependent release, or manually set it to match the track's tempo (usually 0.1 s to 0.6 s).
5. Lower the Threshold until you see 1–3 dB of gain reduction on the meter.
6. Use the Range control to limit the maximum gain reduction applied (e.g., set Range to 3–6 dB), preventing the compressor from over-compressing unexpected loud hits.
7. Open the sidechain panel and enable the Sidechain HP Filter to prevent low-end energy (like a kick drum or sub-bass) from triggering excessive compression.
8. Toggle the Soft Clip switch to insert an analog-modeled waveshaping limiter before the output, letting you warm up transients and prevent digital clipping.

Why it matters:
Glue Compressor is the standard tool for bringing cohesion to a group of tracks. Its analog saturation (Soft Clip) and Range limiter let you control bus dynamics and add punch with fewer artifacts than standard digital compressors.

Common mistakes:
- Over-compressing the low end by leaving the Sidechain HP Filter off, which causes the entire mix to pump or lose bass energy on every kick drum hit.
- Leaving Soft Clip active on clean acoustic tracks, which can introduce unwanted saturation or harmonic distortion.

When this does not apply:
- Surgical channel-level dynamics control or upward compression (use standard Compressor or Multiband Dynamics instead).

Related questions:
- How does the Range control work on Ableton Glue Compressor?
- When should I use the Sidechain Filter on Glue Compressor?
- What does the Soft Clip toggle do in Glue Compressor?
- What are the best Glue Compressor settings for a mix bus?
