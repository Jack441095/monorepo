# Wwise Engine Handoff For Unity And Unreal

Type: Game audio implementation workflow
Tags: wwise, unity, unreal, game audio, integration, events, soundbank, naming, handoff, programmer, implementation
Status: Approved
Source title: Wwise Help 2025.1.4 - Wwise Unity Integration and Wwise Unreal Integration
Source creator: Audiokinetic
Source URL: https://www.audiokinetic.com/en/library/edge/

Short answer:
A Unity or Unreal handoff should include Event names, SoundBank names, game sync names, asset paths, and expected behavior. Do not hand programmers only WAVs and expect the implementation intent to be obvious.

Try this:
1. Create a short implementation sheet with Event name, trigger condition, Wwise object, SoundBank, game object, and owner.
2. Use stable naming such as `Play_UI_Click`, `Play_Footstep`, `Set_State_Combat`, or `Set_Switch_Surface_Concrete`.
3. Document RTPC ranges and units, for example speed `0-1`, health `0-100`, distance in meters, or intensity `0-100`.
4. Document Switch or State values exactly as they appear in Wwise so code and Wwise do not drift.
5. Include required banks for each scene, level, menu, or gameplay mode.
6. Include expected audition behavior: where the sound plays, whether it loops, how it stops, and what should happen when the object despawns.
7. For bugs, report the engine scene, game object, Event, bank loaded, repro steps, and whether it works in Wwise Authoring.

Ableton role:
Ableton provides clean source assets, loops, stems, and reference mixes. The engine handoff describes how those assets should become runtime behavior through Wwise and the game engine.

Why it matters:
Most Unity or Unreal audio bugs are naming, loading, or game-sync bugs. A clear handoff lets KENN answer implementation questions without pretending the problem is always a mix problem.

Related questions:
- What should I give a Unity programmer for Wwise audio?
- How should I name Wwise Events for Unreal?
- Why does my Wwise Event work in Authoring but not in Unity?
