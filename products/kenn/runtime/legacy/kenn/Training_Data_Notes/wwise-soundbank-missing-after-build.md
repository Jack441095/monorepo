# Wwise SoundBank Map And Missing After Build

Type: Game audio troubleshooting workflow
Tags: wwise, game audio, soundbank, soundbanks, bank map, boot, ui, shared, shared sounds, level audio, missing media, build, generated, load, unload, path, platform, unity, unreal, event, troubleshooting, audiokinetic
Status: Approved
Source title: Wwise 101 - Working with Multiple SoundBanks and Managing SoundBank size
Source creator: Audiokinetic
Source URL: https://www.audiokinetic.com/en/courses/wwise101/

Short answer:
If a Wwise SoundBank works in the editor but is missing after a game build, check generation, platform, packaging, load order, path, and Event inclusion. A generated bank on the wrong platform or outside the build package is still missing at runtime.

Bank map:
Map SoundBanks by runtime need. Keep boot and startup audio in a boot bank, menu and common interface audio in a UI bank, repeated cross-level assets in a shared bank, and scene-specific ambience, dialogue, combat, or music in level banks. Load shared banks before level banks when level audio depends on them, and unload level banks when the player leaves that content.

Try this:
1. Regenerate SoundBanks for the target platform, not only the authoring/editor platform.
2. Confirm the Event and its media are assigned to the bank you expect.
3. Check the generated bank files are copied into the Unity or Unreal build output or streaming assets location used by the integration.
4. Verify the game loads the bank before posting its Events and unloads it only after those sounds are no longer needed.
5. Watch for case-sensitive path/name problems when moving from macOS or Windows editor workflows to target hardware.
6. Keep shared UI or boot Events in a stable always-loaded bank if they are needed before level-specific banks load.
7. Use the profiler or build logs to separate "bank not loaded", "event not in bank", and "media missing" failures.
8. Document the expected bank map: boot banks, shared banks, level banks, music banks, and unload rules.

Check:
Do not assume the bank is valid just because Authoring plays the Event. Authoring can audition content outside the final runtime packaging path.

Why it matters:
SoundBank failures are handoff failures as much as audio failures. KENN should recommend checks that help both the sound designer and programmer find the broken build step.

Related questions:
- My Wwise SoundBank is missing after a Unity build.
- Why does an Event work in editor but not in the packaged game?
- How should I organize Wwise banks for boot, UI, levels, and music?
- How should I map Wwise SoundBanks for boot, UI, shared sounds, and level audio?
