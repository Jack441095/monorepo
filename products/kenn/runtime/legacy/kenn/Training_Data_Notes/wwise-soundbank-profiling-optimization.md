# Wwise SoundBank Profiling And Optimization

Type: Game audio implementation workflow
Tags: wwise, game audio, soundbank, soundbanks, profiling, cpu, memory, optimization, voices, streaming, mobile, audiokinetic
Status: Approved
Source title: Wwise Help 2025.1.4 - Finishing your projects
Source creator: Audiokinetic
Source URL: https://www.audiokinetic.com/en/library/edge/

Short answer:
SoundBanks are delivery containers for runtime audio data and Events. Profiling tells you whether the game is failing because of CPU, memory, voices, streaming, or missing content. Do not solve runtime problems only by making the Ableton master quieter.

Try this:
1. Group SoundBanks around how the game loads content: boot, shared UI, level, biome, character, combat, or cutscene.
2. Keep common UI and shared system sounds in a stable shared bank instead of duplicating them across level banks.
3. Check that every Event the game calls is included in a loaded SoundBank before debugging mix or export settings.
4. Profile on target hardware, not only on the studio machine.
5. Watch voice count, virtual voices, streaming, CPU, memory, and loud busses during heavy gameplay.
6. If memory is high, review compression, streaming, sample rate, channel count, looping ambience length, and duplicated assets.
7. If CPU is high, review expensive effects, convolution or reverb count, voice limits, bus processing, and random containers with too many simultaneous voices.
8. Export a short reproduction note for programmers: level, action, bank loaded, Event name, expected sound, observed result.

Ableton handoff:
Deliver clean, trimmed WAV assets and implementation notes, but leave runtime loading, voice limiting, and memory decisions to the Wwise project. For mobile, prioritize short mono/stereo assets, controlled tails, and purposeful loop lengths.

Why it matters:
SoundBank and profiling problems can look like bad mixing. KENN should separate production fixes from implementation fixes before recommending EQ, limiting, or re-exporting.

Related questions:
- Why does my Wwise sound play in Authoring but not in game?
- How should I organize SoundBanks for a level?
- How do I reduce Wwise CPU or memory?
