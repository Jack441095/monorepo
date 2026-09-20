Type: Game audio optimization
Tags: wwise, unreal, memory, advanced profiler, unreal stats, soundbank, media lifecycle, reverb tail
Status: Approved
Source title: Memory Usage Considerations
Source creator: Audiokinetic
Source URL: https://www.audiokinetic.com/en/public-library/2024.1.6_8842/?id=using_soundbanks_memory.html&source=UE4
Source version: Wwise Unreal Integration 2024.1.6
Reviewed: 2026-07-01

# Wwise Unreal Memory: Profile Both Engines


Short answer:
Wwise and Unreal memory are divided, so diagnose both. Use Wwise Advanced Profiler for Wwise allocations and Unreal's Wwise memory statistics for integration-side allocations.

Try this:
1. Capture a baseline after initialization, during loading the target level, at peak activity, and after unloading.
2. Record SoundBank, media, prefetch, voice, effect, and integration memory rather than one total alone.
3. Confirm which Unreal assets still reference the media after the level or actor is destroyed.
4. Allow active voices and reverb tails to finish, then capture again; media can remain needed after its owning Unreal object disappears.
5. Repeat on the target platform and flag memory that grows after each load/unload cycle.

Why it matters:
A clean Wwise capture does not prove Unreal released every integration asset, and an Unreal total does not explain Wwise arena or media use. Both views are required for a complete budget.

Common mistakes:
- Calling retained media a leak before active tails and sound-engine references have ended.
- Profiling only Play In Editor, where editor assets and loading behavior differ from packaged builds.

When this does not apply:
Platform-native audio memory and third-party plugin allocations may need additional platform tools beyond the Wwise and Unreal views.

Related questions:
- Why do Wwise and Unreal report different audio memory totals?
- When should Wwise media unload after an Unreal object is destroyed?
- How do I detect a Wwise memory leak across level reloads?
- Which profilers should I use for Wwise Unreal memory?

Editor notes: The draft has been structured into the required note format, with clear UK-friendly production language and no invented steps or devices. Metadata lines have remained unchanged as provided.
