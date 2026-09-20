# Jack Gandy Client Export Specifications

Type: Personal studio workflow
Tags: jack, export, stems, wav, mp3, format, sample rate, bit depth, dither, client delivery
Status: Approved
Source: Jack Gandy Personal Workflow
Reviewed: 2026-07-07

Short answer:
Jack Gandy has two distinct export configurations depending on the client type:
1. **Streaming Release (Final Masters)**: Export as lossless WAV, 24-bit depth, 44.1 kHz sample rate, with Triangular dither enabled.
2. **Client Preview**: Export as MP3, 320 kbps constant bit rate (CBR), for fast email/chat sharing.

Try this:
1. Open the Export Audio/Video dialog in Ableton (Cmd+Shift+R).
2. Set File Type to WAV.
3. Choose Sample Rate: 44.100 (unless requested otherwise).
4. Set Bit Depth: 24.
5. Set Dither Options: Triangular (use this if exporting to a lower bit depth than the internal 32-bit floating point).
6. Enable the MP3 export toggle at 320 kbps if sending draft previews.

Why it matters:
24-bit/44.1kHz is the gold standard for digital distribution (Spotify, Apple Music). Dithering is critical when converting 32-bit float audio to 24-bit because it covers truncation distortion with low-level noise, preserving the resolution of quiet tails.

Common mistakes:
- Exporting previews as heavy, uncompressed WAVs, which makes email or chat delivery slow and cumbersome.
- Forgetting to dither when downgrading bit depth.

When this does not apply:
- When a client explicitly requests high-resolution delivery (e.g. 96 kHz / 32-bit WAV for video post-production or archiving).

Related questions:
- What are Jack's export specifications?
- What file format does Jack Gandy deliver to clients?
- When should I dither in Ableton?
