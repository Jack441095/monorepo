# Operator FM Synthesis Basics

Type: Sound design workflow
Tags: operator, fm synthesis, ableton, oscillator, algorithm, modulator, carrier, ratio, envelope, fm bass, bell, pad
Status: Approved
Source: Ableton Live 12 Manual
Reviewed: 2026-07-01

Short answer:
Operator uses four oscillators (A–D) in FM configurations called algorithms. A carrier oscillator produces sound you hear; a modulator oscillator controls the carrier's pitch, creating sidebands and harmonic complexity. The Amount knob on a modulator sets how much it changes the carrier — higher values add more harmonics and brightness.

Try this:
1. Start with Algorithm 1 (single carrier, three modulators in series). Lower all modulator Amounts to zero, then raise them one at a time to hear what each adds.
2. For an FM bass: set oscillator A as carrier (sine wave), B as modulator (sine), ratio B = 1, Amount B = low. Reduce the envelope decay on B so modulation fades quickly — gives a punchy transient that settles into a clean sub.
3. For a bell: use a 2-carrier algorithm. Set both carriers to sine. Set a modulator ratio to 3.5 or 7.0 (non-integer ratios produce inharmonic partials that sound metallic). Long decay on both carriers.
4. Ratio sets the modulator's frequency as a multiple of the note pitch. Integer ratios (1, 2, 3) stay harmonic. Non-integer ratios (1.41, 3.5) sound metallic or glassy.
5. Use the Pitch Envelope on a modulator for attack transients — a fast envelope sweeps FM depth at note-on, creating a click or pluck before the sustain tone.
6. The Filter section is post-FM. Use sparingly for colour; the character comes from the oscillator configuration.

Why it matters:
FM synthesis creates harmonics without filters. You can build sounds from simple sine waves that would need heavy processing to achieve with subtractive synthesis — especially metallic, glassy, or plucky tones.

Common mistakes:
- Setting modulator Amount too high — FM becomes noisy rather than harmonic when sidebands overlap.
- Using complex algorithms before understanding simple carrier/modulator pairs — start with two oscillators.
- Ignoring the Coarse and Fine ratio controls — small ratio changes dramatically change the timbre.

When this does not apply:
For warm, filter-driven sounds, subtractive synthesis (Analog or Wavetable) is more intuitive. FM excels at metallic, digital, and transient-rich textures.

Related questions:
- How does FM synthesis work in Ableton Operator?
- How do I make an FM bass in Operator?
- What is the ratio knob in Operator?
- How do I make a bell sound in Operator?
- What is the difference between a carrier and a modulator in Operator?
