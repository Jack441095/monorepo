Type: Advanced metering reference
Tags: itu bs 1770, k weighting, integrated loudness, lufs, lkfs, gating, channel weighting, loudness meter
Status: Approved
Source title: Recommendation ITU-R BS.1770-5
Source creator: International Telecommunication Union
Source URL: https://www.itu.int/dms_pubrec/itu-r/rec/bs/R-REC-BS.1770-5-202311-I%21%21PDF-E.pdf
Source version: BS.1770-5, November 2023
Reviewed: 2026-07-01

# ITU BS.1770 K-Weighting and Gated Programme Loudness

Short answer:
BS.1770 programme loudness is not an ordinary RMS reading. It applies a two-stage K-weighting filter, measures mean-square energy per channel, applies channel weighting, sums the result, and uses absolute and relative gating for integrated measurement.

Try this:
1. Use a meter that explicitly supports the required BS.1770 revision and delivery format.
2. Measure the complete programme for integrated loudness; use momentary and short-term readings for local behaviour rather than substituting them for the final integrated value.
3. Confirm channel mapping before trusting a multichannel or immersive reading.
4. Keep the LFE treatment and render configuration consistent with the applicable specification.
5. Record the meter standard, programme region, true peak, and measurement scope in the delivery report.

Why it matters:
Two meters can disagree when they use different algorithm revisions, channel layouts, gates, or measurement ranges. Naming the standard makes a loudness value reproducible.

Common mistakes:
- Calling any average level measurement LUFS without confirming BS.1770-compatible processing.
- Measuring only the loudest section and reporting it as full-programme integrated loudness.

When this does not apply:
BS.1770 defines measurement algorithms, not one universal creative mastering target. Follow the platform, broadcaster, client, or regional delivery specification.

Related questions:
- What does K-weighting do in a LUFS meter?
- Why does integrated loudness use gating?
- Why do two LUFS meters disagree?
- Does BS.1770 specify one mastering loudness target?

Useful terms:
- **K-Weighting**: A filter applied to measure mean-square energy per channel.
- **Integrated Loudness**: The sum of the loudness values across all channels, adjusted for gating and weighting.
- **Gating**: Technique used to limit the influence of short-term peaks on integrated measurements.

Editor notes:
The excerpt focuses on the application of BS.1770 in measuring programme loudness, emphasizing the importance of using a meter that supports the required revision and format. It also highlights common mistakes and when BS.1770 does not apply. The related questions provide further context for understanding the topic.
