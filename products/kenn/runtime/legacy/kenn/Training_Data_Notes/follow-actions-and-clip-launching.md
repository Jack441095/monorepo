# Follow Actions and Clip Launching

Type: Production workflow
Tags: follow actions, session view, clip launch, loop, chain, random, ableton, arrangement, live performance
Status: Approved
Source: Ableton Live 12 Manual
Reviewed: 2026-07-01

Short answer:
Follow Actions tell a clip what to do when it finishes playing — play the next clip, a random clip, jump back to itself, or stop. They are the main tool for building generative loops, multi-clip sequences, and autonomous session view arrangements without manual triggering.

Try this:
1. Select a clip in Session View. Open Clip View (double-click the clip). Go to the Launch panel.
2. Enable Follow Action by setting a time (bars/beats) and choosing an action from the Action A dropdown. Action B is the alternate — set a probability split between A and B using the Chance knob.
3. To loop within a group of clips: set all clips to Follow Action "Next" and set the last clip to "First" — the sequence loops automatically.
4. For randomised sequences: set all clips to Action A = "Any" (random). Each cycle picks a different clip in the group.
5. To chain clips that always run in order: set Action A = "Next", Chance A = 100%.
6. Clip groups are defined by position in a track — the Follow Action scope is all clips in the same track by default.
7. In Live 11+, you can set scenes as the scope instead of individual tracks for polyrhythmic sequencing.

Why it matters:
Follow Actions turn Session View into a generative playback engine. You can build 16-bar structures that evolve automatically, or set up probability-based loops that never repeat exactly.

Common mistakes:
- Setting a Follow Action time shorter than the clip loop length — the clip triggers a new clip before it finishes playing.
- Forgetting to set the last clip's Follow Action to "First" — the sequence stops after the last clip instead of looping.
- Using "Any" probability when you actually want a fixed order — use "Next" for ordered sequences.

When this does not apply:
Arrangement View clips do not have Follow Actions. Follow Actions are Session View only.

Related questions:
- How do I make clips loop automatically in Ableton Session View?
- How do I sequence clips without pressing play manually?
- What does Follow Action do in Ableton?
- How do I randomise clip playback in Ableton?
- How do I build a generative loop in Ableton?
