Type: Mastering/mixing diagnostic
Tags: loudness range, lra, dynamics, mastering, compression, mix diagnosis, loudness meter
Status: Approved
Source title: EBU Tech 3343 — Guidelines for Production of Programmes in accordance with EBU R 128
Source creator: European Broadcasting Union (EBU), PLOUD group
Source URL: https://tech.ebu.ch/publications/tech3343
Source version: V4, November 2023 (§ 3.3 Loudness Range, § 11.2.2)
Reviewed: 2026-07-06

# Loudness Range (LRA) as a Dynamics Diagnostic

Short answer:
Loudness Range (LRA), measured in LU, quantifies how much a track's loudness actually varies over its length — it's a statistical spread, not a peak-to-trough number, so one loud drum hit or one quiet intro can't swing it on its own. It's a genuinely useful second opinion alongside your ears for judging whether a mix or master has been over-compressed, and for checking that a mastering chain hasn't quietly flattened a mix's dynamics.

Try this:
1. Run LRA on a reference mix or master you already know sounds good, in the genre you're working in, to get a feel for what a healthy number looks like for that style (very dense/loud EDM masters often sit low; acoustic or classical material sits much higher).
2. Measure LRA on your own mix before and after mastering-chain processing (compression, limiting).
3. If LRA drops sharply after processing with no deliberate creative intent behind it, that's a flag: the chain is squashing dynamics more than you meant to, even if peak level and integrated loudness look fine.
4. Use LRA together with, not instead of, listening — a good LRA number on an unpleasant-sounding mix doesn't mean the mix is fine.
5. When a client says a reference track "hits harder," compare LRA and short-term loudness swings, not just integrated loudness — a mix can hit harder by having a wider LRA (more contrast between sections) rather than by being louder overall.

Why it matters:
Loudness Range was designed to catch exactly the kind of over-processing that a simple integrated-loudness or peak reading can't see: a track can be gated below -70 LUFS excluded, statistically trimmed of outliers, and still show you a clean, comparable number for "how much this track's energy actually moves around." That makes it a good proxy for "was this over-compressed" that doesn't depend on genre-specific loudness targets.

Common mistakes:
- Treating LRA as something to hit a specific number for — there's no universal "correct" LRA, it depends entirely on genre and artistic intent.
- Only checking LRA after mastering and never comparing it to the pre-master mix, missing exactly the before/after comparison that makes it useful.
- Assuming a wide LRA always means "better" — some genres (aggressive electronic, some hip-hop) intentionally want a narrow, dense LRA as part of the sound.

When this does not apply:
Very short clips (under roughly 60 seconds — think ad reads, intros, drops) don't generate enough data points for a meaningful LRA reading; don't trust it on short-form content.

Related questions:
- How do I know if my master is over-compressed?
- What's a good Loudness Range for [genre]?
- Why does my mix sound flat after mastering even though the loudness is fine?
- What's the difference between LUFS and Loudness Range?
