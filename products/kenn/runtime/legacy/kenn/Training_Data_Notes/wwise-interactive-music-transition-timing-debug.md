# Wwise Interactive Music Transition Timing Debug

Type: Game audio troubleshooting workflow
Tags: wwise, ableton, game audio, interactive music, music segment, transition, transition segment, stinger, beat, bar, grid, bpm, sync, combat music, late, off beat, audiokinetic
Status: Approved
Source title: Wwise Help 2025.1.4 - Creating interactive music; Wwise 101
Source creator: Audiokinetic
Source URL: https://www.audiokinetic.com/en/library/edge/

Short answer:
If a Wwise music transition is late, early, or off-beat, check musical metadata before rewriting the mix. Confirm BPM, bar length, segment boundaries, entry and exit cues, transition rules, stingers, and whether the game changes State early enough for the next musical sync point.

Try this:
1. Export Ableton stems with exact bar starts, matching length, and no hidden pickup silence unless it is intentional.
2. Confirm each music segment has the correct tempo, time signature, and grid.
3. Place entry and exit cues where the music should actually connect, not just at the visible file start and end.
4. Set transition rules around musical sync points such as immediate, next beat, next bar, or next grid according to the design.
5. If combat music arrives too late, ask whether the game State is sent late or whether Wwise is waiting for the next bar by design.
6. If the transition flams or doubles, check whether a stinger, transition segment, or old layer is overlapping the new segment.
7. Profile the State or Switch change and music transition while reproducing the gameplay moment.
8. Re-import the rendered stems into Ableton and test the loop or transition against the same BPM grid.

Check:
Do not fix timing by nudging random audio files until the Wwise music rules are understood. A late transition may be correct if the rule waits for the next bar.

Why it matters:
Interactive music bugs sit between Ableton arrangement, Wwise music metadata, and game timing. KENN should diagnose all three instead of saying only "export tighter stems."

Related questions:
- My Wwise combat music transition is late.
- Why is my Wwise stinger off beat?
- How do I prepare Ableton stems for bar-accurate Wwise transitions?
