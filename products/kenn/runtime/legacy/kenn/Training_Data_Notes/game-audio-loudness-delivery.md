# Game Audio Loudness Delivery

Type: Game audio delivery workflow
Tags: game audio, loudness, wwise, unity, unreal, dialogue, sfx, music, middleware, delivery, mix targets
Status: Approved

Short answer:
For game audio, loudness is about consistent playback across interactive states, not one final master level. Balance dialogue, music, ambience, and SFX by bus, then test in the engine or middleware with real gameplay intensity.

Try this:
1. Separate dialogue, music, ambience, UI, and SFX into clear buses before judging loudness.
2. Keep dialogue intelligible first; duck music or dense ambiences when narrative content matters.
3. Use loudness meters for long-form checks, but also test short events for peak and annoyance.
4. In Wwise, Unity, or Unreal, test the mix during quiet, normal, and high-action gameplay states.
5. Leave headroom on buses that can stack many simultaneous sounds.
6. Export naming, loop points, fades, and variations clearly so implementation does not break the mix.

Why it matters:
Interactive audio changes every time the player acts. A game mix that sounds balanced in a DAW can overload, mask dialogue, or become fatiguing once many events trigger together.

Related questions:
- How loud should game dialogue be?
- How do I stop game SFX from masking music?
- What should I check before delivering game audio assets?
