# Jack Gandy Personal Gain-Staging Targets

Type: Personal studio workflow
Tags: jack, gain staging, ableton, headroom, volume, meter, peak, average, dbfs, mix prep
Status: Approved
Source: Jack Gandy Personal Workflow
Reviewed: 2026-07-07

Short answer:
Jack Gandy's target gain-staging levels in Ableton Live are an average of -18 dBFS (for RMS/loudness) with peaks capped at -6 dBFS. This guarantees healthy analog-modeled plugin operation and leaves ample headroom for the final master.

Try this:
1. Insert a Utility device at the front of every track's device chain.
2. Adjust the Utility gain so that average levels sit around -18 dBFS on the meter.
3. Verify that the peak levels on individual channels do not exceed -6 dBFS.
4. Keep the main track faders at 0 dB (unity) for final balancing rather than using them to fix gain-staging problems.

Why it matters:
Most analog-modeled plugins are calibrated to reference -18 dBFS as 0 VU. Staying at this target keeps plugins running in their clean sweet spot rather than forcing them into accidental digital distortion. It also ensures that summing multiple tracks does not clip the master bus.

Common mistakes:
- Allowing individual tracks to peak near 0 dBFS, which leaves no headroom on the master bus and clips summing nodes.

When this does not apply:
- When intentionally driving a saturator or analog plugin hard to get audible clipping or soft saturation.

Related questions:
- What are Jack's gain staging targets?
- What headroom does Jack Gandy target?
- How does Jack prep a mix?
