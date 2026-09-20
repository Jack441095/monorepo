# Jack Gandy Mastering Clipper Workflow

Type: Personal studio workflow
Tags: jack, mastering, clipper, soft clip, limiter, loudness, lufs, transients, dynamics
Status: Approved
Source: Jack Gandy Personal Workflow
Reviewed: 2026-07-07

Short answer:
Jack Gandy uses a soft clipper (or Ableton's Saturator in soft-clip mode) directly *before* the brickwall limiter in his mastering chain. This clips off the fastest, unhearable transient peaks, allowing the final limiter to achieve a louder master without introducing pumping or limiting artifacts.

Try this:
1. Place a soft clipper (e.g. Ableton's Saturator with Soft Clip enabled and Drive at 0 dB) immediately before the mastering limiter.
2. Push the gain into the soft clipper until you see it shave off 1–2 dB of the fastest transients (check the waveform or gain reduction meters).
3. Set the final mastering limiter ceiling to -1.0 dB (or -0.5 dB to prevent inter-sample clipping on streaming platforms).
4. Monitor the master's integrated loudness, targeting -10 to -8 LUFS for loud modern genres.

Why it matters:
Limiters sound bad when forced to react to ultra-fast, high-amplitude transients (like snare or kick hits); they trigger wide gain reduction envelopes that pull down the volume of the whole mix, causing pumping. A clipper clips these peaks instantly without recovery time, preserving dynamic energy.

Common mistakes:
- Clipping too hard (over 3 dB), which introduces audible, harsh high-frequency distortion and ruins the mix balance.
- Setting the limiter ceiling to 0.0 dB, which causes clipping distortion during conversion to streaming codecs (like MP3/AAC).

When this does not apply:
- In highly dynamic acoustic, jazz, or classical music where transient peaks must remain untouched.

Related questions:
- Where does Jack Gandy place the clipper in mastering?
- Why use a clipper before a limiter?
- What are Jack's mastering loudness targets?
