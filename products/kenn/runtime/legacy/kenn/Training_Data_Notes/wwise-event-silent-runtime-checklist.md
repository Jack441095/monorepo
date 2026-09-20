# Wwise Event Silent Runtime Checklist

Type: Game audio troubleshooting workflow
Tags: wwise, game audio, event, events, silent, no sound, runtime, authoring, game object, soundbank, soundbanks, profiler, unity, unreal, troubleshooting, audiokinetic
Status: Approved
Source title: Wwise 101 - Profiling Game Syncs and Working with Multiple SoundBanks
Source creator: Audiokinetic
Source URL: https://www.audiokinetic.com/en/courses/wwise101/

Short answer:
If a Wwise Event plays in Authoring but is silent in-game, debug the runtime chain before changing the mix. Confirm the Event name, loaded SoundBank, registered game object, listener position, bus routing, voice limits, and profiler capture.

Try this:
1. Verify the exact Event string or ID the game posts; a typo or renamed Event can look like a bad export.
2. Confirm the SoundBank containing that Event and media is generated and loaded before the Event is posted.
3. Check the game object is registered and has a valid position when the Event is posted.
4. Confirm the listener exists, is assigned correctly, and is close enough if attenuation or spatialization is active.
5. Look for muted busses, bypassed routing, voice limits, virtual voices, and zero-volume RTPC or State changes.
6. Capture with the Wwise profiler while reproducing the issue and check whether the Event is received, rejected, virtualized, or missing media.
7. Test with a known-good simple one-shot Event in the same scene to separate game integration from asset-specific problems.
8. Write the reproduction clearly: scene, game action, Event, SoundBank, expected result, observed result, and profiler evidence.

Check:
Do not start by re-exporting from Ableton or adding gain. Runtime silence is usually caused by integration state, missing bank/media, object/listener setup, routing, or voice management.

Why it matters:
KENN should diagnose the Wwise signal path in order. A good answer separates Authoring playback from the runtime call chain and gives a programmer a reproducible checklist.

Related questions:
- My Wwise Event plays in Authoring but is silent in Unity. What should I check?
- Why does Wwise receive my Event but no sound comes out?
- How do I troubleshoot Wwise runtime silence?
