# Ableton Multiband Dynamics Device

Type: Ableton device workflow
Tags: ableton, multiband dynamics, multiband compression, dynamics, expansion, crossover, sidechain, mixing, mastering
Status: Approved
Source: Ableton Live 12 Reference Manual (live12-manual-en.pdf)
Reviewed: 2026-07-06

Short answer:
Multiband Dynamics is an advanced dynamics processor that splits the audio signal into three frequency bands (Low, Mid, High) using adjustable crossovers. Each band supports independent upward and downward compression and expansion, making it a powerful tool for corrective mixing and mastering.

Try this:
1. Place Multiband Dynamics on a group bus (like a drum or vocal group) or on your master channel.
2. Set the crossover frequencies (Low-to-Mid and Mid-to-High) to target specific frequency zones (e.g., Low crossover at 120 Hz to isolate sub-bass, High crossover at 3.5 kHz to isolate sibilance).
3. Identify the threshold zones: the outer threshold columns control Downward compression (reducing gain when signals exceed the threshold), and the inner columns control Upward compression (increasing gain when signals fall below the threshold).
4. Apply Upward Compression: adjust the inner threshold and set the ratio above 1.0 to lift low-level harmonics, reverb tails, or quiet vocals without compressing the loud peaks.
5. Apply Downward Compression: adjust the outer threshold and set the ratio to compress loud transients in a specific band (such as taming harsh mid-range guitar frequencies).
6. Configure band-specific sidechaining: open the Sidechain panel, select an external source (like a kick track), and enable sidechaining only on the Low band to duck the sub-bass while leaving the mid-range presence intact.

Why it matters:
Multiband Dynamics lets you correct frequency imbalances that standard single-band compressors cannot handle. It allows you to control muddy low-mid build-up, tame harsh high frequencies, or add low-end pocket sidechaining with surgical precision.

Common mistakes:
- Over-compressing bands independently without level-matching, which shifts the frequency balance of the track and alters the overall mix timbre.
- Setting crossover points too close together, which can introduce phase artifacts or comb-filtering near the crossover frequencies.

When this does not apply:
- Standard single-track processing where a simple, transparent compressor (like standard Compressor) is faster and cleaner to configure.

Related questions:
- What is the difference between upward and downward compression in Multiband Dynamics?
- How do I sidechain only the low end of a bass in Ableton?
- How do I set crossover frequencies in Multiband Dynamics?
- How do I tame harsh frequencies using Multiband Dynamics?
