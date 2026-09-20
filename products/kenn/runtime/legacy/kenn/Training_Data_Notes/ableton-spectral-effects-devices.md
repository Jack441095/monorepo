# Ableton Spectral Effects Devices

Type: Ableton device workflow
Tags: ableton, spectral time, spectral resonator, spectral processing, delay, freeze, pitch tracking, midi sidechain, sound design
Status: Approved
Source: Ableton Live 12 Reference Manual (live12-manual-en.pdf)
Reviewed: 2026-07-06

Short answer:
Ableton's spectral suite includes Spectral Time and Spectral Resonator. These devices perform real-time Fast Fourier Transforms (FFT) to process audio as individual frequency bins. Spectral Time combines a spectral delay with a freeze function, while Spectral Resonator stretches and shifts frequencies to create metallic resonators, supporting MIDI sidechain routing for chordal playability.

Try this:
1. For Spectral Time: place it on a vocal track or melodic instrument. Use the Tilt and Spray controls to offset the delay times of different frequencies, transforming a simple sound into a lush, scattered ambient cloud.
2. Trigger the Freeze button: use manual mode to capture a slice of audio and hold it indefinitely as a pad, or set it to Auto mode to freeze whenever the input level exceeds a threshold.
3. Adjust FFT Resolution: set to higher bin sizes for smooth, high-fidelity ambient clouds, or lower sizes for metallic, glitchy, or robotic textures.
4. For Spectral Resonator: insert it on percussion loops or white noise to turn them into melodic instruments.
5. Enable MIDI input: click the MIDI button in the device header, select a MIDI track as the input source, and play notes or chords on that MIDI track to automatically shift the resonance frequencies of the audio track to match.
6. Set the Unison voices (up to 8) and adjust Pitch and Decay to control the stereo width, detuning, and decay length of the resonant harmonics.

Why it matters:
Spectral processing opens up entirely new sound-design possibilities. Instead of processing the sound as a single waveform, these devices let you freeze, delay, and tune individual frequency components, turning simple percussion hits or vocal noise into melodic pads and synth chords.

Common mistakes:
- Running too many spectral devices simultaneously, as the FFT calculations can cause high CPU loads. If needed, freeze/flatten the tracks.
- Setting the decay time too long on Spectral Resonator when playing fast chord changes, resulting in a muddy overlap of notes.

When this does not apply:
- Standard mixing tasks where simple utility delays, standard EQs, or transparent compression are required.

Related questions:
- How do I use MIDI sidechaining with Spectral Resonator?
- What does the Freeze control do in Spectral Time?
- How do I adjust the FFT resolution in Ableton spectral devices?
- How do I create ambient pads from percussion using Spectral Time?
