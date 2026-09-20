# Wwise Events RTPC States And Switches

Type: Game audio implementation workflow
Tags: wwise, game audio, events, rtpc, game parameter, states, switches, game sync, implementation, audiokinetic
Status: Approved
Source title: Wwise Help 2025.1.4 - Interacting with the game
Source creator: Audiokinetic
Source URL: https://www.audiokinetic.com/en/library/edge/

Short answer:
Use Events for game actions, RTPCs or Game Parameters for continuous values, Switches for mutually exclusive variants, and States for broader game or mix conditions. Do not treat them as interchangeable just because they all connect game logic to sound.

Try this:
1. Start with the gameplay question: what action or condition should change sound?
2. Use a Wwise Event when code needs to trigger behavior such as Play, Stop, Pause, or Set State.
3. Use an RTPC or Game Parameter when the sound should follow a continuous value such as speed, health, distance, RPM, danger, or intensity.
4. Use a Switch when one object needs one selected variant, such as footstep surface, weapon type, material, or character size.
5. Use a State when the whole game, level, music, or mix condition changes, such as paused, underwater, combat, menu, or low health.
6. Name game syncs from the game designer's language, then document the value range or possible options for programmers.
7. Profile the behavior in Wwise before blaming Ableton exports; the problem is often the game sync mapping, not the WAV.

Decision check:
If the value slides, it is probably an RTPC. If the value chooses one label from a list, it is probably a Switch. If the condition affects a broader mode or mix, it is probably a State. If it tells Wwise to do something now, it is an Event.

Why it matters:
Many implementation bugs come from using the wrong Wwise object. A clean Event, RTPC, State, and Switch plan lets Ableton assets stay simple while Wwise handles interactivity.

Related questions:
- What is the difference between a Wwise Event and an RTPC?
- Should footsteps use States or Switches?
- When should I use a State instead of a Game Parameter?
