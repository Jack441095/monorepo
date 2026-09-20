# AES TD1008 Internet Streaming Loudness Recommendations

Type: Advanced streaming reference
Tags: aes td1008, loudness, streaming, internet audio, normalization, lufs, true peak, album normalization, speech loudness, music loudness, distribution
Status: Approved
Source: AES TD1008 — Recommendations for Loudness of Internet Audio Streaming and On-Demand Distribution (aes-td1008.pdf)
Reviewed: 2026-07-06

Short answer:
AES TD1008 recommends standardized loudness targets for streaming and on-demand audio distribution. It targets -16 LUFS for music, -18 LUFS for speech, and a maximum true peak of -1 dBTP to prevent inter-sample clipping and ensure consistent playback levels across platforms.

Try this:
1. Determine your delivery target: target -16 LUFS for music-only content, and -18 LUFS for speech-focused content (podcasts, audiobooks, talk radio).
2. For mixed-format streams (where speech and music are combined in real-time), target -17 LUFS to balance the two content types.
3. Ensure that your maximum True Peak level never exceeds -1 dBTP (or -2 dBTP for louder masters above -14 LUFS) to prevent clipping distortion during lossy codec transcoding.
4. Implement album normalization: normalize the loudest track from the album to -14 LUFS, allowing the quieter tracks to maintain their relative dynamic relationships instead of normalizing every track individually.
5. Check your audio files using an ITU-R BS.1770 compliant meter before exporting the final delivery package.

Why it matters:
AES TD1008 aims to eliminate inconsistent playback levels and reduce the need for excessive limiting (the "loudness war"). Following these guidelines preserves the dynamic range and transients of your tracks while ensuring they translate consistently without sounding squashed on streaming platforms.

Common mistakes:
- Crushing the master's dynamics to achieve a higher LUFS level before uploading; streaming platforms will simply turn down the track, leaving it sounding flat and lifeless compared to dynamic, normalized tracks.
- Ignoring the True Peak limit, which can cause audible inter-sample clipping when the file is transcoded to lossy formats (like MP3, AAC, or Ogg Vorbis) by the streaming service.

When this does not apply:
- Cinema surround sound, terrestrial television broadcast, and highly dynamic classical performances, which follow separate standards (like EBU R 128 or ATSC A/85).

Related questions:
- What are the loudness targets recommended by AES TD1008?
- What is the difference between AESTD1004 and AESTD1008?
- How does album normalization work under AES TD1008?
- Why does AES recommend a maximum true peak of -1 dBTP?
