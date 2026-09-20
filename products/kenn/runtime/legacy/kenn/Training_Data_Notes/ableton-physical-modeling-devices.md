# Ableton Physical Modeling Instruments and Effects

Type: Ableton device workflow
Tags: ableton, collision, corpus, electric, tension, physical modeling, resonator, string, mallet, tine, sound design
Status: Approved
Source: Ableton Live 12 Reference Manual (live12-manual-en.pdf)
Reviewed: 2026-07-06

Short answer:
Ableton's physical modeling suite includes Collision (mallet/resonator synth), Corpus (resonant acoustic filter), Electric (classic Rhodes/Wurlitzer tine modeler), and Tension (acoustic string modeler). Rather than playing samples, these devices use mathematical models to simulate physical interactions like hammer strikes, string tension, and pipe resonances.

Try this:
1. For Collision: choose a mallet exciter type and adjust the Stiffness and Noise parameters to change the strike transient click.
2. Select Resonator 1 type (Beam, Marimba, String, Membrane, Plate, Pipe, or Tube) and adjust the Decay, Material (wooden vs. metallic), and Radius controls to shape the body resonance.
3. For Corpus: place it on an audio track (such as a snare drum or dry synth). Choose a resonator type, set the Tune to match your song's key, and adjust Decay to ring out a physical pitch on every hit.
4. For Electric: adjust the Hammer parameters (hardness and noise) and the Tine settings (decay and decay modulation) to morph from a soft, warm Wurlitzer tone to a bright, bell-like Rhodes bark.
5. For Tension: set the Exciter to Pluck, Bow, or Hammer, and adjust the String properties (Damp, Decay, Inharmonicity) to emulate organic acoustic guitars, harps, violins, or cellos.

Why it matters:
Physical modeling provides organic, realistic acoustic behaviors that sample libraries cannot duplicate. Because the instruments calculate resonances in real time, parameters like string dampening, hammer hardness, and tine decay respond dynamically to MIDI velocity and modulation wheel changes.

Common mistakes:
- Over-resonating Collision or Corpus (high Decay and high Resonator gain), which can cause feedback peaks that distort the channel.
- Setting decay too long on low notes, which can build up muddy low frequencies.

When this does not apply:
- Standard subtractive analog synthesis or digital wavetable sweeps (use Drift or Wavetable instead).

Related questions:
- What is the difference between Collision and Corpus?
- How do I design acoustic guitar sounds using Tension?
- How do I change the harmonic timbre of Electric?
- What are the resonator types in Collision?
