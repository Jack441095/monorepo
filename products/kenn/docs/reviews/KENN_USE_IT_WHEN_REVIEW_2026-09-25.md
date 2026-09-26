# "Use it when…" lines for KENN's Ableton notes: review

**Drafted:** 2026-09-25 on the GPU notes model (`kenn-notes-qwen3-4b-gpu1`) · **Status:** waiting for Jack's review

Each line is added to its note so KENN can find the note when a producer describes what they want instead of naming
the device. The model saw only the note itself, never the test questions.

**How to review:** tick the box for each line you're happy with. Edit a line in place if it's nearly right, or
delete a line you don't want. Only ticked lines go into KENN's notes, at the next index rebuild.

**Measured effect (all 114 lines, in a throwaway index; the real index is untouched):**

| Questions | Without | With |
|---|---|---|
| 125 describe-it questions (recall@4) | 0.744 | **0.760** |
| same, ranking (MRR) | 0.605 | **0.626** |
| 128 original questions (recall@4) | 0.983 | 0.983 |

A small gain, and nothing got worse. What to look for: some lines miss the everyday situation (Align Delay's line is
about syncing to video, but producers mostly use it to line up mics), and a few are generic ("add movement to a
track"). Sharper lines should help more than more lines.

## Second round, 26 Sept: sharper lines

Under each drafted line there is now a second, sharper one written by Claude in producer language (Align Delay's is
about lining up mics; Redux's says "bitcrush" and "8 bit"). Tick either, both or neither.

To test them fairly, Qwen3 8B on the box wrote a new sealed set first: two questions per note, from the note alone,
in everyday words without naming the device (228 questions). Recall@4, measured in memory (the index is untouched):

| Lines | Original 58 | Describe-it 125 | Sealed 228 |
|---|---|---|---|
| None (today) | 0.983 | 0.744 | 0.338 |
| Drafted (4B) | 0.983 | 0.760 | 0.417 |
| Sharper (Claude) | 0.983 | 0.904 | 0.386 |
| **Both** | 0.983 | 0.880 | **0.447** |

Read the middle column with care: Claude wrote those 125 questions and had seen which ones missed, so its lines look
better there than they are. The sealed set is the fair test, and there the two kinds of line help most together.
The sealed set is harsh: many of its questions are general mixing problems ("my drum tracks have low-end rumble")
that several notes answer well, but only the note the question was written from counts. Nothing got worse anywhere.

## Lines (114)

- [ ] **Ableton Live 12 Accessibility and Keyboard Navigation** (`ableton-accessibility-and-navigation.md`)
      Use it when: you need to navigate controls without a mouse; you're adjusting parameters on the fly; you're managing multiple clips in Session View; you're editing in the Arrangement View; you're using a screen reader to follow feedback.
      - [ ] Sharper line: Use it when: you want to drive Live from the keyboard instead of the mouse, move between tracks, devices and clips with shortcuts, or use Live with a screen reader.
- [ ] **Ableton Align Delay (Audio Effect)** (`ableton-align-delay-device.md`)
      Use it when: you need to sync audio with video; fix timing issues from latency; adjust for physical distance in a live setup; correct mismatched audio cues in a mix; align vocal and instrumental tracks precisely.
      - [ ] Sharper line: Use it when: two mics on the same source are a few milliseconds out of time and sound thin or phasey; you need to delay one track by milliseconds or samples to line it up with the others; a bass DI and amp mic don't line up.
- [ ] **Ableton Amp (Audio Effect)** (`ableton-amp-device.md`)
      Use it when: you need more warmth in your bass; your guitars lack character; you want to add grit to a vocal track; your synth sounds flat; you're trying to make a drum hit more punchy.
      - [ ] Sharper line: Use it when: you want a guitar amp sound on a DI guitar or bass; a synth or vocal needs gritty amp character; you want crunch or overdrive like a real amplifier.
- [ ] **Ableton Analog and Impulse Instruments** (`ableton-analog-and-impulse-instruments.md`)
      Use it when: you need to add warmth and character to a synth lead; your drums lack punch and definition; you want to create a dynamic, evolving bass line; your samples sound flat or lifeless; you're looking to shape sound with filters and envelopes without heavy processing.
      - [ ] Sharper line: Use it when: you want a classic subtractive synth sound or a quick eight-slot drum kit from samples.
- [ ] **Ableton Analog Synthesizer** (`ableton-analog-synth.md`)
      Use it when: you need a warm, rich bass; you want a punchy, moving lead; you're shaping a classic synth pad; you're trying to add depth with detuned layers; you're looking to create vibrato or filter movement.
      - [ ] Sharper line: Use it when: you want a warm classic analog-style bass, lead or pad with two oscillators and filters.
- [ ] **Ableton Arpeggiator MIDI Effect** (`ableton-arpeggiator.md`)
      Use it when: you need to turn a chord into a rhythmic melody; your synth lacks movement and energy; you want to add melodic interest to a bassline; your patterns feel static and uninteresting; you're looking for a quick way to generate a catchy synth line.
      - [ ] Sharper line: Use it when: you want held chords to play as a rolling pattern of single notes; you want notes to cycle up and down in time.
- [ ] **Ableton Audio Effect Rack (Rack)** (`ableton-audio-effect-rack-device.md`)
      Use it when: you need to organize multiple effects, your signal flow is getting complicated, you want to control effects with macros, you're trying to isolate specific chains for processing, or you're setting up parallel effects for different parts of the mix.
      - [ ] Sharper line: Use it when: you want to group several effects into one device, run effects in parallel, split a sound into bands, or control many knobs with one macro.
- [ ] **Ableton Live Audio Fact Sheet and Summing Engine** (`ableton-audio-fact-sheet-neutral-operations.md`)
      Use it when: you need neutral playback, want to avoid audible artifacts, are mixing without warping, are rendering at 32-bit, or are exporting to 16-bit without dithering.
      - [ ] Sharper line: Use it when: you want to know whether Live changes your audio when nothing is applied, how Live sums tracks, or whether exporting at 16 or 24 bit adds anything.
- [ ] **Ableton Auto Filter Device** (`ableton-auto-filter-device.md`)
      Use it when: you want to add movement to a synth, create dynamic auto-wah on a drum loop, shape a rhythmic filter pattern, sweep a pad's cutoff with transients, or add stereo width to a melody line.
      - [ ] Sharper line: Use it when: you want a filter sweep, a resonant low pass that opens and closes on its own, a wah or wobble, or a filter that follows how loud the sound is.
- [ ] **Ableton Auto Pan-Tremolo Modulation** (`ableton-auto-pan-device.md`)
      Use it when: you want to add movement to a sustained synth, create rhythmic gating on a drum loop, need a subtle stereo width on a pad, want to simulate a sidechain pump without clicks, or try to add dynamic depth to a vocal track.
      - [ ] Sharper line: Use it when: you want a sound to move between the left and right speakers in time, a tremolo that pulses the volume, or a choppy gated effect.
- [ ] **Ableton Auto Pan-Tremolo (Audio Effect)** (`ableton-auto-pan-tremolo-device.md`)
      Use it when: you need to add movement to a track; your synth lacks depth; you want to make a vocal sound more spatial; your rhythm is too flat; you're trying to create a lush, evolving atmosphere.
      - [ ] Sharper line: Use it when: you want a sound to bounce between left and right in time with the song, a rhythmic volume chop, or a tremolo pulse.
- [ ] **Ableton Auto Shift Real-Time Pitch and Formant Correction** (`ableton-auto-shift-device.md`)
      Use it when: you need to fix out-of-tune vocals; you want to add harmonies on the fly; you're trying to make a vocal sound more modern and sharp; you're adjusting vocal timbre without changing pitch; you're syncing vocal performance to a song's key.
      - [ ] Sharper line: Use it when: you want to pitch correct or autotune a vocal, snap singing to a scale, get a hard robotic tune effect, or change the formant.
- [ ] **Ableton Beat Repeat** (`ableton-beat-repeat.md`)
      Use it when: you need quick drum fills, want to add glitchy transitions, are looking for a vocal stutter, need a rhythmic fill in a song, or want to create a sudden audio break in a track.
      - [ ] Sharper line: Use it when: you want glitchy stutter repeats, vocal chops repeating at the end of a phrase, or random buffer-repeat fills on drums.
- [ ] **Ableton Live 12 Bounce to Audio Workflow** (`ableton-bounce-to-audio-workflow.md`)
      Use it when: you need to capture processed audio for reuse; you want to isolate a track’s sound from the mixer; you’re preparing a final mix for export; you’re making variations of a section without affecting the original; you’re working with group tracks and need to bounce post-mixer.
      - [ ] Sharper line: Use it when: you want to commit a MIDI or effects track to audio, render a track in place, or turn a synth part into a waveform you can edit and chop.
- [ ] **Ableton Cabinet Speaker Emulation** (`ableton-cabinet-device.md`)
      Use it when: your guitar sounds harsh or thin; your bass lacks punch; you need more warmth in a synth lead; your drums feel flat; you want to add room ambiance without muddying the mix.
      - [ ] Sharper line: Use it when: you want a guitar speaker cabinet and mic sound after an amp, or to take the fizz off distorted DI guitars.
- [ ] **Ableton CC Control MIDI Modulation** (`ableton-cc-control-midi-effect.md`)
      Use it when: you need to control hardware synths with named parameters; you want to automate filter cutoff or envelope shapes; you're trying to match physical knob labels to Live controls; you're sending CC messages to external gear without conflicting with pitch or sustain; you're setting up multiple synth templates for quick switching.
      - [ ] Sharper line: Use it when: you want a clip to send MIDI CC messages to external gear or a plugin, or automate controller knobs from Live.
- [ ] **Ableton Channel EQ Simplified Tonal Shaping** (`ableton-channel-eq-device.md`)

      - [ ] Sharper line: Use it when: you want a quick simple EQ with low, mid and high like a mixing desk channel, without fiddly bands.      Use it when you need to add warmth to vocals; clean up sub-bass rumble; boost clarity on cymbals; tame boxiness in synth leads; or shape a track's overall character quickly.
- [ ] **Ableton Chorus-Ensemble Spatial Modulation** (`ableton-chorus-ensemble-device.md`)
      Use it when: you want to add thickness and width to guitars, synths, or vocals; need vintage shimmer or rich, textured modulation; are trying to keep bass tight while adding stereo depth.
      - [ ] Sharper line: Use it when: you want to thicken and widen a synth pad or guitar, make a sound richer with modulated copies, or get a vintage chorus or ensemble shimmer.
- [ ] **Ableton Live Clip Envelopes and Modulation** (`ableton-clip-envelopes-and-modulation.md`)
      Use it when: you want to add subtle pitch variations to a vocal sample; you need to modulate the filter cutoff of a synth sustain; you're trying to shape the dynamics of a drum hit; you're adjusting the pan position of a melody line; you're adding expression to a MIDI performance.
      - [ ] Sharper line: Use it when: you want automation that lives inside a clip and loops with it instead of on the timeline, or to modulate a clip's pitch, volume or sends per clip.
- [ ] **Clip Envelopes In Ableton** (`ableton-clip-envelopes.md`)
      Use it when: you want to change the volume, filter, or effects of a clip without affecting others; you need to make a sound fade in or out with each loop; you're trying to vary the pitch or pan on different parts of a loop; you want to add a rhythmic modulation that syncs with the clip's timing; you need to adjust reverb or delay levels per clip in a layered arrangement.
      - [ ] Sharper line: Use it when: you want automation that belongs to one clip rather than the arrangement timeline, or changes that repeat every time the clip loops.
- [ ] **Ableton Collision Physical Modeling Synthesizer** (`ableton-collision-synth.md`)
      Use it when: you need organic metallic sounds like mallets on marimba; you want to simulate real-world percussion with dynamic velocity response; you're designing complex resonant textures like struck pipes or plates; you're looking for tactile, non-repetitive acoustic hits; you want to avoid sample-based synth sounds for more physical realism.
      - [ ] Sharper line: Use it when: you want mallet, marimba, bell or struck-metal sounds, or percussive plucked tones from physical modeling.
- [ ] **Ableton Live Comping and Take Lanes** (`ableton-comping-and-take-lanes.md`)
      Use it when: you need to capture multiple performances, select the best parts for a comp, audition different takes, copy the best sections to the main lane, or smooth transitions between recorded parts.
      - [ ] Sharper line: Use it when: you recorded several vocal or guitar takes and want to pick the best bits from each into one final take.
- [ ] **Ableton Compressor Device** (`ableton-compressor-device.md`)
      Use it when: you need to even out vocal levels, control drum transients, or smooth out a synth's dynamic range; your track feels too loud or too quiet in parts; you want to make sure the kick drum cuts through the mix without clashing with other elements; you're trying to add punch to a snare or bass without losing clarity; you're dealing with a signal that has inconsistent volume over time.
      - [ ] Sharper line: Use it when: you want to even out a vocal or bass that jumps in level, control peaks, add punch, or duck one sound when another plays with sidechain.
- [ ] **Ableton Live Converting Audio to MIDI** (`ableton-converting-audio-to-midi.md`)
      Use it when: you need to extract melodies, harmonies, or drum patterns from audio to work with in MIDI for arrangement or editing; you want to turn a vocal line or instrument into playable notes; you're trying to isolate and manipulate rhythmic elements like kicks and snares; you're converting a complex performance into editable MIDI data for remixing or resequencing; you're working with warped audio and want to preserve timing changes in the converted MIDI.
      - [ ] Sharper line: Use it when: you want to turn a recorded drum loop, melody, humming or chords into MIDI notes you can edit or play with another sound.
- [ ] **Ableton Corpus And Resonators** (`ableton-corpus-resonators.md`)
      Use it when: you want drums to have a melodic feel; your sounds lack body and warmth; you need a shimmer on hi-hats or shakers; you're trying to add harmonic interest to a rhythm; you're experimenting with tuned textures and evolving tones.
      - [ ] Sharper line: Use it when: you want a drum hit or noise to ring at a musical pitch, add metallic or tuned resonance, or make sounds resonate like a tube, plate or string.
- [ ] **Ableton Live CPU Management and Track Freezing** (`ableton-cpu-management-and-freezing.md`)
      Use it when: you need to reduce CPU load; your tracks are slowing down; you're struggling with latency; you want to free up resources; you're dealing with too many effects on a track.
      - [ ] Sharper line: Use it when: your set is crackling or the CPU meter is maxed out, and you want to freeze tracks or reduce the load.
- [ ] **Ableton CV Tools for Modular Synthesizer Integration** (`ableton-cv-tools-device-routing.md`)
      Use it when: you need to control hardware modular synths with precise pitch and gate signals, sync modular sequencers to your tempo, or modulate hardware filters with a custom LFO.
      - [ ] Sharper line: Use it when: you want to control a modular or Eurorack synth from Live with CV and gate signals.
- [ ] **Ableton Delay and Reverb Devices** (`ableton-delay-and-reverb-devices.md`)
      Use it when: you need to add depth to a vocal track; want to create a sense of space in a synth lead; are trying to make a drum hit feel more present; need to separate high frequencies for stereo imaging; struggle with muddy reverb in the low end.
      - [ ] Sharper line: Use it when: you want echoes or a sense of space and room on a sound, and want to choose between Live's delay and reverb devices.
- [ ] **Ableton Live Plugin Delay Compensation (PDC)** (`ableton-device-delay-compensation.md`)
      Use it when: your tracks are out of sync after using effects; you're monitoring input with latency issues; you're dealing with multiple devices causing delay; you need to record with precise timing; you're adjusting sync in complex setups.
      - [ ] Sharper line: Use it when: tracks drift out of time after adding plugins, recorded parts sound late, or you want to understand plugin latency.
- [ ] **Ableton Drift and Meld Synthesizers** (`ableton-drift-and-meld-synths.md`)
      Use it when: you need organic warmth in a synth lead; your pads lack depth and character; you're trying to create evolving ambient textures; your drums sound thin and lifeless; you want to add subtle imperfections to mimic analog behavior.
      - [ ] Sharper line: Use it when: you want a simple warm synth for quick basses, leads and pads, or a two-engine synth for evolving textures.
- [ ] **Ableton Drift Synthesizer** (`ableton-drift-synth.md`)
      Use it when: you need warmth and character in your sounds; your synth lacks organic movement; you want to emulate vintage hardware; your patches feel too precise and lifeless; you're looking for subtle imperfections and drift in your melodies.
      - [ ] Sharper line: Use it when: you want a lightweight analog-flavoured synth for fat basses, drifting leads and pads without heavy CPU.
- [ ] **Ableton Drum Buss and Beat Repeat Devices** (`ableton-drum-buss-and-beat-repeat.md`)
      Use it when: you need to add warmth and punch to a drum group; you're trying to glue together drum transients; you want to create rhythmic variations with loops; you're looking for a subtle sub-bass boost; you need dynamic pitch shifts in a beat repeat.
      - [ ] Sharper line: Use it when: you want to add weight, punch, drive and low-end boom to a drum group with one device, or glitchy stutter repeats.
- [ ] **Ableton Live Drum Racks and Internal Routing** (`ableton-drum-racks-and-internal-routing.md`)
      Use it when: you need to route drum sounds to separate channels for effects; you want to trigger multiple sounds with one MIDI note; you're trying to keep your drum kit clean in the mix; you're dealing with conflicting sounds from overlapping MIDI notes; you want to apply stereo effects to specific drum elements.
      - [ ] Sharper line: Use it when: you want to build a drum kit on pads, give each drum its own effects, or route a kick and snare to separate outputs.
- [ ] **Ableton Drum Sampler One-Shot Workflow** (`ableton-drum-sampler-device.md`)
      Use it when: you need a punchy kick, a tight snare, or a clear hi-hat with no extra noise; your samples have pre-transient dead space or lack sub-bass; you want to shape the attack of a drum without affecting the sustain.
      - [ ] Sharper line: Use it when: you want to play one-shot drum samples with quick tone, pitch and envelope shaping on a pad.
- [ ] **Ableton Dynamic Tube Warmth and Asymmetric Drive** (`ableton-dynamic-tube-device.md`)

      - [ ] Sharper line: Use it when: you want warm tube saturation that responds to how loud the sound is, or gentle analog-style colour.      Use it when you need warmth on vocals, want punch on synth leads, struggle with thin drums, need smooth harmonic richness on acoustic instruments, or want dynamic compression on transient-heavy tracks.
- [ ] **Ableton Echo Device** (`ableton-echo-device.md`)
      Use it when: you need to add depth to a vocal track; you want to create a wide, stereo delay effect; you're trying to build a dub-style delay with warmth; you're looking for a dynamic, evolving delay tail; you want to add analog character and tape noise to a sound.
      - [ ] Sharper line: Use it when: you want a vintage tape or analog style delay, echoes that duck so the repeats sit behind a vocal, or dub delays with character and wobble.
- [ ] **Ableton Live MPE Editing and Expression Control** (`ableton-editing-mpe.md`)
      Use it when: you need to shape the feel of each note in a polyphonic performance; you're trying to make a melody more expressive and dynamic; you want to adjust how notes bend or slide in real time; you're editing after a performance to refine pressure and velocity curves; you're working with MPE instruments and want precise control over per-note parameters.
      - [ ] Sharper line: Use it when: you want per-note pitch bends, slides and pressure in a clip, or to edit expression recorded from an MPE controller.
- [ ] **Ableton Electric (Instrument)** (`ableton-electric-device.md`)
      Use it when: you need to add warmth and realism to a piano sound; your chords lack depth and fullness; you're trying to make the attack more natural and dynamic; the sustain is too short or too long; the noise during the attack and release feels flat or lifeless.
      - [ ] Sharper line: Use it when: you want an electric piano sound like a Rhodes or Wurlitzer.
- [ ] **Ableton Envelope Follower (Audio Effect)** (`ableton-envelope-follower-device.md`)
      Use it when: you need to control a parameter with the volume of a track; you want to create a dynamic effect like auto-wah; you're trying to gate a sound with another track's signal; you're adjusting the intensity of a modulation based on audio input; you're shaping how a parameter responds to the rhythm of a song.
      - [ ] Sharper line: Use it when: you want the loudness of one sound to move a knob on another device, or a filter or effect that reacts to the level of a track.
- [ ] **Ableton Envelope MIDI (MIDI Effect)** (`ableton-envelope-midi-device.md`)
      Use it when: you need to shape dynamic changes in your sound; you want to control parameters with an ADSR envelope; you're trying to add expression to a performance; you're automating a parameter over time; you're looking to modulate effects or filters in real time.
      - [ ] Sharper line: Use it when: you want each MIDI note to trigger a shape that moves a parameter, like a filter opening on every note.
- [ ] **Ableton EQ Eight (Audio Effect)** (`ableton-eq-eight-device.md`)
      Use it when: you need to cut muddiness in a vocal track; your bass is too boomy in the mix; you want to brighten a dull synth; your drums lack punch in the midrange; and you're trying to make a sound sit better in the stereo field.
      - [ ] Sharper line: Use it when: you want to cut mud, boost or cut specific frequencies, notch out a ring, filter lows or highs, or cut just the side channel low end in mid-side mode.
- [ ] **Ableton EQ Three DJ Kill-EQ Workflow** (`ableton-eq-three-device.md`)
      Use it when: you need instant bass/mid/high cuts during drops; you're transitioning between tracks in a set; you want to isolate and boost specific frequency ranges on a DJ stem; you're preparing for a breakdown with a sudden frequency mute; you're trying to clean up a track by surgically removing problematic frequencies.
      - [ ] Sharper line: Use it when: you want DJ-style kill switches for lows, mids and highs, or to drop the bass out of a track completely.
- [ ] **Ableton Erosion Harmonic Degradation** (`ableton-erosion-device.md`)
      Use it when: you need to add sharp top-end grit to a dull bass, enhance snares with metallic presence, or inject harmonic sizzle into a dense mix.
      - [ ] Sharper line: Use it when: you want a degraded, digital, gritty or noisy texture, or a lo-fi broken sound.
- [ ] **Ableton Essential Audio Utilities and Coloration** (`ableton-essential-audio-utilities.md`)
      Use it when: you need to add width and movement to a track; you're trying to fix a tuning issue on a vocal or instrument; you want to inject grit and character into a drum loop or synth; you're looking to create a harmonized vocal effect; you're aiming for a vintage, warm sound with record-like imperfections.
      - [ ] Sharper line: Use it when: you want basic gain, phase, mono and colour tools for fixing and preparing audio.
- [ ] **Ableton Essential Workflow Hacks and Shortcuts** (`ableton-essential-workflow-hacks.md`)
      Use it when: you need to quickly hide or show tracks to focus on specific parts of your arrangement; you want to isolate a clip to edit without playing it; you're trying to find your most used plugins or instruments in the Browser; you're adjusting MIDI notes on the fly without using the wheel; you're organizing your session to keep it clean and easy to navigate.
      - [ ] Sharper line: Use it when: you want faster ways to work in Live: shortcuts, templates and time-saving tricks.
- [ ] **Ableton Expression Control (MIDI Effect)** (`ableton-expression-control-device.md`)
      Use it when: you need to control parameters with live performance inputs; you want to automate settings on the fly; you're trying to add expressive variation to a sound; you're mapping external controllers to effects or filters; you're adjusting modulation depth for a more organic feel.
      - [ ] Sharper line: Use it when: you want to turn velocity, aftertouch, mod wheel or pitch bend into movement on any parameter.
- [ ] **Ableton External Audio Effect Hardware Insert** (`ableton-external-audio-effect.md`)
      Use it when: you need to process audio through external analog gear; you're blending outboard effects with dry signals; you're trying to fix phase issues from hardware delays; you're routing to a physical mixer or outboard compressor; you're adjusting levels to avoid clipping or distortion.
      - [ ] Sharper line: Use it when: you want to use a hardware compressor, pedal or outboard effect inside a Live track as if it were a plugin.
- [ ] **Ableton External Instrument Hardware MIDI and Audio Routing** (`ableton-external-instrument.md`)
      Use it when: you need to play and record hardware synths or drum machines; you want to automate or freeze a live performance; you're dealing with MIDI and audio latency issues; you're routing audio from external gear into Live; you're trying to keep project organization simple and efficient.
      - [ ] Sharper line: Use it when: you want to play and record a hardware synth from Live, sending MIDI out and getting its audio back in.
- [ ] **Ableton Filter Delay Tri-Band Spatial Echo** (`ableton-filter-delay-device.md`)
      Use it when: you want to add depth to a vocal or synth by creating layered, frequency-specific echoes that sit in different parts of the mix; your main signal is too bright and needs a warm, low-mid delay to balance it; you're trying to make a drum hit feel more spatial without muddying the high-end; you need a delay that evolves in tone as it repeats; you're looking to add ambient texture without overwhelming the main sound.
      - [ ] Sharper line: Use it when: you want delays on separate low, mid and high bands, each panned and timed differently, for wide filtered echoes.
- [ ] **Ableton Follow Actions** (`ableton-follow-actions.md`)
      Use it when: you want clips to play in sequence; you need random variations in a pattern; you're building a song structure without Arrangement View; you're setting up a live performance loop; you want to automate transitions between tracks.
      - [ ] Sharper line: Use it when: you want clips to trigger the next clip automatically, play in random order, or make a set that evolves on its own.
- [ ] **Ableton Wwise One-Shot SFX Asset Prep** (`ableton-game-audio-asset-prep.md`)
      Use it when: you need clean one-shots for Wwise Events, want seamless loops for ambient spaces, are preparing stems for music layers, have to trim tails carefully for precise timing, or need clear metadata for asset organization.
      - [ ] Sharper line: Use it when: you are exporting one-shot sound effects for a game engine and want clean starts, ends and levels.
- [ ] **Ableton Glue Compressor Device** (`ableton-glue-compressor-device.md`)
      Use it when: you need to glue together a dense mix; your drums and vocals are fighting for space; you want tighter dynamics on a group of tracks; your master bus feels flat or unbalanced; you're looking for analog warmth without over-compressing.
      - [ ] Sharper line: Use it when: you want analog-style bus compression that glues a drum group or mix together, like a classic console compressor.
- [ ] **Ableton Grain Delay (Audio Effect)** (`ableton-grain-delay-device.md`)
      Use it when: you need to add texture to a synth pad; you want to create rhythmic patterns with delayed sounds; you're trying to make a vocal track feel more spatial; you're looking for a subtle echo that doesn't muddy the mix; you want to experiment with pitch-shifted delays for a warped effect.
      - [ ] Sharper line: Use it when: you want a granular delay with pitch shifting and randomisation for shimmering or glitchy textures.
- [ ] **Ableton Hybrid Reverb Dual Engine** (`ableton-hybrid-reverb-device.md`)
      Use it when: you need realistic room ambiance for vocals or instruments; want a lush, modulated tail for ambient textures; are mixing in a studio and need to avoid muddiness from low-end rumble; are blending acoustic and digital spaces for a hybrid reverb effect; want to maintain clear transients while adding depth and space.
      - [ ] Sharper line: Use it when: you want a big lush reverb, a real-room convolution space mixed with an algorithmic tail, or a shimmer or dark ambient reverb.
- [ ] **Ableton Hybrid Reverb** (`ableton-hybrid-reverb.md`)
      Use it when: you need a natural room reverb for vocals; want to add depth to ambient pads; are trying to create a shimmer effect on a melody; need a realistic cathedral sound for a choir; looking to blend digital and real space textures.
      - [ ] Sharper line: Use it when: you want a lush reverb that blends a real recorded space with a smooth algorithmic tail.
- [ ] **Ableton Instrument Rack (Rack)** (`ableton-instrument-rack-device.md`)
      Use it when: you need to organize multiple instrument or effect chains, simplify control with macro mappings, route signals efficiently, manage complex setups, or create custom device combinations for specific sounds or performances.
      - [ ] Sharper line: Use it when: you want to layer several synths on one track, split a keyboard, or control a whole instrument layer with macros.
- [ ] **Ableton Live Clip Launch Modes and Follow Actions** (`ableton-launching-clips-and-follow-actions.md`)
      Use it when: you need to trigger other clips automatically after your current one; you want to add variation or randomness to your sequence; you're trying to create a chain of events that flow smoothly; you're dealing with timing inconsistencies in a live performance; you want to control when follow actions happen relative to the main clip.
      - [ ] Sharper line: Use it when: you want to change how a clip starts when you launch it (trigger, gate, toggle, repeat) or chain clips automatically.
- [ ] **Ableton LFO (Audio Effect)** (`ableton-lfo-device.md`)
      Use it when: you want to add movement to a synth's filter; you're trying to make a vocal effect more dynamic; you need to vary the depth of a reverb over time; you're struggling with a dull synth sound; you want to create a pulsing rhythm effect.
      - [ ] Sharper line: Use it when: you want to wobble or sweep any knob automatically, modulate several parameters with a low frequency oscillator, or add slow movement.
- [ ] **Ableton Limiter and Gate Devices** (`ableton-limiter-and-gate-devices.md`)
      Use it when: you need to prevent clipping on master buses; you're cleaning up noise from vocal room ambiance; you want to control loud peaks in a mix; you're gating drum transients to avoid bleed; you're trying to keep a clean stereo image without losing width.
      - [ ] Sharper line: Use it when: you want to stop a bus or master clipping with a brickwall limiter, get it louder safely, or cut out background noise and bleed between hits with a gate.
- [ ] **Ableton Link Synchronization** (`ableton-link-sync.md`)
      Use it when: you need to keep multiple devices in time for a performance; you want to change tempo without stopping the session; you're syncing Live with a mobile app or another device; you're working with independent transport starts and stops; you're ensuring all peers follow the same beat and phase.
      - [ ] Sharper line: Use it when: you want Live to stay in time with another laptop, an app or a friend's setup over the network.
- [ ] **DJing And Live Performance With Ableton** (`ableton-live-djing.md`)
      Use it when: you need smooth transitions between tracks; you're beat-matching live performances; you want to automate crossfader movements for seamless fades.
      - [ ] Sharper line: Use it when: you want to DJ or perform live with Live: beatmatching, warping tracks and triggering sections.
- [ ] **Ableton Looper Device** (`ableton-looper-device.md`)
      Use it when: you need to record and layer live sounds on the fly; you want to build a loop that stays in time with your song; you're overdubbing extra parts without stopping the loop; you're trying to capture spontaneous ideas during a performance; you're syncing your loop to the beat instead of counting bars manually.
      - [ ] Sharper line: Use it when: you want to record and overdub live loops of guitar, vocals or beatbox like a loop pedal.
- [ ] **Ableton Looper Device** (`ableton-looper.md`)
      Use it when: you need to record and layer live sounds in real time; you want to build a complex arrangement on stage; you're overdubbing additional layers onto an existing loop; you're trying to create evolving, self-erasing textures; you're syncing loops to a tempo for a performance.
      - [ ] Sharper line: Use it when: you want a loop pedal inside Live to record, overdub and layer live loops.
- [ ] **Max For Live Basics** (`ableton-max-for-live-basics.md`)
      Use it when: you need to add texture to a track; you want to automate parameters with a smooth, rhythmic movement; you're looking for a way to control effects with audio dynamics instead of a compressor.
      - [ ] Sharper line: Use it when: you want to use or build Max for Live devices and understand what they can do.
- [ ] **Ableton Max for Live Overview** (`ableton-max-for-live-overview.md`)
      Use it when: you need to add custom sounds or effects that aren't available natively; you're trying to create unique modulation sources or interactive tools; you're dealing with complex signal processing that requires visual programming; you're looking for flexible, real-time adjustable instruments; you're building or modifying patches for specific sonic goals.
      - [ ] Sharper line: Use it when: you want an overview of Max for Live and the extra devices and tools it adds.
- [ ] **Ableton Max for Live Modulation Utilities** (`ableton-max-modulation-devices.md`)
      Use it when: you need to add rhythmic movement to filter cutoffs; want to vary synth parameters with keyboard velocity; are trying to create dynamic changes in reverb decay; need to randomize effects parameters for interest; or want to match drive levels to playing dynamics.
      - [ ] Sharper line: Use it when: you want modulators like LFOs, envelope followers or randomisers that move other device knobs.
- [ ] **Using MIDI Controllers With Ableton** (`ableton-midi-controller-setup.md`)
      Use it when: you need to play instruments live; you want to trigger clips without a mouse; you're trying to control synth parameters in real time; you're setting up a control surface for deep integration; you're having trouble with velocity or aftertouch settings.
      - [ ] Sharper line: Use it when: you want to set up a MIDI keyboard or controller, map its knobs to Live, or it isn't being detected.
- [ ] **Ableton MIDI Effect Rack Device** (`ableton-midi-effect-rack-device.md`)
      Use it when: you need to process different MIDI sounds separately; you want to switch between effects on the fly; you're trying to isolate specific notes for modulation; you're dealing with multiple layered MIDI instruments; you want to control different effects per note range.
      - [ ] Sharper line: Use it when: you want to combine MIDI effects, like a chord and an arpeggiator, into one device with macros.
- [ ] **Ableton MIDI Effects Devices** (`ableton-midi-effects-devices.md`)
      Use it when: you need to add rhythmic patterns from chords; you want to harmonize a melody with supporting notes; you're trying to keep a sequence in key; you're looking for subtle pitch variation in a MIDI line; you want to generate random but musical note shifts.
      - [ ] Sharper line: Use it when: you want to change notes before they reach an instrument: chords, arpeggios, scales, random notes or velocity.
- [ ] **Ableton Live MIDI Fact Sheet and Timing** (`ableton-midi-fact-sheet-timing-jitter.md`)
      Use it when: your MIDI recordings sound out of sync; you're experiencing timing issues with hardware synths; you need consistent playback speed; your drum patterns feel loose; you're trying to fix jitter in live performances.
      - [ ] Sharper line: Use it when: your MIDI timing feels late or loose, or you want to understand MIDI latency and jitter in Live.
- [ ] **Ableton MIDI Monitor (MIDI Effect)** (`ableton-midi-monitor-device.md`)
      Use it when: you need to see what notes and velocities are being sent to an instrument; you're troubleshooting a MIDI setup; you want to understand how a performance is being translated into MIDI messages; you're trying to capture a specific moment of playing; you're working with MPE and need to check polyphonic aftertouch data.
      - [ ] Sharper line: Use it when: you want to see which notes, velocities and CC messages are coming in from your controller.
- [ ] **Ableton Live 12 MIDI Transformations and Generators** (`ableton-midi-tools-transformations-generators.md`)
      Use it when: you need to add rhythmic patterns to a melody; you want to stretch or warp a sequence to fit a tempo; you're trying to create a melodic line from a simple rhythm; you're adjusting a scale-based sequence to fit a key; you're editing a clip to make it more dynamic and interesting.
      - [ ] Sharper line: Use it when: you want to strum or arpeggiate a chord in the clip editor, humanise timing, generate a rhythm or melody, or reshape the notes in a clip.
- [ ] **Ableton Live Mixing and Gain Staging** (`ableton-mixing-and-gain-staging.md`)
      Use it when: you need to balance track levels to prevent clipping; you want to monitor a specific track without affecting others; you're trying to make a mix sound fuller and more present; you're transitioning between songs smoothly; you're grouping tracks to manage volume relationships.
      - [ ] Sharper line: Use it when: you want sensible levels on every track, headroom on the master, and a mix that doesn't clip.
- [ ] **Ableton Modulation Effects Devices** (`ableton-modulation-effects-devices.md`)
      Use it when: you need to add thickness to thin sounds; you want to create movement with rhythmic sweeps; you're looking for a warm, organic lo-fi texture.
      - [ ] Sharper line: Use it when: you want chorus, flanger, phaser or tremolo style movement on a sound.
- [ ] **Ableton MPE Control (MIDI Effect)** (`ableton-mpe-control-device.md`)
      Use it when: you need to shape expressive controller input to make notes more dynamic; your MIDI signals lack smooth velocity or aftertouch response; you want to add nuance to performance with custom curve mappings; your instruments don't support MPE but you still want expressive control; you're trying to make slides feel more natural and responsive.
      - [ ] Sharper line: Use it when: you want to shape or remap the pitch bend, slide and pressure coming from an MPE controller.
- [ ] **Ableton Multiband Dynamics Device** (`ableton-multiband-dynamics-device.md`)
      Use it when: you need to tame harsh mid-range frequencies; your vocals sound muffled in the mix; you want to add low-end punch without muddying the high end; your drums feel flat and lifeless; you're trying to keep quiet elements like reverb tails from cutting through.
      - [ ] Sharper line: Use it when: you want to compress only the low end or only the highs of a sound, tame harsh frequencies dynamically, or get the OTT squashed upward compression sound.
- [ ] **Ableton Note Echo (MIDI Effect)** (`ableton-note-echo-device.md`)
      Use it when: you need to add rhythmic echoes to MIDI notes; your drum hits lack depth and body; you want to create swing or groove in a MIDI sequence; you're trying to make echoed notes feel more dynamic and expressive; you're working with MPE controllers and need to echo pressure and slide data.
      - [ ] Sharper line: Use it when: you want MIDI notes to repeat as echoes that get quieter, like a delay on the notes themselves.
- [ ] **Ableton Operator (Instrument)** (`ableton-operator-device.md`)
      Use it when: you need to shape a rich, textured sound; you're trying to add depth and movement; you want to create a complex, evolving pad; you're struggling with a thin or uninteresting tone; you're looking to add subtle modulation and resonance.
      - [ ] Sharper line: Use it when: you want FM synthesis sounds: bells, electric pianos, metallic basses or digital leads.
- [ ] **Ableton Overdrive (Audio Effect)** (`ableton-overdrive-device.md`)
      Use it when: your guitars lack warmth; your vocals need edge; your drums need punch; your bass needs definition; your synth leads need character.
      - [ ] Sharper line: Use it when: you want a guitar pedal style overdrive or drive with a mid-range focus.
- [ ] **Ableton Pedal Analog Circuit Saturation** (`ableton-pedal-device.md`)
      Use it when: you need thick, warm overdrive on guitars; want aggressive distortion for rock tracks; are trying to add grit to clean drums; face thinness in heavy distortion mixes; need a low-end boost for bass synths.
      - [ ] Sharper line: Use it when: you want guitar stomp box overdrive, distortion or fuzz on a guitar, bass, synth or drums.
- [ ] **Ableton Phaser-Flanger Jet sweeps and Comb Filtering** (`ableton-phaser-flanger-device.md`)
      Use it when: you want to add dramatic frequency notches to drums, create metallic resonance on synths, or generate sweeping jet effects on guitars and pads.
      - [ ] Sharper line: Use it when: you want a swooshing jet sweep, a notch sweep phasing effect on a guitar, or comb-filter flanging.
- [ ] **Ableton Physical Modeling Instruments and Effects** (`ableton-physical-modeling-devices.md`)
      Use it when: you want to create realistic acoustic textures like warm piano tones, bright Rhodes sounds, or resonant drum hits; you need dynamic responses to MIDI velocity and modulation; you're designing sounds that mimic real-world physical interactions like string vibrations or mallet strikes.
      - [ ] Sharper line: Use it when: you want sounds modelled on real strings, mallets, tubes and plates rather than samples.
- [ ] **Ableton Pitch and Note Length MIDI Effects** (`ableton-pitch-and-note-length-midi-effects.md`)
      Use it when: you need to transpose melodies on the fly; you want notes to trigger only when releasing a key; you're trying to make all notes the same length; you're scaling note duration with how hard you play; you're building key splits for specific ranges.
      - [ ] Sharper line: Use it when: you want to transpose incoming MIDI, or make notes longer or shorter automatically.
- [ ] **Ableton Rack Architecture and Chain Selectors** (`ableton-racks-and-chain-selectors.md`)
      Use it when: you need to switch between different instrument or effect setups on the fly; you want to map keyboard ranges or note velocity to different chains; you're trying to create smooth transitions between plugin configurations.
      - [ ] Sharper line: Use it when: you want to switch between different effect chains or sounds with one knob, or build a morphing rack.
- [ ] **Ableton Racks and Macros** (`ableton-racks-and-macros.md`)
      Use it when: you need to control multiple effects or instruments at once; you want to blend dry and wet signals in real time; you're adjusting settings across different chains for parallel processing; you're trying to simplify complex patches into manageable controls; you're setting up macro-based live performance setups.
      - [ ] Sharper line: Use it when: you want one knob to control several parameters at once, or to save a group of devices as a reusable preset.
- [ ] **Ableton Random (MIDI Effect)** (`ableton-random-device.md`)
      Use it when: you want to add unexpected variation to a melody; your sequence needs a natural, human-like imperfection; you're trying to create a dynamic, evolving rhythm; you're simulating a live performance with subtle pitch shifts; you need to break monotony in a repetitive pattern.
      - [ ] Sharper line: Use it when: you want MIDI notes to change pitch randomly for generative melodies or happy accidents.
- [ ] **Ableton Redux Bitcrushing and Downsampling** (`ableton-redux-device.md`)
      Use it when: you want to add gritty texture to clean drums; need harsh aliasing for industrial beats; trying to create lo-fi warmth in synth leads; want digital distortion in electronic bass; looking for aggressive edge in clean vocal tracks.
      - [ ] Sharper line: Use it when: you want to bitcrush a sound, make drums sound like an old 8 or 12 bit sampler, get lo-fi crunchy digital aliasing, or downsample for grit.
- [ ] **Ableton Roar Saturation and Distortion** (`ableton-roar-device.md`)
      Use it when: you need to add warmth and edge to drums, enhance the harmonic content of synths, fix thin or lifeless sounds, control low-end distortion without muddying the mix, or create dynamic, input-reactive saturation.
      - [ ] Sharper line: Use it when: you want heavy saturation or distortion, multi-stage drive for aggressive basses and drums, or distortion with filters and feedback.
- [ ] **Ableton Live Audio and MIDI Routing Architecture** (`ableton-routing-and-submixing.md`)
      Use it when: you need to route a track’s output to another track; you want to monitor a track without it playing through the speakers; you’re trying to create a submix for a group of tracks; you’re recording a track’s output as a sample; you’re adjusting how a track’s signal is sent to the main mix.
      - [ ] Sharper line: Use it when: you want to send tracks to a group or bus, route audio from one track into another, or set up sidechain inputs.
- [ ] **Ableton Sampler (Instrument)** (`ableton-sampler-device.md`)
      Use it when: you need to create layered sounds; your samples aren't matching the right notes; you want to switch between different articulations; you're trying to fix inconsistent sample triggers; you're designing a custom instrument with multiple voices.
      - [ ] Sharper line: Use it when: you want to build a multi-sampled instrument with zones and layers, or deep sampler modulation.
- [ ] **Ableton Saturator Waveshaping and Saturation** (`ableton-saturator-device.md`)
      Use it when: you need to add warmth to a vocal, your drums sound thin, or your synth lacks presence.
      - [ ] Sharper line: Use it when: you want warmth, soft clipping, harmonic saturation or gentle distortion to make a sound fuller and louder.
- [ ] **Ableton Scale And Chord MIDI Effects** (`ableton-scale-chord-effects.md`)
      Use it when: you want to stay in key, your chords sound off, you're trying to make one-finger chord progressions, you're not sure about the scale you're using, or you're experimenting with unconventional MIDI patterns.
      - [ ] Sharper line: Use it when: you want every note to snap to a key, or one key to play a whole chord.
- [ ] **Ableton Seamless Loop Clicks For Wwise** (`ableton-seamless-loop-clicks-wwise.md`)
      Use it when: your loops click in Wwise because they have sudden level jumps; you need to align start and end markers exactly; you're exporting a rhythmic loop that doesn't loop cleanly; you're dealing with ambient sounds that have tails or pops; you're trying to avoid clicks by adding crossfades but it's not working.
      - [ ] Sharper line: Use it when: a loop clicks or pops at the loop point in a game engine and you need it to loop seamlessly.
- [ ] **Ableton Shaper (Audio Effect)** (`ableton-shaper-device.md`)
      Use it when: you need to add movement to a sound; your synth lacks character; you want to shape a waveform dynamically; your effects are too static; you're trying to make a pad more expressive.
      - [ ] Sharper line: Use it when: you want to draw your own custom modulation shape with breakpoints and use it to move a parameter.
- [ ] **Ableton Shaper MIDI (MIDI Effect)** (`ableton-shaper-midi-device.md`)
      Use it when: you need to dynamically shape parameters with MIDI notes; you want to add expression to synth or instrument performance; you're trying to create smooth transitions between sounds; you're looking for a way to modulate effects in real time; you're working with live performance techniques like velocity-sensitive modulation.
      - [ ] Sharper line: Use it when: you want a drawn modulation shape triggered by MIDI notes to move parameters.
- [ ] **Ableton Shifter and Distortion Devices** (`ableton-shifter-and-distortion-devices.md`)
      Use it when: you need to add character to a vocal track; you're trying to create a metallic or clangorous sound; you want to preserve the low end while adding distortion.
      - [ ] Sharper line: Use it when: you want pitch shifting, ring modulation or frequency shifting, or a range of distortion colours.
- [ ] **Ableton Simpler (Instrument)** (`ableton-simpler-device.md`)
      Use it when: you need to shape a sample's tone with filters, add dynamic movement with envelopes, or create rhythmic patterns by slicing or looping a sample.
      - [ ] Sharper line: Use it when: you want to play a single sample across the keyboard, slice a loop into pads, or chop a vocal into notes.
- [ ] **Ableton Spectral Effects Devices** (`ableton-spectral-effects-devices.md`)
      Use it when: you want to turn vocal layers into shimmering ambient textures; you need to freeze a snare hit and turn it into a sustained pad; you're trying to make a noise sample into a melodic synth lead; you're struggling with muddy harmonics from overlapping chords; you want to create a metallic, bell-like resonance from a drum loop.
      - [ ] Sharper line: Use it when: you want to freeze a sound, smear it into a pad, or make spectral delays and resonances.
- [ ] **Type: Sound Design** (`ableton-spectral-resonator.md`)
      Use it when: you want to add depth to a vocal track; you're trying to make a synth sound more full; you need to enhance the warmth of a bass line; you're looking to create a mysterious ambient texture; you want to make a drum hit more present in the mix.
      - [ ] Sharper line: Use it when: you want to turn a sound into tuned resonances that follow MIDI notes, or make drums and noise sing in key.
- [ ] **Using Spectrum And Analyzers In Ableton** (`ableton-spectrum-analyzer.md`)
      Use it when: you need to find thin drums; your mix feels too bright; you're trying to balance low-end presence; you want to check for resonant peaks; you're comparing your mix to a reference.
      - [ ] Sharper line: Use it when: you want to see the frequencies in a sound, find what is causing mud or harshness, or compare your mix with a reference.
- [ ] **Ableton Live 12 Stem Separation** (`ableton-stem-separation.md`)
      Use it when: you need to isolate vocals, drums, bass, or other elements to edit, sample, or remix; you want to separate audio from a track for precise manipulation; you're preparing a track for a DJ set or live performance; you're trying to clean up a recording by removing unwanted noise; you want to merge specific stems back into a single track for simplicity.
      - [ ] Sharper line: Use it when: you want to pull the vocal out of a finished song, make an acapella or instrumental, or split a track into drums, bass, vocals and other.
- [ ] **Ableton Template Project Setup** (`ableton-template-project-setup.md`)
      Use it when: you need to quickly set up a project with pre-routed tracks, return effects, and default plugins for efficient recording and mixing; you want to save time by starting from a consistent structure every session; you're preparing a template for a specific genre or workflow; you need color-coded tracks to keep your DAW organized; you're looking to streamline the process of adding vocals, instruments, and effects without reconfiguring everything from scratch.
      - [ ] Sharper line: Use it when: you want Live to open with your tracks, returns and devices already set up every time.
- [ ] **Ableton Live Tempo Follower and Synchronization** (`ableton-tempo-follower-and-sync.md`)
      Use it when: you need to keep your track in time with other devices; your drum machine is out of sync with the beat; you're following a live performance with a microphone; you want to sync your MIDI sequencer to an external controller; your audio input is changing tempo on the fly.
      - [ ] Sharper line: Use it when: you want Live to follow a live drummer's or band's tempo, or sync Live's tempo to incoming audio.
- [ ] **Ableton Tension (Instrument)** (`ableton-tension-device.md`)
      Use it when: you need realistic string instrument sounds; you're trying to simulate bow, hammer, or plectrum playing; you want to control string decay and vibrato; you're experimenting with damping and tension effects; you're looking for dynamic, expressive string textures.
      - [ ] Sharper line: Use it when: you want a realistic plucked, bowed or hammered string instrument sound.
- [ ] **Ableton Tuner Instrument Calibration** (`ableton-tuner-device.md`)
      Use it when: you need to tune a guitar or bass in real time; you're calibrating a synth or vocal track for perfect pitch; you're setting up intonation on a string instrument; you're adjusting to a non-standard tuning like 432 Hz; you're ensuring a microphone capture is in tune with the project's scale.
      - [ ] Sharper line: Use it when: you want to tune a guitar, bass or other live instrument before recording.
- [ ] **Ableton Live 12 Tuning Systems and Microtuning** (`ableton-tuning-systems-microtuning.md`)
      Use it when: you need to retune your entire project for a specific scale or temperament; your instruments are out of tune with standard 12-TET; you're working with non-Western or historical tuning systems.
      - [ ] Sharper line: Use it when: you want to use non-Western scales, quarter tones or custom microtuning.
- [ ] **Ableton Live Groove Pool and Swing** (`ableton-using-grooves.md`)
      Use it when: you want to add swing to your drums; you need to make your MIDI notes more human; you're trying to fix timing issues in a vocal track; you want to vary the rhythm of a bass line; you're looking to add a subtle random feel to a synth line.
      - [ ] Sharper line: Use it when: you want to add swing or shuffle to a beat, or make programmed drums feel less robotic.
- [ ] **Ableton Utility Gain and Stereo Control** (`ableton-utility-device.md`)
      Use it when: you need to balance track levels, fix phase issues, adjust stereo width, ensure bass is mono, or check if a track sounds good on mono.
      - [ ] Sharper line: Use it when: you want to change gain, make a track mono, narrow or widen the stereo image, flip the phase, or mono the bass.
- [ ] **Ableton Velocity Dynamics and Randomization** (`ableton-velocity-midi-effect.md`)
      Use it when: you need to add natural variation to rigid drum hits; you want to smooth out inconsistent MIDI playing; you're trying to prevent soft notes from fading out; you're dealing with harsh velocity spikes in layered sounds; you're looking to make electronic MIDI feel more human.
      - [ ] Sharper line: Use it when: you want to randomise or limit note velocities so a part sounds more human or more even.
- [ ] **Ableton Vinyl Distortion Turntable Artifacts** (`ableton-vinyl-distortion-device.md`)
      Use it when: you want to add authentic vinyl texture to lo-fi beats; your tracks need subtle crackle and dust noise; you're emulating a turntable's imperfections; you're looking for dynamic, non-repeating distortion; you're aiming for a warm, analog character in electronic music.
      - [ ] Sharper line: Use it when: you want vinyl crackle, turntable wobble or old record noise for a lo-fi sound.
- [ ] **Ableton Vocoder** (`ableton-vocoder.md`)
      Use it when: you want to shape a synth with a vocal; you need a robot voice effect; you're trying to make a talking synth; you're looking to blend speech with a pad or bright sound; you want to create a more mechanical or synthetic vocal texture.
      - [ ] Sharper line: Use it when: you want a robot voice, to make a synth talk with a vocal, or a vocoded choir effect.
- [ ] **Ableton Warp Modes and Transient Smearing** (`ableton-warp-modes-and-transient-smearing.md`)
      Use it when: you need sharp transients in warped drums; your beats mode is still smearing after a big tempo change; you're working with a full mix that's losing punch; you're trying to keep a vocal line clear after warping; you're dealing with a dense arrangement where transients blur into each other.
      - [ ] Sharper line: Use it when: drums sound smeared or flammy after time stretching, or you want to choose the right warp mode for vocals, drums or full mixes.
- [ ] **Fixing Clicks After Warping A Kick In Ableton** (`ableton-warped-kick-clicks.md`)
      Use it when: your kick has a click after warping; you're unsure if the click is in the clip or the render; you need to keep the attack clean but still warp for timing; the click appears only in real-time but not in an offline render; you're trying to fix a warped transient without changing the sound.
      - [ ] Sharper line: Use it when: a kick clicks or pops after warping or time stretching it.
- [ ] **Ableton Wavetable Synthesizer** (`ableton-wavetable-synth.md`)
      Use it when: you need rich, evolving textures; want to create warm analog-style leads; are trying to fix a thin, hollow sound; need a deep, resonant sub foundation; or want to add movement and complexity to a static pad.
      - [ ] Sharper line: Use it when: you want a modern wavetable synth for evolving pads, growly basses and leads.
