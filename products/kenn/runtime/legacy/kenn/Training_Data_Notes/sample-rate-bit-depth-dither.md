# Sample Rate, Bit Depth, and Dither

Type: Export workflow
Tags: sample rate, 44.1 khz, 48 khz, bit depth, dither, export, mastering, recording, video delivery, delivery specification, wav
Status: Approved
Source: Audio_Too studio practice
Reviewed: 2026-07-01

Short answer:
Record and mix at the project's native sample rate, normally 44.1 or 48 kHz, using 24-bit audio or 32-bit float processing. Dither once, only when reducing the final file to a fixed lower bit depth such as 16-bit.

Try this:
1. Choose 48 kHz for video or game work and follow the delivery specification when one exists; 44.1 kHz remains normal for music-only delivery.
2. Record at 24-bit so conservative input levels still retain ample resolution.
3. Keep intermediate stems and mastering files at 24-bit or 32-bit float without dither.
4. Perform sample-rate conversion once with a high-quality offline converter when the final format requires it.
5. Add dither at the final word-length reduction, after limiting, and do not dither a file that stays at 32-bit float.

Why it matters:
Repeated conversion and repeated dither provide no benefit. Sensible gain staging at 24-bit matters more than chasing very high sample rates without a delivery need.

Related questions:
- Should I record music at 44.1 kHz or 48 kHz?
- When should I use dither on an export?
- Should stems be 24-bit or 32-bit float?
- Does a higher sample rate automatically sound better?
