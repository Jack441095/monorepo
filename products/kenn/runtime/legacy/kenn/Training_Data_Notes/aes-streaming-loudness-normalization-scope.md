Type: Advanced streaming reference
Tags: aes td1004, streaming loudness, network playback, normalization, lufs, true peak, mobile listening, peak limiting
Status: Approved
Source title: AES TD1004.1.15-10 Recommendation for Loudness of Audio Streaming and Network File Playback
Source creator: Audio Engineering Society Technical Council
Source URL: https://aes.org/wp-content/uploads/2024/01/AESTD1004_1_15_10.pdf
Source version: Version 1.0, 19 October 2015
Reviewed: 2026-07-01

# AES Streaming Loudness Normalization: Scope and Tradeoffs


Short answer:
AES TD1004 recommends loudness normalization for radio-like streams and network file playback, with a target range intended to balance mobile audibility against excessive peak limiting. It is contextual guidance, not proof that every music platform masters to one fixed number.

Try this:
1. Identify whether the deliverable is a radio-like continuous stream, podcast/network file, music master, or another programme type.
2. Obtain the current platform specification instead of assuming its normalization target from an old chart.
3. Measure integrated loudness and true peak, then codec-audition representative loud and transient sections.
4. Prefer lowering target level over heavy peak limiting when extra loudness creates audible artefacts.
5. Preserve the unconstrained high-resolution master so alternate platform versions can be derived safely.

Why it matters:
The AES document explains the quality tradeoff: a higher target can require more limiting, while a lower target leaves more peak-to-loudness ratio and may sound clearer but quieter without normalization.

Common mistakes:
- Treating the document's 2015 recommendation as a live specification for every current streaming service.
- Forcing all content to the same number without considering programme type and codec behavior.

When this does not apply:
Film, highly dynamic surround content, and platform-specific music delivery can follow different standards. Use the current delivery contract.

Related questions:
- Does AES recommend one LUFS target for every streaming platform?
- Why can a lower streaming target preserve more dynamics?
- How does true peak affect lossy streaming delivery?
- Should I limit harder or lower the streaming target?
