# Wavetable Sound Design Basics

Type: Sound design workflow
Tags: wavetable, ableton, oscillator, morph, sub, unison, filter, lfo, modulation, sound design
Status: Approved
Source: Ableton Live 12 Manual
Reviewed: 2026-07-01

Short answer:
Wavetable is Ableton's wavetable synthesiser. Each oscillator scans through a table of single-cycle waveforms. Moving the Position knob morphs between waveforms in the table — this is the main tonal character control. Stacking two oscillators with different tables, tuning, and positions gives you the full sound before any filter or effects.

Try this:
1. Start with one oscillator. Pick a table in the Category browser (Basic Shapes for clean, Analog for grit, Noise for texture).
2. Move the Position knob while holding a note to hear the morph range across the table.
3. Add modulation: assign an LFO to Position with a slow rate for movement, or an Envelope to Position with high Sustain and a quick attack for an animated attack transient.
4. For sub bass: set Osc 2 to Sine, tune it down an octave, keep its level low, and keep it completely dry. No filter, no unison.
5. Unison adds multiple detuned voices per note — use it sparingly on leads and pads; avoid it on bass as it causes mono compatibility issues.
6. The Filter section is post-oscillator. Use a 24 dB LP for aggressive cuts, 12 dB LP for gentler rolls. Modulate Cutoff with Env 2 for a classic attack pluck shape.
7. Reduce Poly to 1 for monophonic leads with portamento.

Why it matters:
Position modulation is Wavetable's signature move. Morphing through a table in real time gives smooth, organic texture change that a static waveform can't do.

Common mistakes:
- Leaving Unison on both oscillators and a bass layer — mono sum collapses.
- Modulating Position too fast so you get aliasing noise rather than motion.
- Forgetting to check the output level with the built-in gain knob before the signal hits the chain.

When this does not apply:
For sampled instruments or acoustic emulations, Simpler or Sampler will feel more natural than Wavetable.

Related questions:
- How do I use Wavetable in Ableton?
- How do I make a moving pad with Wavetable?
- What does the Position knob do in Wavetable?
- How do I add sub bass with Wavetable?
- Should I use Unison on bass in Wavetable?
