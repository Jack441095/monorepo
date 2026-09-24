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

## Lines (114)

- [ ] **Ableton Live 12 Accessibility and Keyboard Navigation** (`ableton-accessibility-and-navigation.md`)
      Use it when: you need to navigate controls without a mouse; you're adjusting parameters on the fly; you're managing multiple clips in Session View; you're editing in the Arrangement View; you're using a screen reader to follow feedback.
- [ ] **Ableton Align Delay (Audio Effect)** (`ableton-align-delay-device.md`)
      Use it when: you need to sync audio with video; fix timing issues from latency; adjust for physical distance in a live setup; correct mismatched audio cues in a mix; align vocal and instrumental tracks precisely.
- [ ] **Ableton Amp (Audio Effect)** (`ableton-amp-device.md`)
      Use it when: you need more warmth in your bass; your guitars lack character; you want to add grit to a vocal track; your synth sounds flat; you're trying to make a drum hit more punchy.
- [ ] **Ableton Analog and Impulse Instruments** (`ableton-analog-and-impulse-instruments.md`)
      Use it when: you need to add warmth and character to a synth lead; your drums lack punch and definition; you want to create a dynamic, evolving bass line; your samples sound flat or lifeless; you're looking to shape sound with filters and envelopes without heavy processing.
- [ ] **Ableton Analog Synthesizer** (`ableton-analog-synth.md`)
      Use it when: you need a warm, rich bass; you want a punchy, moving lead; you're shaping a classic synth pad; you're trying to add depth with detuned layers; you're looking to create vibrato or filter movement.
- [ ] **Ableton Arpeggiator MIDI Effect** (`ableton-arpeggiator.md`)
      Use it when: you need to turn a chord into a rhythmic melody; your synth lacks movement and energy; you want to add melodic interest to a bassline; your patterns feel static and uninteresting; you're looking for a quick way to generate a catchy synth line.
- [ ] **Ableton Audio Effect Rack (Rack)** (`ableton-audio-effect-rack-device.md`)
      Use it when: you need to organize multiple effects, your signal flow is getting complicated, you want to control effects with macros, you're trying to isolate specific chains for processing, or you're setting up parallel effects for different parts of the mix.
- [ ] **Ableton Live Audio Fact Sheet and Summing Engine** (`ableton-audio-fact-sheet-neutral-operations.md`)
      Use it when: you need neutral playback, want to avoid audible artifacts, are mixing without warping, are rendering at 32-bit, or are exporting to 16-bit without dithering.
- [ ] **Ableton Auto Filter Device** (`ableton-auto-filter-device.md`)
      Use it when: you want to add movement to a synth, create dynamic auto-wah on a drum loop, shape a rhythmic filter pattern, sweep a pad's cutoff with transients, or add stereo width to a melody line.
- [ ] **Ableton Auto Pan-Tremolo Modulation** (`ableton-auto-pan-device.md`)
      Use it when: you want to add movement to a sustained synth, create rhythmic gating on a drum loop, need a subtle stereo width on a pad, want to simulate a sidechain pump without clicks, or try to add dynamic depth to a vocal track.
- [ ] **Ableton Auto Pan-Tremolo (Audio Effect)** (`ableton-auto-pan-tremolo-device.md`)
      Use it when: you need to add movement to a track; your synth lacks depth; you want to make a vocal sound more spatial; your rhythm is too flat; you're trying to create a lush, evolving atmosphere.
- [ ] **Ableton Auto Shift Real-Time Pitch and Formant Correction** (`ableton-auto-shift-device.md`)
      Use it when: you need to fix out-of-tune vocals; you want to add harmonies on the fly; you're trying to make a vocal sound more modern and sharp; you're adjusting vocal timbre without changing pitch; you're syncing vocal performance to a song's key.
- [ ] **Ableton Beat Repeat** (`ableton-beat-repeat.md`)
      Use it when: you need quick drum fills, want to add glitchy transitions, are looking for a vocal stutter, need a rhythmic fill in a song, or want to create a sudden audio break in a track.
- [ ] **Ableton Live 12 Bounce to Audio Workflow** (`ableton-bounce-to-audio-workflow.md`)
      Use it when: you need to capture processed audio for reuse; you want to isolate a track’s sound from the mixer; you’re preparing a final mix for export; you’re making variations of a section without affecting the original; you’re working with group tracks and need to bounce post-mixer.
- [ ] **Ableton Cabinet Speaker Emulation** (`ableton-cabinet-device.md`)
      Use it when: your guitar sounds harsh or thin; your bass lacks punch; you need more warmth in a synth lead; your drums feel flat; you want to add room ambiance without muddying the mix.
- [ ] **Ableton CC Control MIDI Modulation** (`ableton-cc-control-midi-effect.md`)
      Use it when: you need to control hardware synths with named parameters; you want to automate filter cutoff or envelope shapes; you're trying to match physical knob labels to Live controls; you're sending CC messages to external gear without conflicting with pitch or sustain; you're setting up multiple synth templates for quick switching.
- [ ] **Ableton Channel EQ Simplified Tonal Shaping** (`ableton-channel-eq-device.md`)
      Use it when you need to add warmth to vocals; clean up sub-bass rumble; boost clarity on cymbals; tame boxiness in synth leads; or shape a track's overall character quickly.
- [ ] **Ableton Chorus-Ensemble Spatial Modulation** (`ableton-chorus-ensemble-device.md`)
      Use it when: you want to add thickness and width to guitars, synths, or vocals; need vintage shimmer or rich, textured modulation; are trying to keep bass tight while adding stereo depth.
- [ ] **Ableton Live Clip Envelopes and Modulation** (`ableton-clip-envelopes-and-modulation.md`)
      Use it when: you want to add subtle pitch variations to a vocal sample; you need to modulate the filter cutoff of a synth sustain; you're trying to shape the dynamics of a drum hit; you're adjusting the pan position of a melody line; you're adding expression to a MIDI performance.
- [ ] **Clip Envelopes In Ableton** (`ableton-clip-envelopes.md`)
      Use it when: you want to change the volume, filter, or effects of a clip without affecting others; you need to make a sound fade in or out with each loop; you're trying to vary the pitch or pan on different parts of a loop; you want to add a rhythmic modulation that syncs with the clip's timing; you need to adjust reverb or delay levels per clip in a layered arrangement.
- [ ] **Ableton Collision Physical Modeling Synthesizer** (`ableton-collision-synth.md`)
      Use it when: you need organic metallic sounds like mallets on marimba; you want to simulate real-world percussion with dynamic velocity response; you're designing complex resonant textures like struck pipes or plates; you're looking for tactile, non-repetitive acoustic hits; you want to avoid sample-based synth sounds for more physical realism.
- [ ] **Ableton Live Comping and Take Lanes** (`ableton-comping-and-take-lanes.md`)
      Use it when: you need to capture multiple performances, select the best parts for a comp, audition different takes, copy the best sections to the main lane, or smooth transitions between recorded parts.
- [ ] **Ableton Compressor Device** (`ableton-compressor-device.md`)
      Use it when: you need to even out vocal levels, control drum transients, or smooth out a synth's dynamic range; your track feels too loud or too quiet in parts; you want to make sure the kick drum cuts through the mix without clashing with other elements; you're trying to add punch to a snare or bass without losing clarity; you're dealing with a signal that has inconsistent volume over time.
- [ ] **Ableton Live Converting Audio to MIDI** (`ableton-converting-audio-to-midi.md`)
      Use it when: you need to extract melodies, harmonies, or drum patterns from audio to work with in MIDI for arrangement or editing; you want to turn a vocal line or instrument into playable notes; you're trying to isolate and manipulate rhythmic elements like kicks and snares; you're converting a complex performance into editable MIDI data for remixing or resequencing; you're working with warped audio and want to preserve timing changes in the converted MIDI.
- [ ] **Ableton Corpus And Resonators** (`ableton-corpus-resonators.md`)
      Use it when: you want drums to have a melodic feel; your sounds lack body and warmth; you need a shimmer on hi-hats or shakers; you're trying to add harmonic interest to a rhythm; you're experimenting with tuned textures and evolving tones.
- [ ] **Ableton Live CPU Management and Track Freezing** (`ableton-cpu-management-and-freezing.md`)
      Use it when: you need to reduce CPU load; your tracks are slowing down; you're struggling with latency; you want to free up resources; you're dealing with too many effects on a track.
- [ ] **Ableton CV Tools for Modular Synthesizer Integration** (`ableton-cv-tools-device-routing.md`)
      Use it when: you need to control hardware modular synths with precise pitch and gate signals, sync modular sequencers to your tempo, or modulate hardware filters with a custom LFO.
- [ ] **Ableton Delay and Reverb Devices** (`ableton-delay-and-reverb-devices.md`)
      Use it when: you need to add depth to a vocal track; want to create a sense of space in a synth lead; are trying to make a drum hit feel more present; need to separate high frequencies for stereo imaging; struggle with muddy reverb in the low end.
- [ ] **Ableton Live Plugin Delay Compensation (PDC)** (`ableton-device-delay-compensation.md`)
      Use it when: your tracks are out of sync after using effects; you're monitoring input with latency issues; you're dealing with multiple devices causing delay; you need to record with precise timing; you're adjusting sync in complex setups.
- [ ] **Ableton Drift and Meld Synthesizers** (`ableton-drift-and-meld-synths.md`)
      Use it when: you need organic warmth in a synth lead; your pads lack depth and character; you're trying to create evolving ambient textures; your drums sound thin and lifeless; you want to add subtle imperfections to mimic analog behavior.
- [ ] **Ableton Drift Synthesizer** (`ableton-drift-synth.md`)
      Use it when: you need warmth and character in your sounds; your synth lacks organic movement; you want to emulate vintage hardware; your patches feel too precise and lifeless; you're looking for subtle imperfections and drift in your melodies.
- [ ] **Ableton Drum Buss and Beat Repeat Devices** (`ableton-drum-buss-and-beat-repeat.md`)
      Use it when: you need to add warmth and punch to a drum group; you're trying to glue together drum transients; you want to create rhythmic variations with loops; you're looking for a subtle sub-bass boost; you need dynamic pitch shifts in a beat repeat.
- [ ] **Ableton Live Drum Racks and Internal Routing** (`ableton-drum-racks-and-internal-routing.md`)
      Use it when: you need to route drum sounds to separate channels for effects; you want to trigger multiple sounds with one MIDI note; you're trying to keep your drum kit clean in the mix; you're dealing with conflicting sounds from overlapping MIDI notes; you want to apply stereo effects to specific drum elements.
- [ ] **Ableton Drum Sampler One-Shot Workflow** (`ableton-drum-sampler-device.md`)
      Use it when: you need a punchy kick, a tight snare, or a clear hi-hat with no extra noise; your samples have pre-transient dead space or lack sub-bass; you want to shape the attack of a drum without affecting the sustain.
- [ ] **Ableton Dynamic Tube Warmth and Asymmetric Drive** (`ableton-dynamic-tube-device.md`)
      Use it when you need warmth on vocals, want punch on synth leads, struggle with thin drums, need smooth harmonic richness on acoustic instruments, or want dynamic compression on transient-heavy tracks.
- [ ] **Ableton Echo Device** (`ableton-echo-device.md`)
      Use it when: you need to add depth to a vocal track; you want to create a wide, stereo delay effect; you're trying to build a dub-style delay with warmth; you're looking for a dynamic, evolving delay tail; you want to add analog character and tape noise to a sound.
- [ ] **Ableton Live MPE Editing and Expression Control** (`ableton-editing-mpe.md`)
      Use it when: you need to shape the feel of each note in a polyphonic performance; you're trying to make a melody more expressive and dynamic; you want to adjust how notes bend or slide in real time; you're editing after a performance to refine pressure and velocity curves; you're working with MPE instruments and want precise control over per-note parameters.
- [ ] **Ableton Electric (Instrument)** (`ableton-electric-device.md`)
      Use it when: you need to add warmth and realism to a piano sound; your chords lack depth and fullness; you're trying to make the attack more natural and dynamic; the sustain is too short or too long; the noise during the attack and release feels flat or lifeless.
- [ ] **Ableton Envelope Follower (Audio Effect)** (`ableton-envelope-follower-device.md`)
      Use it when: you need to control a parameter with the volume of a track; you want to create a dynamic effect like auto-wah; you're trying to gate a sound with another track's signal; you're adjusting the intensity of a modulation based on audio input; you're shaping how a parameter responds to the rhythm of a song.
- [ ] **Ableton Envelope MIDI (MIDI Effect)** (`ableton-envelope-midi-device.md`)
      Use it when: you need to shape dynamic changes in your sound; you want to control parameters with an ADSR envelope; you're trying to add expression to a performance; you're automating a parameter over time; you're looking to modulate effects or filters in real time.
- [ ] **Ableton EQ Eight (Audio Effect)** (`ableton-eq-eight-device.md`)
      Use it when: you need to cut muddiness in a vocal track; your bass is too boomy in the mix; you want to brighten a dull synth; your drums lack punch in the midrange; and you're trying to make a sound sit better in the stereo field.
- [ ] **Ableton EQ Three DJ Kill-EQ Workflow** (`ableton-eq-three-device.md`)
      Use it when: you need instant bass/mid/high cuts during drops; you're transitioning between tracks in a set; you want to isolate and boost specific frequency ranges on a DJ stem; you're preparing for a breakdown with a sudden frequency mute; you're trying to clean up a track by surgically removing problematic frequencies.
- [ ] **Ableton Erosion Harmonic Degradation** (`ableton-erosion-device.md`)
      Use it when: you need to add sharp top-end grit to a dull bass, enhance snares with metallic presence, or inject harmonic sizzle into a dense mix.
- [ ] **Ableton Essential Audio Utilities and Coloration** (`ableton-essential-audio-utilities.md`)
      Use it when: you need to add width and movement to a track; you're trying to fix a tuning issue on a vocal or instrument; you want to inject grit and character into a drum loop or synth; you're looking to create a harmonized vocal effect; you're aiming for a vintage, warm sound with record-like imperfections.
- [ ] **Ableton Essential Workflow Hacks and Shortcuts** (`ableton-essential-workflow-hacks.md`)
      Use it when: you need to quickly hide or show tracks to focus on specific parts of your arrangement; you want to isolate a clip to edit without playing it; you're trying to find your most used plugins or instruments in the Browser; you're adjusting MIDI notes on the fly without using the wheel; you're organizing your session to keep it clean and easy to navigate.
- [ ] **Ableton Expression Control (MIDI Effect)** (`ableton-expression-control-device.md`)
      Use it when: you need to control parameters with live performance inputs; you want to automate settings on the fly; you're trying to add expressive variation to a sound; you're mapping external controllers to effects or filters; you're adjusting modulation depth for a more organic feel.
- [ ] **Ableton External Audio Effect Hardware Insert** (`ableton-external-audio-effect.md`)
      Use it when: you need to process audio through external analog gear; you're blending outboard effects with dry signals; you're trying to fix phase issues from hardware delays; you're routing to a physical mixer or outboard compressor; you're adjusting levels to avoid clipping or distortion.
- [ ] **Ableton External Instrument Hardware MIDI and Audio Routing** (`ableton-external-instrument.md`)
      Use it when: you need to play and record hardware synths or drum machines; you want to automate or freeze a live performance; you're dealing with MIDI and audio latency issues; you're routing audio from external gear into Live; you're trying to keep project organization simple and efficient.
- [ ] **Ableton Filter Delay Tri-Band Spatial Echo** (`ableton-filter-delay-device.md`)
      Use it when: you want to add depth to a vocal or synth by creating layered, frequency-specific echoes that sit in different parts of the mix; your main signal is too bright and needs a warm, low-mid delay to balance it; you're trying to make a drum hit feel more spatial without muddying the high-end; you need a delay that evolves in tone as it repeats; you're looking to add ambient texture without overwhelming the main sound.
- [ ] **Ableton Follow Actions** (`ableton-follow-actions.md`)
      Use it when: you want clips to play in sequence; you need random variations in a pattern; you're building a song structure without Arrangement View; you're setting up a live performance loop; you want to automate transitions between tracks.
- [ ] **Ableton Wwise One-Shot SFX Asset Prep** (`ableton-game-audio-asset-prep.md`)
      Use it when: you need clean one-shots for Wwise Events, want seamless loops for ambient spaces, are preparing stems for music layers, have to trim tails carefully for precise timing, or need clear metadata for asset organization.
- [ ] **Ableton Glue Compressor Device** (`ableton-glue-compressor-device.md`)
      Use it when: you need to glue together a dense mix; your drums and vocals are fighting for space; you want tighter dynamics on a group of tracks; your master bus feels flat or unbalanced; you're looking for analog warmth without over-compressing.
- [ ] **Ableton Grain Delay (Audio Effect)** (`ableton-grain-delay-device.md`)
      Use it when: you need to add texture to a synth pad; you want to create rhythmic patterns with delayed sounds; you're trying to make a vocal track feel more spatial; you're looking for a subtle echo that doesn't muddy the mix; you want to experiment with pitch-shifted delays for a warped effect.
- [ ] **Ableton Hybrid Reverb Dual Engine** (`ableton-hybrid-reverb-device.md`)
      Use it when: you need realistic room ambiance for vocals or instruments; want a lush, modulated tail for ambient textures; are mixing in a studio and need to avoid muddiness from low-end rumble; are blending acoustic and digital spaces for a hybrid reverb effect; want to maintain clear transients while adding depth and space.
- [ ] **Ableton Hybrid Reverb** (`ableton-hybrid-reverb.md`)
      Use it when: you need a natural room reverb for vocals; want to add depth to ambient pads; are trying to create a shimmer effect on a melody; need a realistic cathedral sound for a choir; looking to blend digital and real space textures.
- [ ] **Ableton Instrument Rack (Rack)** (`ableton-instrument-rack-device.md`)
      Use it when: you need to organize multiple instrument or effect chains, simplify control with macro mappings, route signals efficiently, manage complex setups, or create custom device combinations for specific sounds or performances.
- [ ] **Ableton Live Clip Launch Modes and Follow Actions** (`ableton-launching-clips-and-follow-actions.md`)
      Use it when: you need to trigger other clips automatically after your current one; you want to add variation or randomness to your sequence; you're trying to create a chain of events that flow smoothly; you're dealing with timing inconsistencies in a live performance; you want to control when follow actions happen relative to the main clip.
- [ ] **Ableton LFO (Audio Effect)** (`ableton-lfo-device.md`)
      Use it when: you want to add movement to a synth's filter; you're trying to make a vocal effect more dynamic; you need to vary the depth of a reverb over time; you're struggling with a dull synth sound; you want to create a pulsing rhythm effect.
- [ ] **Ableton Limiter and Gate Devices** (`ableton-limiter-and-gate-devices.md`)
      Use it when: you need to prevent clipping on master buses; you're cleaning up noise from vocal room ambiance; you want to control loud peaks in a mix; you're gating drum transients to avoid bleed; you're trying to keep a clean stereo image without losing width.
- [ ] **Ableton Link Synchronization** (`ableton-link-sync.md`)
      Use it when: you need to keep multiple devices in time for a performance; you want to change tempo without stopping the session; you're syncing Live with a mobile app or another device; you're working with independent transport starts and stops; you're ensuring all peers follow the same beat and phase.
- [ ] **DJing And Live Performance With Ableton** (`ableton-live-djing.md`)
      Use it when: you need smooth transitions between tracks; you're beat-matching live performances; you want to automate crossfader movements for seamless fades.
- [ ] **Ableton Looper Device** (`ableton-looper-device.md`)
      Use it when: you need to record and layer live sounds on the fly; you want to build a loop that stays in time with your song; you're overdubbing extra parts without stopping the loop; you're trying to capture spontaneous ideas during a performance; you're syncing your loop to the beat instead of counting bars manually.
- [ ] **Ableton Looper Device** (`ableton-looper.md`)
      Use it when: you need to record and layer live sounds in real time; you want to build a complex arrangement on stage; you're overdubbing additional layers onto an existing loop; you're trying to create evolving, self-erasing textures; you're syncing loops to a tempo for a performance.
- [ ] **Max For Live Basics** (`ableton-max-for-live-basics.md`)
      Use it when: you need to add texture to a track; you want to automate parameters with a smooth, rhythmic movement; you're looking for a way to control effects with audio dynamics instead of a compressor.
- [ ] **Ableton Max for Live Overview** (`ableton-max-for-live-overview.md`)
      Use it when: you need to add custom sounds or effects that aren't available natively; you're trying to create unique modulation sources or interactive tools; you're dealing with complex signal processing that requires visual programming; you're looking for flexible, real-time adjustable instruments; you're building or modifying patches for specific sonic goals.
- [ ] **Ableton Max for Live Modulation Utilities** (`ableton-max-modulation-devices.md`)
      Use it when: you need to add rhythmic movement to filter cutoffs; want to vary synth parameters with keyboard velocity; are trying to create dynamic changes in reverb decay; need to randomize effects parameters for interest; or want to match drive levels to playing dynamics.
- [ ] **Using MIDI Controllers With Ableton** (`ableton-midi-controller-setup.md`)
      Use it when: you need to play instruments live; you want to trigger clips without a mouse; you're trying to control synth parameters in real time; you're setting up a control surface for deep integration; you're having trouble with velocity or aftertouch settings.
- [ ] **Ableton MIDI Effect Rack Device** (`ableton-midi-effect-rack-device.md`)
      Use it when: you need to process different MIDI sounds separately; you want to switch between effects on the fly; you're trying to isolate specific notes for modulation; you're dealing with multiple layered MIDI instruments; you want to control different effects per note range.
- [ ] **Ableton MIDI Effects Devices** (`ableton-midi-effects-devices.md`)
      Use it when: you need to add rhythmic patterns from chords; you want to harmonize a melody with supporting notes; you're trying to keep a sequence in key; you're looking for subtle pitch variation in a MIDI line; you want to generate random but musical note shifts.
- [ ] **Ableton Live MIDI Fact Sheet and Timing** (`ableton-midi-fact-sheet-timing-jitter.md`)
      Use it when: your MIDI recordings sound out of sync; you're experiencing timing issues with hardware synths; you need consistent playback speed; your drum patterns feel loose; you're trying to fix jitter in live performances.
- [ ] **Ableton MIDI Monitor (MIDI Effect)** (`ableton-midi-monitor-device.md`)
      Use it when: you need to see what notes and velocities are being sent to an instrument; you're troubleshooting a MIDI setup; you want to understand how a performance is being translated into MIDI messages; you're trying to capture a specific moment of playing; you're working with MPE and need to check polyphonic aftertouch data.
- [ ] **Ableton Live 12 MIDI Transformations and Generators** (`ableton-midi-tools-transformations-generators.md`)
      Use it when: you need to add rhythmic patterns to a melody; you want to stretch or warp a sequence to fit a tempo; you're trying to create a melodic line from a simple rhythm; you're adjusting a scale-based sequence to fit a key; you're editing a clip to make it more dynamic and interesting.
- [ ] **Ableton Live Mixing and Gain Staging** (`ableton-mixing-and-gain-staging.md`)
      Use it when: you need to balance track levels to prevent clipping; you want to monitor a specific track without affecting others; you're trying to make a mix sound fuller and more present; you're transitioning between songs smoothly; you're grouping tracks to manage volume relationships.
- [ ] **Ableton Modulation Effects Devices** (`ableton-modulation-effects-devices.md`)
      Use it when: you need to add thickness to thin sounds; you want to create movement with rhythmic sweeps; you're looking for a warm, organic lo-fi texture.
- [ ] **Ableton MPE Control (MIDI Effect)** (`ableton-mpe-control-device.md`)
      Use it when: you need to shape expressive controller input to make notes more dynamic; your MIDI signals lack smooth velocity or aftertouch response; you want to add nuance to performance with custom curve mappings; your instruments don't support MPE but you still want expressive control; you're trying to make slides feel more natural and responsive.
- [ ] **Ableton Multiband Dynamics Device** (`ableton-multiband-dynamics-device.md`)
      Use it when: you need to tame harsh mid-range frequencies; your vocals sound muffled in the mix; you want to add low-end punch without muddying the high end; your drums feel flat and lifeless; you're trying to keep quiet elements like reverb tails from cutting through.
- [ ] **Ableton Note Echo (MIDI Effect)** (`ableton-note-echo-device.md`)
      Use it when: you need to add rhythmic echoes to MIDI notes; your drum hits lack depth and body; you want to create swing or groove in a MIDI sequence; you're trying to make echoed notes feel more dynamic and expressive; you're working with MPE controllers and need to echo pressure and slide data.
- [ ] **Ableton Operator (Instrument)** (`ableton-operator-device.md`)
      Use it when: you need to shape a rich, textured sound; you're trying to add depth and movement; you want to create a complex, evolving pad; you're struggling with a thin or uninteresting tone; you're looking to add subtle modulation and resonance.
- [ ] **Ableton Overdrive (Audio Effect)** (`ableton-overdrive-device.md`)
      Use it when: your guitars lack warmth; your vocals need edge; your drums need punch; your bass needs definition; your synth leads need character.
- [ ] **Ableton Pedal Analog Circuit Saturation** (`ableton-pedal-device.md`)
      Use it when: you need thick, warm overdrive on guitars; want aggressive distortion for rock tracks; are trying to add grit to clean drums; face thinness in heavy distortion mixes; need a low-end boost for bass synths.
- [ ] **Ableton Phaser-Flanger Jet sweeps and Comb Filtering** (`ableton-phaser-flanger-device.md`)
      Use it when: you want to add dramatic frequency notches to drums, create metallic resonance on synths, or generate sweeping jet effects on guitars and pads.
- [ ] **Ableton Physical Modeling Instruments and Effects** (`ableton-physical-modeling-devices.md`)
      Use it when: you want to create realistic acoustic textures like warm piano tones, bright Rhodes sounds, or resonant drum hits; you need dynamic responses to MIDI velocity and modulation; you're designing sounds that mimic real-world physical interactions like string vibrations or mallet strikes.
- [ ] **Ableton Pitch and Note Length MIDI Effects** (`ableton-pitch-and-note-length-midi-effects.md`)
      Use it when: you need to transpose melodies on the fly; you want notes to trigger only when releasing a key; you're trying to make all notes the same length; you're scaling note duration with how hard you play; you're building key splits for specific ranges.
- [ ] **Ableton Rack Architecture and Chain Selectors** (`ableton-racks-and-chain-selectors.md`)
      Use it when: you need to switch between different instrument or effect setups on the fly; you want to map keyboard ranges or note velocity to different chains; you're trying to create smooth transitions between plugin configurations.
- [ ] **Ableton Racks and Macros** (`ableton-racks-and-macros.md`)
      Use it when: you need to control multiple effects or instruments at once; you want to blend dry and wet signals in real time; you're adjusting settings across different chains for parallel processing; you're trying to simplify complex patches into manageable controls; you're setting up macro-based live performance setups.
- [ ] **Ableton Random (MIDI Effect)** (`ableton-random-device.md`)
      Use it when: you want to add unexpected variation to a melody; your sequence needs a natural, human-like imperfection; you're trying to create a dynamic, evolving rhythm; you're simulating a live performance with subtle pitch shifts; you need to break monotony in a repetitive pattern.
- [ ] **Ableton Redux Bitcrushing and Downsampling** (`ableton-redux-device.md`)
      Use it when: you want to add gritty texture to clean drums; need harsh aliasing for industrial beats; trying to create lo-fi warmth in synth leads; want digital distortion in electronic bass; looking for aggressive edge in clean vocal tracks.
- [ ] **Ableton Roar Saturation and Distortion** (`ableton-roar-device.md`)
      Use it when: you need to add warmth and edge to drums, enhance the harmonic content of synths, fix thin or lifeless sounds, control low-end distortion without muddying the mix, or create dynamic, input-reactive saturation.
- [ ] **Ableton Live Audio and MIDI Routing Architecture** (`ableton-routing-and-submixing.md`)
      Use it when: you need to route a track’s output to another track; you want to monitor a track without it playing through the speakers; you’re trying to create a submix for a group of tracks; you’re recording a track’s output as a sample; you’re adjusting how a track’s signal is sent to the main mix.
- [ ] **Ableton Sampler (Instrument)** (`ableton-sampler-device.md`)
      Use it when: you need to create layered sounds; your samples aren't matching the right notes; you want to switch between different articulations; you're trying to fix inconsistent sample triggers; you're designing a custom instrument with multiple voices.
- [ ] **Ableton Saturator Waveshaping and Saturation** (`ableton-saturator-device.md`)
      Use it when: you need to add warmth to a vocal, your drums sound thin, or your synth lacks presence.
- [ ] **Ableton Scale And Chord MIDI Effects** (`ableton-scale-chord-effects.md`)
      Use it when: you want to stay in key, your chords sound off, you're trying to make one-finger chord progressions, you're not sure about the scale you're using, or you're experimenting with unconventional MIDI patterns.
- [ ] **Ableton Seamless Loop Clicks For Wwise** (`ableton-seamless-loop-clicks-wwise.md`)
      Use it when: your loops click in Wwise because they have sudden level jumps; you need to align start and end markers exactly; you're exporting a rhythmic loop that doesn't loop cleanly; you're dealing with ambient sounds that have tails or pops; you're trying to avoid clicks by adding crossfades but it's not working.
- [ ] **Ableton Shaper (Audio Effect)** (`ableton-shaper-device.md`)
      Use it when: you need to add movement to a sound; your synth lacks character; you want to shape a waveform dynamically; your effects are too static; you're trying to make a pad more expressive.
- [ ] **Ableton Shaper MIDI (MIDI Effect)** (`ableton-shaper-midi-device.md`)
      Use it when: you need to dynamically shape parameters with MIDI notes; you want to add expression to synth or instrument performance; you're trying to create smooth transitions between sounds; you're looking for a way to modulate effects in real time; you're working with live performance techniques like velocity-sensitive modulation.
- [ ] **Ableton Shifter and Distortion Devices** (`ableton-shifter-and-distortion-devices.md`)
      Use it when: you need to add character to a vocal track; you're trying to create a metallic or clangorous sound; you want to preserve the low end while adding distortion.
- [ ] **Ableton Simpler (Instrument)** (`ableton-simpler-device.md`)
      Use it when: you need to shape a sample's tone with filters, add dynamic movement with envelopes, or create rhythmic patterns by slicing or looping a sample.
- [ ] **Ableton Spectral Effects Devices** (`ableton-spectral-effects-devices.md`)
      Use it when: you want to turn vocal layers into shimmering ambient textures; you need to freeze a snare hit and turn it into a sustained pad; you're trying to make a noise sample into a melodic synth lead; you're struggling with muddy harmonics from overlapping chords; you want to create a metallic, bell-like resonance from a drum loop.
- [ ] **Type: Sound Design** (`ableton-spectral-resonator.md`)
      Use it when: you want to add depth to a vocal track; you're trying to make a synth sound more full; you need to enhance the warmth of a bass line; you're looking to create a mysterious ambient texture; you want to make a drum hit more present in the mix.
- [ ] **Using Spectrum And Analyzers In Ableton** (`ableton-spectrum-analyzer.md`)
      Use it when: you need to find thin drums; your mix feels too bright; you're trying to balance low-end presence; you want to check for resonant peaks; you're comparing your mix to a reference.
- [ ] **Ableton Live 12 Stem Separation** (`ableton-stem-separation.md`)
      Use it when: you need to isolate vocals, drums, bass, or other elements to edit, sample, or remix; you want to separate audio from a track for precise manipulation; you're preparing a track for a DJ set or live performance; you're trying to clean up a recording by removing unwanted noise; you want to merge specific stems back into a single track for simplicity.
- [ ] **Ableton Template Project Setup** (`ableton-template-project-setup.md`)
      Use it when: you need to quickly set up a project with pre-routed tracks, return effects, and default plugins for efficient recording and mixing; you want to save time by starting from a consistent structure every session; you're preparing a template for a specific genre or workflow; you need color-coded tracks to keep your DAW organized; you're looking to streamline the process of adding vocals, instruments, and effects without reconfiguring everything from scratch.
- [ ] **Ableton Live Tempo Follower and Synchronization** (`ableton-tempo-follower-and-sync.md`)
      Use it when: you need to keep your track in time with other devices; your drum machine is out of sync with the beat; you're following a live performance with a microphone; you want to sync your MIDI sequencer to an external controller; your audio input is changing tempo on the fly.
- [ ] **Ableton Tension (Instrument)** (`ableton-tension-device.md`)
      Use it when: you need realistic string instrument sounds; you're trying to simulate bow, hammer, or plectrum playing; you want to control string decay and vibrato; you're experimenting with damping and tension effects; you're looking for dynamic, expressive string textures.
- [ ] **Ableton Tuner Instrument Calibration** (`ableton-tuner-device.md`)
      Use it when: you need to tune a guitar or bass in real time; you're calibrating a synth or vocal track for perfect pitch; you're setting up intonation on a string instrument; you're adjusting to a non-standard tuning like 432 Hz; you're ensuring a microphone capture is in tune with the project's scale.
- [ ] **Ableton Live 12 Tuning Systems and Microtuning** (`ableton-tuning-systems-microtuning.md`)
      Use it when: you need to retune your entire project for a specific scale or temperament; your instruments are out of tune with standard 12-TET; you're working with non-Western or historical tuning systems.
- [ ] **Ableton Live Groove Pool and Swing** (`ableton-using-grooves.md`)
      Use it when: you want to add swing to your drums; you need to make your MIDI notes more human; you're trying to fix timing issues in a vocal track; you want to vary the rhythm of a bass line; you're looking to add a subtle random feel to a synth line.
- [ ] **Ableton Utility Gain and Stereo Control** (`ableton-utility-device.md`)
      Use it when: you need to balance track levels, fix phase issues, adjust stereo width, ensure bass is mono, or check if a track sounds good on mono.
- [ ] **Ableton Velocity Dynamics and Randomization** (`ableton-velocity-midi-effect.md`)
      Use it when: you need to add natural variation to rigid drum hits; you want to smooth out inconsistent MIDI playing; you're trying to prevent soft notes from fading out; you're dealing with harsh velocity spikes in layered sounds; you're looking to make electronic MIDI feel more human.
- [ ] **Ableton Vinyl Distortion Turntable Artifacts** (`ableton-vinyl-distortion-device.md`)
      Use it when: you want to add authentic vinyl texture to lo-fi beats; your tracks need subtle crackle and dust noise; you're emulating a turntable's imperfections; you're looking for dynamic, non-repeating distortion; you're aiming for a warm, analog character in electronic music.
- [ ] **Ableton Vocoder** (`ableton-vocoder.md`)
      Use it when: you want to shape a synth with a vocal; you need a robot voice effect; you're trying to make a talking synth; you're looking to blend speech with a pad or bright sound; you want to create a more mechanical or synthetic vocal texture.
- [ ] **Ableton Warp Modes and Transient Smearing** (`ableton-warp-modes-and-transient-smearing.md`)
      Use it when: you need sharp transients in warped drums; your beats mode is still smearing after a big tempo change; you're working with a full mix that's losing punch; you're trying to keep a vocal line clear after warping; you're dealing with a dense arrangement where transients blur into each other.
- [ ] **Fixing Clicks After Warping A Kick In Ableton** (`ableton-warped-kick-clicks.md`)
      Use it when: your kick has a click after warping; you're unsure if the click is in the clip or the render; you need to keep the attack clean but still warp for timing; the click appears only in real-time but not in an offline render; you're trying to fix a warped transient without changing the sound.
- [ ] **Ableton Wavetable Synthesizer** (`ableton-wavetable-synth.md`)
      Use it when: you need rich, evolving textures; want to create warm analog-style leads; are trying to fix a thin, hollow sound; need a deep, resonant sub foundation; or want to add movement and complexity to a static pad.
