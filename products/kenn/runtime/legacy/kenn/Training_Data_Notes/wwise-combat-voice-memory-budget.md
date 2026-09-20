# Wwise Combat Sounds Drop Out Voice And Memory Budget

Type: Game audio troubleshooting workflow
Tags: wwise, game audio, combat, sounds drop out, drop out, drops out, louder, assets louder, voice, voices, voice count, virtual voice, priority, limit, limits, cpu, memory, ambience, streaming, compression, random container, profiler, optimization, mobile, mobile build, audiokinetic
Status: Approved
Source title: Wwise 101 - Managing SoundBank size and Optimizing your sound design
Source creator: Audiokinetic
Source URL: https://www.audiokinetic.com/en/courses/wwise101/

Short answer:
If combat audio becomes messy, expensive, or drops sounds, profile voice count, priority, limits, CPU, memory, and streaming before changing the mix. Combat usually needs deliberate voice budgeting, not louder assets.

Sounds drop out:
When Wwise sounds drop out during heavy combat, inspect voice count, virtual voice behavior, voice limits, priority, CPU, memory, and streaming before making assets louder. A louder WAV will not fix a sound that is being limited, virtualized, starved by streaming, or pushed below priority.

Try this:
1. Capture heavy combat in the Wwise profiler on target hardware.
2. Count simultaneous weapons, impacts, footsteps, UI, dialogue, music, ambience, reverb sends, and tails.
3. Set voice limits and priority so critical cues win over repeated low-priority debris or tails.
4. Use virtual voice behavior intentionally; do not let important one-shots silently virtualize.
5. Shorten or trim long tails that stack during rapid actions.
6. Review Random Containers that can trigger too many layers at once.
7. Stream long music and ambience where appropriate, but keep short responsive SFX as memory-loaded assets when needed.
8. For mobile, reduce duplicate variations, channel count, sample rate, long loops, and expensive effects before blaming the composer.

Check:
If a sound disappears only during busy combat, suspect voice limit, priority, bus processing, streaming, or memory pressure before assuming the Event is broken.

Why it matters:
Combat is a stress test for implementation. KENN should recommend a profiler-led budget pass that preserves important gameplay feedback.

Related questions:
- Why do Wwise sounds drop during combat?
- During heavy combat some Wwise sounds drop out. What should I inspect before making the assets louder?
- How do I reduce Wwise voice count without killing impact?
- My mobile build runs out of audio memory during ambience and combat.
