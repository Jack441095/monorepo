# Ableton MIDI Effects Devices

Type: Ableton device workflow
Tags: ableton, midi effects, arpeggiator, chord, scale, random, velocity, routing, creative composition
Status: Approved
Source: Ableton Live 12 Reference Manual (live12-manual-en.pdf)
Reviewed: 2026-07-06

Short answer:
Ableton's MIDI effects process MIDI note data before it reaches an instrument. Key devices include Arpeggiator (splits chords into rhythmic sequences), Chord (adds harmonizing pitches), Scale (clamps notes to a key), Random (adds controlled pitch variation), and Velocity (maps or randomizes note velocities).

Try this:
1. For Arpeggiator: insert it before a virtual instrument. Choose a Style (Up, Down, Converge, Random) and set the Rate (e.g., 1/16) to generate rhythmic note patterns from held chords.
2. Use the Steps and Distance parameters to sweep the pattern across multiple octaves (e.g., 2 steps of 12 semitones to shift up one octave).
3. For Chord: place it before your instrument. Use the Shift dials to add harmonizing notes (e.g., Shift 1 at +3 semitones, Shift 2 at +7 semitones to automatically generate minor triads).
4. For Scale: place it after Chord or Arpeggiator. Choose a scale key and type (like C Minor), forcing any incoming notes (including those shifted by Chord) to clamp to the nearest in-key semitone.
5. For Random: place it before Scale. Set the Chance slider to 20–40% and Choices to 12. This randomly shifts incoming notes by set intervals, which Scale then clamps back to the target key, generating automated, musical variations.
6. For Velocity: place it first in the chain. Adjust the Random control to add subtle velocity variations (humanization) to mechanical MIDI patterns.

Why it matters:
MIDI effects are powerful tools for creative writing and live performance. They allow you to generate complex chord progressions, build auto-arpeggiating sequences, ensure you never play a wrong note, and humanize robotic MIDI sequences before they enter your instruments.

Common mistakes:
- Placing Scale *before* Chord or Arpeggiator. If the chord shifts notes out of key, they will not be corrected. Always place Scale after devices that shift pitch.
- Leaving Random Chance too high without a Scale device, which creates chaotic, out-of-key note structures.

When this does not apply:
- Standard audio channels, since MIDI effects only process MIDI notes and do not output sound directly.

Related questions:
- How do I keep my arpeggiator in key using Ableton MIDI effects?
- What order should Ableton MIDI effects be placed in?
- How do I use the Chord device to play triads?
- How do I humanize MIDI drum patterns in Ableton?
