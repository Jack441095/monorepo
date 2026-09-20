# Ableton Pitch and Note Length MIDI Effects

Type: Ableton device workflow
Tags: ableton, midi effects, pitch, note length, transposition, octaves, key scale, gate time, trigger, release trigger
Status: Approved
Source: Ableton Live 12 Reference Manual (live12-manual-en.pdf)
Reviewed: 2026-07-06

Short answer:
Pitch and Note Length are classic MIDI processing devices. Pitch transposes incoming MIDI notes in semitones or octaves, clamping them to custom upper and lower ranges. Note Length adjusts the duration of MIDI notes, allowing you to force a constant note length, scale note lengths dynamically with velocity, or trigger notes on the release of a key.

Try this:
1. For Pitch: place it before your virtual instrument. Use the Pitch dial to transpose incoming notes in semitones (e.g., +12 for one octave up, or -5 for a fourth down).
2. Set Range and Lowest parameters: define a specific range of active MIDI notes. Notes falling outside this range are blocked, letting you build manual key-splits on MIDI tracks.
3. For Note Length: place it before your instrument. Set the Mode switch to Trigger (sends note-on messages) or Release (sends note-on only when a keyboard key is released, ideal for harpsichord or decay emulation).
4. Set Length in milliseconds or sync it to the song's tempo (e.g., 1/16 or 1/8) to force all incoming notes to a specific duration.
5. Adjust the Gate parameter: values below 100% shorten the notes (staccato), and values above 100% extend them (legato).
6. Tune the Vel Scale slider: map velocity to note length so that hitting a key harder generates a longer note.

Why it matters:
These MIDI effects are valuable tools for live playing and generative composition. Pitch is ideal for instant octave transpositions or key limits, while Note Length lets you design mechanical staccato sequences, pad triggers on key release, or custom synth envelopes that scale dynamically with velocity.

Common mistakes:
- Placing Pitch after the virtual instrument, which has no effect since instruments output audio, not MIDI.
- Forgetting to turn off Note Length sync when aiming for precise millisecond triggers, resulting in timing offsets if the song tempo shifts.

When this does not apply:
- Standard audio tracks, as these devices only process MIDI data.

Related questions:
- How do I transpose MIDI tracks in Ableton?
- How do I make notes trigger when I release a key in Ableton?
- How do I scale note length with velocity in Ableton?
- What does the Gate control do in Ableton Note Length?
