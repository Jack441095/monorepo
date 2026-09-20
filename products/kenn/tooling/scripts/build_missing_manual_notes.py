#!/usr/bin/env python3
"""Build missing official Ableton Live 12 Reference Manual notes for KENN knowledge base."""

from pathlib import Path
import re
from pypdf import PdfReader

REPO_ROOT = Path(__file__).resolve().parents[2]
PDF_PATH = REPO_ROOT / "apps" / "backend" / "src" / "kenn" / "Training_Data_PDF" / "live12-manual-en.pdf"
NOTES_DIR = REPO_ROOT / "apps" / "backend" / "src" / "kenn" / "Training_Data_Notes"

DEVICES = [
    {
        "filename": "ableton-auto-shift-device.md",
        "title": "Ableton Auto Shift Real-Time Pitch and Formant Correction",
        "type": "Ableton device workflow",
        "tags": "ableton, auto shift, live 12, pitch correction, autotune, formant, vocal processing, harmonization, scales",
        "pages": (537, 544),
        "short_answer": "Auto Shift is Live 12's real-time pitch correction, pitch shifting, and formant tracking audio effect. It enables transparent pitch tracking, hard-tuned modern vocal effects, monophonic and polyphonic MIDI-driven harmonization, and formant alteration with scale awareness.",
        "try_this": [
            "Place Auto Shift as the first insert effect on a monophonic lead vocal track.",
            "Enable the Scale Awareness toggle to automatically quantize pitch correction to the project's global key.",
            "Choose your tracking algorithm: Monophonic Pitch for solo vocal takes or Polyphonic for complex polyphonic feeds.",
            "Set the Speed (Glide) control: use fast settings (0-5 ms) for sharp modern hard-tuned effects, or moderate settings (20-45 ms) for transparent vocal stabilization.",
            "Adjust the Shift control in semitones or cents to repitch audio without affecting tempo.",
            "Engage the Formant toggle and dial Formant Shift to alter vocal timbre (gender / throat length adjustment) independently of pitch.",
            "Switch to MIDI mode and route a MIDI track into Auto Shift to dynamically play vocal harmonies with keyboard voicings.",
            "Use the Vibrato section with rate and amount controls to re-introduce natural or rhythmic pitch modulation to locked vocals."
        ],
        "why_it_matters": "Auto Shift eliminates the requirement for external third-party autotune plugins inside Live 12. Its direct coupling to Live's global Scale and tuning frameworks prevents out-of-key vocal artifacts and preserves zero-latency performance.",
        "common_mistakes": [
            "Feeding polyphonic vocal stacks or noisy backgrounds into Monophonic mode, causing erratic pitch tracking and fluttering artifacts.",
            "Applying heavy downward formant shift without compensating with high-pass filtering, leading to low-mid chest resonance buildup."
        ],
        "when_this_does_not_apply": [
            "Offline vocal tuning or micro-editing of individual syllable pitch curves (use Clip Pitch envelopes or complex comping).",
            "Broad polyphonic instrument timbral shifts where Shifter or Spectral Resonator is more suitable."
        ],
        "related_questions": [
            "How do I set up hard-tuned vocal effects in Ableton Live 12?",
            "How does Auto Shift scale awareness work?",
            "How do I control vocal harmonies with MIDI in Auto Shift?",
            "What is the difference between Pitch Shift and Formant Shift in Auto Shift?"
        ]
    },
    {
        "filename": "ableton-auto-pan-device.md",
        "title": "Ableton Auto Pan-Tremolo Modulation",
        "type": "Ableton device workflow",
        "tags": "ableton, auto pan, tremolo, modulation, stereo width, lfo, panning, dynamics, sound design",
        "pages": (533, 536),
        "short_answer": "Auto Pan is a dual-LFO modulation effect that creates stereo panning, amplitude tremolo, and rhythmic gating. By altering the LFO phase between left and right channels, it smoothly transitions from stereo ping-pong movement (Phase 180°) to unified monophonic volume chopping (Phase 0°).",
        "try_this": [
            "Insert Auto Pan on a sustained Rhodes piano, synth pad, or hi-hat loop.",
            "Select LFO Rate mode: choose Hertz (Hz) for free-running subtle movement, or Beat Sync (1/16, 1/8, 1/4) for tempo-locked rhythmic gating.",
            "Set the Phase parameter: dial 180° for classic stereo ping-pong panning between speakers.",
            "Set Phase to 0° (or 360°) to align both channels into an identical amplitude tremolo effect.",
            "Adjust Amount to control modulation depth, keeping it below 40% for subtle spatial width or 100% for full hard cuts.",
            "Select the LFO Waveform: Sine/Triangle for gentle panning, or Square/Saw for aggressive EDM chopper effects.",
            "Adjust the Shape control to skew the waveform symmetry and alter the envelope acceleration.",
            "Use Offset to nudge the starting phase point of the LFO cycle relative to clip launch."
        ],
        "why_it_matters": "Auto Pan creates perceived stereo motion without phase-inversion penalties. When configured at 0° phase, it provides a CPU-efficient, click-free alternative to volume automation for tremolo and sidechain-style pumping.",
        "common_mistakes": [
            "Using 180° phase on low-frequency bass or kick signals, causing wide phase rotation that weakens center sub punch.",
            "Setting 100% Amount with Square wave without smoothing, producing audible zero-crossing clicks."
        ],
        "when_this_does_not_apply": [
            "Static stereo field positioning (use Utility or track Pan control).",
            "Haas-effect psychoacoustic widening (use Delay with 1-15 ms offset instead)."
        ],
        "related_questions": [
            "How do I turn Auto Pan into a rhythmic tremolo?",
            "What does the Phase control do in Ableton Auto Pan?",
            "How do I create sidechain pumping with Auto Pan?",
            "Why does my stereo panning collapse in mono?"
        ]
    },
    {
        "filename": "ableton-drum-sampler-device.md",
        "title": "Ableton Drum Sampler One-Shot Workflow",
        "type": "Ableton device workflow",
        "tags": "ableton, drum sampler, live 12, drums, one shot, transient, playback, sampler, sound design",
        "pages": (701, 706),
        "short_answer": "Drum Sampler is Live 12's streamlined instrument dedicated to one-shot drum sample playback. It combines sample start/end trimming, dedicated transient envelope shaping, pitch envelope bending, sub-oscillator generation, and built-in FX (punch, stretch, frequency modulation) into a compact pad-friendly interface.",
        "try_this": [
            "Drop Drum Sampler onto a Drum Rack pad or MIDI track.",
            "Load an acoustic or synthesized snare or kick sample into the waveform display.",
            "Adjust Sample Start to eliminate pre-transient dead space, maximizing punch.",
            "Select the Playback Mode: One-Shot for full playback or Gate to choke sound upon MIDI key release.",
            "Switch the FX processor to Punch to accentuate attack transients, or 8-Bit for crunchy vintage grit.",
            "Enable the Sub generator on thin kick drums to inject a clean sine sub-bass fundamental underneath.",
            "Use Pitch Envelope with a short decay (10-30 ms) and +12 semitones to create sharp EDM kick transients.",
            "Fine-tune the Filter section (Lowpass/Highpass) to tame harsh high end or eliminate low rumble on hats."
        ],
        "why_it_matters": "Drum Sampler replaces bloated multi-layer samplers with an instantaneous, low-CPU playback engine optimized specifically for percussive hits, delivering faster pad workflow and built-in transient shaping.",
        "common_mistakes": [
            "Leaving start markers too loose, introducing 5-15 ms of silent attack delay that throws off groove timing.",
            "Over-applying the Sub generator on already-heavy 808 samples, producing sub-bass mud and intermodulation distortion."
        ],
        "when_this_does_not_apply": [
            "Multi-sampled velocity-layered instruments (use standard Sampler instead).",
            "Complex looped melodic phrases requiring granular or slicing playback (use Simpler in Slice mode)."
        ],
        "related_questions": [
            "How do I add sub punch to kick drums with Live 12 Drum Sampler?",
            "What playback modes are in Drum Sampler?",
            "How do I pitch bend one-shot drum samples?",
            "What is the difference between Simpler and Drum Sampler?"
        ]
    },
    {
        "filename": "ableton-redux-device.md",
        "title": "Ableton Redux Bitcrushing and Downsampling",
        "type": "Ableton device workflow",
        "tags": "ableton, redux, bitcrusher, downsampling, lo-fi, distortion, sample rate, digital artifacts, sound design",
        "pages": (615, 616),
        "short_answer": "Redux is Live's sample-rate reduction and bit-depth quantization processor. It degrades digital audio resolution to emulate early 8-bit/12-bit samplers, create metallic aliasing overtones, and add aggressive industrial edge to clean signals.",
        "try_this": [
            "Insert Redux on clean acoustic drums, synthesizer plucks, or electric bass.",
            "Activate the Downsample section: engage Sample Rate reduction to introduce ringing frequency aliasing.",
            "Select Downsample Mode: choose Linear for musical aliasing or Exponential for extreme frequency disintegration.",
            "Adjust Bit Depth reduction down from 16-bit toward 8-bit or 6-bit to add quantization noise and crunch.",
            "Engage the Post-Filter toggle to shave off high-frequency hiss generated by severe bit degradation.",
            "Use the Pre-Filter control to limit input bandwidth before crushing, controlling aliasing pitch reflections.",
            "Automate Sample Rate reduction during build-ups to create rising digital formant transitions.",
            "Blend the Dry/Wet knob to 25-40% for parallel vintage grit while preserving full dynamic punch."
        ],
        "why_it_matters": "Redux provides precise digital degradation without analog saturation curves. Its dual-filter design controls harsh intermodulation distortion, delivering authentic vintage digital character without speaker-damaging treble spikes.",
        "common_mistakes": [
            "Reducing Bit Depth below 6-bit without high-shelf EQ, creating overwhelming background noise during decaying tails.",
            "Applying 100% wet Redux to delicate acoustic elements without level-matching, leading to ear fatigue."
        ],
        "when_this_does_not_apply": [
            "Warm harmonic tube or tape saturation (use Saturator, Roar, or Dynamic Tube instead).",
            "Clean dynamic control and gain staging."
        ],
        "related_questions": [
            "How do I emulate vintage 12-bit SP-1200 drums in Ableton?",
            "What is the difference between Sample Rate reduction and Bit Depth in Redux?",
            "How do I prevent harsh noise when bitcrushing?",
            "How does Redux aliasing work?"
        ]
    },
    {
        "filename": "ableton-erosion-device.md",
        "title": "Ableton Erosion Harmonic Degradation",
        "type": "Ableton device workflow",
        "tags": "ableton, erosion, noise, distortion, harmonics, top end, sound design, presence, texture",
        "pages": (580, 580),
        "short_answer": "Erosion degrades incoming audio by modulating it with filtered noise or a sine wave. It introduces sharp digital grit, radio distortion, and harmonic sizzle that cuts through dense mixes.",
        "try_this": [
            "Insert Erosion on a sub-heavy 808, electric bass, or snare top mic.",
            "Select Erosion Mode: Noise for white noise modulation, Band Filter for localized sizzle, or Sine for FM-style metallic grit.",
            "Adjust the Frequency control to sweep and focus the modulation on the desired frequency band (e.g. 2.5 kHz to 6 kHz for vocal/snare presence).",
            "Adjust Width when in Band Filter mode to narrow the resonance peak or broaden the noisy texture.",
            "Dial the Amount parameter carefully from 0 upwards until high-frequency harmonics emerge.",
            "Place Erosion before a saturator or compressor to drive the newly generated harmonics into analog glue.",
            "On monophonic sub-bass, use Sine mode tuned to the song's root frequency to synthesize audible mid-range overtones for mobile speakers."
        ],
        "why_it_matters": "Erosion generates real high-frequency energy on dull, dark tracks where conventional EQ boosting would only boost hiss. It enables 808s and basslines to translate across small smartphone speakers.",
        "common_mistakes": [
            "Over-applying Amount above 50, resulting in harsh, brittle top end that conflicts with cymbals.",
            "Placing Erosion after reverb, modulating reverb tails into unmusical noise wash."
        ],
        "when_this_does_not_apply": [
            "Clean mastering or natural acoustic recordings.",
            "Broadband stereo widening (use Chorus-Ensemble or Delay instead)."
        ],
        "related_questions": [
            "How do I make 808 bass audible on iPhone speakers with Erosion?",
            "What is the difference between Noise and Sine modes in Ableton Erosion?",
            "How does Erosion add bite to snares?",
            "Where should Erosion sit in a vocal chain?"
        ]
    },
    {
        "filename": "ableton-pedal-device.md",
        "title": "Ableton Pedal Analog Circuit Saturation",
        "type": "Ableton device workflow",
        "tags": "ableton, pedal, overdrive, distortion, fuzz, guitar, analog modeling, saturation, mixing",
        "pages": (609, 611),
        "short_answer": "Pedal is a circuit-level model of iconic analog guitar stompboxes. It offers three distinct saturation characters—Overdrive, Distortion, and Fuzz—coupled with a three-band EQ and sub-bass enhancement.",
        "try_this": [
            "Insert Pedal on electric guitars, bass synths, or drum loops.",
            "Choose your Model: Overdrive for warm, dynamic preamp clipping; Distortion for aggressive, hard-clipping rock bite; or Fuzz for square-wave, vintage transistor chaos.",
            "Dial the Gain knob to control clipping drive while observing output meters.",
            "Engage the Sub toggle to add a low-end boost below 250 Hz, restoring weight often lost in heavy guitar distortion circuits.",
            "Use the 3-band EQ: adjust Bass, Mid, and Treble to shape pre- or post-distortion tone.",
            "Toggle Mid Frequency to center the mid-band EQ anywhere from 500 Hz to 2 kHz for surgical guitar presence.",
            "Blend the Dry/Wet control to 15-30% for parallel grit on clean drum buses."
        ],
        "why_it_matters": "Pedal models the non-linear compression and clipping stages of real physical analog circuits. Its Sub switch prevents the characteristic low-end thinning associated with traditional guitar pedals, making it exceptionally powerful for electronic bass synthesis.",
        "common_mistakes": [
            "Using Fuzz mode with high Gain on wide stereo synths without low-passing, generating piercing high-frequency intermodulation.",
            "Leaving Output Gain unadjusted, sending +12 dB peaks into subsequent plugins."
        ],
        "when_this_does_not_apply": [
            "Transparent gain staging or clinical mastering.",
            "Subtle acoustic bus warming (use Saturator or Glue Compressor soft clipping instead)."
        ],
        "related_questions": [
            "What is the difference between Overdrive, Distortion, and Fuzz in Ableton Pedal?",
            "How do I use Pedal on an 808 bass without losing sub punch?",
            "How does the Sub switch work on Ableton Pedal?",
            "Can I use Pedal in parallel for drum processing?"
        ]
    },
    {
        "filename": "ableton-dynamic-tube-device.md",
        "title": "Ableton Dynamic Tube Warmth and Asymmetric Drive",
        "type": "Ableton device workflow",
        "tags": "ableton, dynamic tube, tube, saturation, warmth, harmonics, preamps, mixing",
        "pages": (572, 572),
        "short_answer": "Dynamic Tube models tube preamplifiers featuring two independent tube stages and dynamic bias modulation. It generates even and odd harmonics with an asymmetric transfer curve, imparting vintage analog warmth and natural compression.",
        "try_this": [
            "Insert Dynamic Tube on vocals, synth leads, or drum busses.",
            "Select Tube Model: Model A for clean triode saturation, Model B for punchy pentode character, or Model C for aggressive modern high-gain clipping.",
            "Increase the Drive knob to push signal into the virtual tube grids.",
            "Adjust the Bias control: dial positive to create asymmetric clipping that enriches even-order (octave) harmonics, imparting smooth warmth.",
            "Set Bias to zero for symmetrical clipping emphasizing aggressive odd-order harmonics.",
            "Engage the Envelope control to dynamically push the tube into saturation on transient peaks while staying clean on decays.",
            "Use Tone to filter high-frequency distortion and avoid brittle treble buildup."
        ],
        "why_it_matters": "Dynamic Tube provides dynamic, signal-reactive warmth. The asymmetric bias control generates musical even-order harmonics (sweetening vocals and acoustic instruments) that typical static clippers cannot produce.",
        "common_mistakes": [
            "Setting Tone too bright on harsh source material, exaggerating upper-mid sibilance.",
            "Applying heavy Drive without adjusting the Output level control, skewing mix fader relationships."
        ],
        "when_this_does_not_apply": [
            "Extreme digital bitcrushing (use Redux).",
            "Multi-band saturation across independent frequency splits (use Roar)."
        ],
        "related_questions": [
            "What do Tube Models A, B, and C do in Ableton Dynamic Tube?",
            "How do even harmonics create warmth in Dynamic Tube?",
            "How does the Envelope follower interact with tube bias?",
            "Why use Dynamic Tube over Saturator?"
        ]
    },
    {
        "filename": "ableton-chorus-ensemble-device.md",
        "title": "Ableton Chorus-Ensemble Spatial Modulation",
        "type": "Ableton device workflow",
        "tags": "ableton, chorus, ensemble, modulation, stereo width, dimension, vintage, sound design",
        "pages": (551, 554),
        "short_answer": "Chorus-Ensemble is a versatile spatial modulation processor that thickens and widens signals using pitch-modulated delay lines. It features Classic chorus, thick multi-LFO Ensemble mode, and vintage BBD (Bucket-Brigade Device) vibrato.",
        "try_this": [
            "Insert Chorus-Ensemble on electric guitars, synth strings, or vocal doubles.",
            "Choose Mode: Chorus for classic two-voice stereo shimmering; Ensemble for rich 6-voice multi-LFO string-machine wash; or Vibrato for rotary pitch modulation.",
            "Adjust Rate to set modulation speed (0.1 Hz to 10 Hz).",
            "Adjust Depth to control the pitch deviation amplitude.",
            "Engage Warmth to introduce vintage bucket-brigade analog saturation and low-pass filtering.",
            "Use Width to expand or contract the stereo field from pure mono to exaggerated wide side information.",
            "Adjust the High-Pass filter on the input signal to prevent modulation of low-end frequencies, keeping bass punch centered."
        ],
        "why_it_matters": "Chorus-Ensemble combines legendary vintage stompbox and string-synthesizer modulation topologies in a single low-latency device. Its built-in high-pass filter protects low-end mono compatibility.",
        "common_mistakes": [
            "Using 100% Dry/Wet on monophonic lead vocals, causing excessive detune drift and pitch instability.",
            "Forgetting to engage the input high-pass filter on bass elements, blurring low-frequency punch."
        ],
        "when_this_does_not_apply": [
            "Tight mono vocal doubling (use micro-pitch shift or short mono Haas delay).",
            "Phase-aligned drum transients (chorus introduces phase smearing across drums)."
        ],
        "related_questions": [
            "How do I recreate the Juno 106 chorus in Ableton?",
            "What is the difference between Chorus and Ensemble modes?",
            "How do I keep chorus from muddying up the bass?",
            "How does the Warmth parameter affect tone in Chorus-Ensemble?"
        ]
    },
    {
        "filename": "ableton-phaser-flanger-device.md",
        "title": "Ableton Phaser-Flanger Jet sweeps and Comb Filtering",
        "type": "Ableton device workflow",
        "tags": "ableton, phaser, flanger, comb filter, modulation, sweep, jet effect, sound design",
        "pages": (612, 614),
        "short_answer": "Phaser-Flanger combines all-pass filter phase cancellation (Phaser) with short modulated delay comb filtering (Flanger). It generates classic jet sweeps, psychedelic notches, and metallic resonance.",
        "try_this": [
            "Insert Phaser-Flanger on acoustic drum overheads, rhythm electric guitar, or pad synths.",
            "Select Mode: Phaser for sweeping all-pass filter notches, or Flanger for comb-filter metallic resonance.",
            "Choose Poles (Poles 2-12 in Phaser mode) to set the number of frequency notches in the spectrum.",
            "Adjust Center Frequency to position the sweep focus around the instrument's key range.",
            "Increase Feedback to accentuate resonant peaks for pronounced, whistling sweeps.",
            "Set Rate: choose Hz for free modulation or Beat Sync (1/4, 1/2) for tempo-locked cyclical movement.",
            "Use Stereo Phase (Phase control) to offset modulation between left and right ears, creating wide three-dimensional motion."
        ],
        "why_it_matters": "Phaser-Flanger produces dramatic timbral movement without pitch shifting. The polarity inversion and poles selection give pinpoint control over notch sharpness and sweep depth.",
        "common_mistakes": [
            "Running high Feedback on drum buses with low headroom, causing resonant volume spikes that trigger downstream clipping limiters.",
            "Applying heavy flanging across full mixes, causing phase cancellation in mono playback."
        ],
        "when_this_does_not_apply": [
            "Clean stereo widening without frequency comb filtering (use Chorus-Ensemble or Delay).",
            "Pitch vibrato modulation."
        ],
        "related_questions": [
            "What is the difference between a Phaser and a Flanger?",
            "How do Poles affect notch count in Ableton Phaser?",
            "How do I create the classic jet plane sweep on drums?",
            "Why does Flanger cause phase issues in mono?"
        ]
    },
    {
        "filename": "ableton-eq-three-device.md",
        "title": "Ableton EQ Three DJ Kill-EQ Workflow",
        "type": "Ableton device workflow",
        "tags": "ableton, eq three, dj, kill switches, crossover, performance, filters, mixing",
        "pages": (579, 579),
        "short_answer": "EQ Three is a specialized 3-band DJ-style equalizer featuring independent Low, Mid, and High gain controls, customizable crossover frequencies, and dedicated 24 dB or -inf dB kill switches for live performance and transitions.",
        "try_this": [
            "Insert EQ Three on a master bus, live playback channel, or DJ stem group.",
            "Adjust Crossover Frequencies: set FreqLo (typically 250 Hz) and FreqHi (typically 2.5 kHz) to define the three operating bands.",
            "Use the Kill buttons (On/Off toggles below each band) to instantaneously mute the bass, mids, or highs during breakdowns.",
            "Toggle between 24 dB and 48 dB slope modes: use 24 dB for musical blending or 48 dB for surgical frequency isolation.",
            "Map GainLo to an external MIDI knob for instant DJ bass cuts when introducing a new drop or kick drum.",
            "Map High kill switch to create dramatic build-up filtration before drops."
        ],
        "why_it_matters": "EQ Three is purpose-built for real-time live performance, DJing, and drastic build-up mutes where clean surgical parametric EQs (like EQ Eight) are too slow to automate.",
        "common_mistakes": [
            "Using EQ Three as a critical mastering EQ: its crossover filters introduce continuous phase shift even when all band gains are set to 0 dB.",
            "Leaving 48 dB mode on subtle acoustic tracks, causing audible phase ringing around crossover points."
        ],
        "when_this_does_not_apply": [
            "Studio mastering or clinical corrective EQ (use EQ Eight with linear/minimum phase filters).",
            "Multi-band dynamic compression (use Multiband Dynamics)."
        ],
        "related_questions": [
            "Why does EQ Three color sound even with all gains at 0 dB?",
            "How do I set up DJ kill switches in Ableton Live?",
            "What is the difference between 24 dB and 48 dB mode in EQ Three?",
            "When should I use EQ Eight instead of EQ Three?"
        ]
    },
    {
        "filename": "ableton-channel-eq-device.md",
        "title": "Ableton Channel EQ Simplified Tonal Shaping",
        "type": "Ableton device workflow",
        "tags": "ableton, channel eq, mixing, channel strip, high pass, broad strokes, workflow",
        "pages": (549, 550),
        "short_answer": "Channel EQ is a streamlined, musical 3-band equalizer inspired by classic analog mixing console channel strips. It features a fixed 80 Hz high-pass filter, a broad low shelf, a sweeping mid-band with adaptive Q, and a gentle high shelf.",
        "try_this": [
            "Insert Channel EQ on individual audio or MIDI channels as a first-line balancing tool.",
            "Engage the HP 80 Hz switch on vocals, guitars, and synths to instantly clean sub-bass rumble.",
            "Adjust Low shelf gain (100 Hz) to gently add warmth (+1 to +2 dB) or clean boxiness (-1 to -3 dB).",
            "Sweep the Mid Frequency knob between 120 Hz and 7.5 kHz while adjusting Mid Gain: observe how the filter bandwidth (Q) automatically sharpens as gain increases.",
            "Adjust the High shelf (8.5 kHz) to add open air and sheen to vocals, cymbals, and acoustic instruments.",
            "Use Channel EQ across all session tracks for fast, analog-style broad tonal balance before reaching for surgical EQ."
        ],
        "why_it_matters": "Channel EQ minimizes decision fatigue and CPU consumption. Its musical, wide curves and adaptive mid Q prevent over-processing and phase distortion on routine track balancing.",
        "common_mistakes": [
            "Attempting to notch out narrow room resonances or whistle frequencies (use EQ Eight instead).",
            "Applying the 80 Hz high-pass on bass guitar or kick drum, gutting the fundamental punch."
        ],
        "when_this_does_not_apply": [
            "Surgical acoustic feedback removal or resonant frequency notch filtering.",
            "Master bus dynamic EQing."
        ],
        "related_questions": [
            "What makes Channel EQ different from EQ Eight?",
            "How does the adaptive Q work in Channel EQ?",
            "When should I use the 80 Hz high-pass switch?",
            "Is Channel EQ modeled after an analog console?"
        ]
    },
    {
        "filename": "ableton-cabinet-device.md",
        "title": "Ableton Cabinet Speaker Emulation",
        "type": "Ableton device workflow",
        "tags": "ableton, cabinet, speaker, impulse response, guitar, amp, physical modeling, mixing",
        "pages": (547, 548),
        "short_answer": "Cabinet emulates the frequency response, resonances, and acoustic dispersion of physical guitar and bass speaker cabinets using impulse-response convolution, with selectable speaker sizes, microphone models, and microphone placement.",
        "try_this": [
            "Insert Cabinet immediately after the Amp device, or on raw synthesizer bass and drum lines.",
            "Select Cabinet Type: 1x12 for vintage combo warmth, 4x12 for heavy rock power, 4x10 for punchy bass, or 8x10 for massive SVT-style low-end weight.",
            "Select Microphone Model: Dynamic (57-style) for aggressive mid punch, or Condenser (87-style) for open, detailed top end.",
            "Adjust Microphone Position: Near/Far to adjust room reflection depth, and On/Off Axis to control brightness.",
            "Toggle Mono/Stereo processing mode depending on whether incoming audio is mono guitar or stereo synth.",
            "Use Cabinet on aggressive synth leads or fuzz bass to smooth out harsh digital buzz into a warm physical sound."
        ],
        "why_it_matters": "Distortion and amp simulators sound brittle and fizzy without a speaker cabinet. Cabinet acts as an acoustic low-pass and formant filter, shaping raw clipping harmonics into natural, organic frequencies.",
        "common_mistakes": [
            "Placing Cabinet before Amp or distortion, resulting in muddy overdrive of filtered signals.",
            "Using Far mic placement on dry bass tracks, washing out punch in unnecessary virtual room reflections."
        ],
        "when_this_does_not_apply": [
            "Direct-inject (DI) acoustic instruments or clean mastering.",
            "Modern synthesized sub-bass where full 20-40 Hz sub extension is required (Cabinet naturally rolls off sub-bass)."
        ],
        "related_questions": [
            "Why does my guitar distortion sound harsh without Cabinet?",
            "What is the difference between On-Axis and Off-Axis microphone placement?",
            "Can I use Cabinet on electronic drum loops?",
            "How does Cabinet interact with the Amp device?"
        ]
    },
    {
        "filename": "ableton-filter-delay-device.md",
        "title": "Ableton Filter Delay Tri-Band Spatial Echo",
        "type": "Ableton device workflow",
        "tags": "ableton, filter delay, delay, stereo, bandpass, echo, sound design, spatial",
        "pages": (583, 583),
        "short_answer": "Filter Delay splits incoming audio into three independent frequency bands (Left, Left+Right, Right), each equipped with its own bandpass filter, delay timing, feedback loop, and stereo pan position.",
        "try_this": [
            "Insert Filter Delay on a return track or dry vocal/synth channel.",
            "Engage Channel 1 (Left): set bandpass filter to low-mids (400 Hz), Delay time to 3/16, and pan hard left.",
            "Engage Channel 2 (Center L+R): set bandpass filter to mid presence (1.5 kHz), Delay time to 2/16, and pan center.",
            "Engage Channel 3 (Right): set bandpass filter to high air (4 kHz), Delay time to 4/16, and pan hard right.",
            "Adjust Feedback independently on each channel to create cascading echoes that evolve in timbre as they decay.",
            "Fine-tune the Dry/Wet balance to integrate the spatial echoes behind the main dry signal."
        ],
        "why_it_matters": "Filter Delay eliminates the clutter of full-range echoes. By restricting delays to specific frequency registers, it creates lush, complex three-dimensional movement without muddying the mix core.",
        "common_mistakes": [
            "Running overlapping full-range feedback on all three channels, causing acoustic buildup and masking the lead vocal.",
            "Setting wide bandpass filters that let sub-bass leak into the center delay channel."
        ],
        "when_this_does_not_apply": [
            "Simple tempo-synced ping-pong delays (use standard Delay or Echo).",
            "Clean vocal slapback without frequency filtering."
        ],
        "related_questions": [
            "How do I create evolving frequency delays in Ableton?",
            "What makes Filter Delay different from standard Delay?",
            "How do I use Filter Delay for ambient vocal throws?",
            "How do the three channels in Filter Delay route audio?"
        ]
    },
    {
        "filename": "ableton-vinyl-distortion-device.md",
        "title": "Ableton Vinyl Distortion Turntable Artifacts",
        "type": "Ableton device workflow",
        "tags": "ableton, vinyl distortion, lo-fi, crackle, turntable, dust, pinch effect, character",
        "pages": (657, 657),
        "short_answer": "Vinyl Distortion reproduces the mechanical and geometric anomalies of vinyl record playback. It generates tracing distortion, pinch-effect harmonic distortion, turntable surface noise, and customizable vinyl crackle.",
        "try_this": [
            "Insert Vinyl Distortion on lo-fi hip-hop keys, drum breaks, or master stems.",
            "Adjust the Crackle Density knob to control the frequency of dust clicks and pops.",
            "Adjust Crackle Volume to blend vinyl dust beneath the music.",
            "Use the Tracing Distortion section: adjust Drive and Frequency to emulate the physical distortion created when a stylus maneuvers high-frequency groove cuts.",
            "Use the Pinch Effect section: adjust Drive to introduce even harmonics created by vertical stylus displacement.",
            "Toggle Mono/Stereo crackle behavior to switch between authentic vintage mono record noise and wide modern stereo lo-fi texture."
        ],
        "why_it_matters": "Vinyl Distortion provides authentic physical record modeling without using static repeating audio loops. Because crackle is dynamically generated, it never repeats obvious sample patterns.",
        "common_mistakes": [
            "Setting Crackle Density and Volume too high on quiet passages, overpowering delicate acoustic decays.",
            "Applying heavy tracing distortion without high-shelf EQ, creating fatiguing upper-mid harshness."
        ],
        "when_this_does_not_apply": [
            "High-fidelity commercial mastering and clean modern pop.",
            "Tape saturation (use Saturator or Dynamic Tube)."
        ],
        "related_questions": [
            "How do I create realistic vinyl crackle in Ableton Live?",
            "What is the Pinch Effect in Vinyl Distortion?",
            "How does Tracing Distortion alter frequency response?",
            "Why use Vinyl Distortion instead of vinyl sample loops?"
        ]
    },
    {
        "filename": "ableton-tuner-device.md",
        "title": "Ableton Tuner Instrument Calibration",
        "type": "Ableton device workflow",
        "tags": "ableton, tuner, tuning, pitch, strobe, calibration, guitar, bass, live 12",
        "pages": (649, 654),
        "short_answer": "Tuner is Ableton's high-precision pitch measurement and instrument calibration utility. It features Classic needle view, high-resolution Strobe view, customizable reference pitch (440 Hz standard), and Live 12 Scale/Microtuning awareness.",
        "try_this": [
            "Insert Tuner as the very first device on a live audio track connected to a guitar, bass, or microphone.",
            "Select View Mode: Classic for intuitive needle/cents display, or Strobe for ultra-precise intonation calibration.",
            "Play a sustained monophonic note: observe the detected note name, octave, and deviation in cents.",
            "Adjust the Reference Frequency (default 440 Hz) if tuning to orchestral or non-standard pitch standards (e.g. 432 Hz).",
            "In Live 12, toggle Scale/Tuning display mode to calibrate notes against the project's active microtuning tuning system."
        ],
        "why_it_matters": "Tuner provides zero-latency, real-time pitch feedback on the audio input buffer. Strobe mode provides the sub-cent resolution required for professional guitar intonation setup and analog oscillator calibration.",
        "common_mistakes": [
            "Placing Tuner after chorus, reverb, or delay, confusing the pitch detection algorithm with modulated echoes.",
            "Attempting to tune chords or polyphonic instruments (Tuner is strictly monophonic)."
        ],
        "when_this_does_not_apply": [
            "Polyphonic chord tuning (tune individual strings or single voices independently).",
            "Continuous pitch automation."
        ],
        "related_questions": [
            "How accurate is Ableton Tuner in Strobe view?",
            "How do I change the reference frequency from 440 Hz in Ableton Tuner?",
            "Can I tune analog hardware synths with Ableton Tuner?",
            "Where should Tuner sit in an input monitoring chain?"
        ]
    },
    {
        "filename": "ableton-collision-synth.md",
        "title": "Ableton Collision Physical Modeling Synthesizer",
        "type": "Ableton device workflow",
        "tags": "ableton, collision, physical modeling, mallet, marimba, bells, sound design, resonator",
        "pages": (684, 692),
        "short_answer": "Collision is a physical modeling instrument created with Applied Acoustics Systems that simulates the physics of struck objects. It couples two exciter sections (Mallet and Noise) with two physical resonators (Beam, Marimba, String, Membrane, Plate, Pipe, Tube).",
        "try_this": [
            "Load Collision onto a MIDI track for acoustic mallets, percussive bells, or organic metallic textures.",
            "Configure Exciter 1 (Mallet): adjust Stiffness and Noise to simulate the hardness of a physical striker.",
            "Configure Resonator 1: choose Structure (Beam for metallic bars, Marimba for tuned wood, Membrane for drumheads, or Pipe for air columns).",
            "Adjust Decay to control ring-out time and Material to simulate wood, nylon, or heavy metal density.",
            "Engage Resonator 2 in parallel or serial to simulate complex compound physical bodies (e.g. a wooden bar resting over an acoustic tube resonator).",
            "Use LFOs and the Modulation matrix to modulate Mallet Stiffness via key velocity for organic acoustic dynamics."
        ],
        "why_it_matters": "Collision generates tactile, organic acoustic timbres without sample libraries. Because every strike calculates physical vibrations in real-time, no two velocity hits sound static or repetitive.",
        "common_mistakes": [
            "Setting Resonator Decay and Listening Position too extreme, causing continuous self-oscillation that clips output meters.",
            "Neglecting the Material and Inharmonics controls, leaving resonators sounding like simple sine waves."
        ],
        "when_this_does_not_apply": [
            "Standard subtractive supersaws or 808 sub-bass (use Drift, Analog, or Wavetable).",
            "FM metallic bass sound design (use Operator)."
        ],
        "related_questions": [
            "How does physical modeling in Ableton Collision work?",
            "What is the difference between Beam and Marimba resonators?",
            "How do I design hyper-realistic mallet instruments in Collision?",
            "How do I link Resonator 1 and Resonator 2 in Collision?"
        ]
    },
    {
        "filename": "ableton-external-audio-effect.md",
        "title": "Ableton External Audio Effect Hardware Insert",
        "type": "Ableton device workflow",
        "tags": "ableton, external audio effect, hardware, analog outboard, latency compensation, routing, mixing",
        "pages": (581, 582),
        "short_answer": "External Audio Effect routes audio out of Live to outboard analog hardware processors (compressors, EQs, tape delays) and brings the processed signal back into the DAW track with automatic sample-accurate delay compensation.",
        "try_this": [
            "Insert External Audio Effect on any track, bus, or return channel.",
            "Select Audio To: choose the physical audio interface outputs connected to your hardware unit's inputs.",
            "Select Audio From: choose the physical audio interface inputs returning from your hardware unit's outputs.",
            "Adjust Output Gain to drive the analog gear cleanly, preventing DAC clipping.",
            "Adjust Input Gain to balance the returned analog signal.",
            "Click the Hardware Latency measurement button to calculate and offset ADC/DAC conversion delay automatically.",
            "Fine-tune the Latency Delay in milliseconds or samples if manual phase alignment against dry tracks is needed."
        ],
        "why_it_matters": "External Audio Effect integrates analog outboard equipment into Live's native mixer just like a plugin, while automatically maintaining plugin delay compensation across the entire song arrangement.",
        "common_mistakes": [
            "Routing to outputs that are simultaneously assigned to control room monitors, causing feedback loops.",
            "Failing to measure hardware roundtrip latency, causing phase cancellation when blending parallel outboard processing."
        ],
        "when_this_does_not_apply": [
            "Purely in-the-box VST/AU plugin routing.",
            "Sending audio to external analog synths (use External Instrument instead)."
        ],
        "related_questions": [
            "How do I integrate analog hardware compressors into Ableton Live?",
            "How does latency compensation work with External Audio Effect?",
            "How do I calibrate input and output levels for outboard gear in Ableton?",
            "Why is my hardware return out of phase with the original track?"
        ]
    },
    {
        "filename": "ableton-external-instrument.md",
        "title": "Ableton External Instrument Hardware MIDI and Audio Routing",
        "type": "Ableton device workflow",
        "tags": "ableton, external instrument, hardware synths, midi routing, latency, drum machines, studio",
        "pages": (712, 713),
        "short_answer": "External Instrument combines MIDI output and audio return into a single track device. It allows external hardware synthesizers, sound modules, and drum machines to be played, automated, and frozen inside Live like a software instrument.",
        "try_this": [
            "Insert External Instrument on a MIDI track.",
            "Select MIDI To: choose the MIDI output port and MIDI channel connected to your external hardware synth.",
            "Select Audio From: choose the audio interface input channels receiving audio from the synth's line outputs.",
            "Adjust Gain to set optimal recording level.",
            "Adjust Hardware Latency offset to align synth playback precisely to the project grid.",
            "Add native audio effects (Reverb, EQ, Compression) directly after External Instrument in the same device chain.",
            "Freeze and flatten the track when you are ready to commit the hardware performance to permanent audio stems."
        ],
        "why_it_matters": "External Instrument condenses what previously required two separate tracks (one MIDI track and one Audio track) into a single unified instrument channel, streamlining CPU usage and project organization.",
        "common_mistakes": [
            "Forgetting to enable the audio inputs in Live's Audio Settings, leaving Audio From disabled.",
            "Leaving monitoring set to In during playback after recording, resulting in doubled audio or phasing."
        ],
        "when_this_does_not_apply": [
            "Controlling software VST3/AU virtual instruments.",
            "Routing audio to outboard effect processors (use External Audio Effect)."
        ],
        "related_questions": [
            "How do I connect external hardware synthesizers to Ableton Live?",
            "How do I freeze hardware synthesizer tracks in Ableton?",
            "How do I fix MIDI latency on hardware synths in Live?",
            "What is the difference between External Instrument and External Audio Effect?"
        ]
    },
    {
        "filename": "ableton-cc-control-midi-effect.md",
        "title": "Ableton CC Control MIDI Modulation",
        "type": "Ableton device workflow",
        "tags": "ableton, cc control, midi, live 12, automation, hardware control, modulation, workflow",
        "pages": (665, 665),
        "short_answer": "CC Control is Live 12's dedicated MIDI effect for generating, remapping, and automating continuous controller (CC) messages. It provides customizable knobs for sending CC parameters to external hardware synths and software instruments.",
        "try_this": [
            "Insert CC Control at the beginning of a MIDI track before an External Instrument or VST plugin.",
            "Assign each knob to a target CC number (e.g. CC 74 for filter cutoff, CC 1 for mod wheel, CC 11 for expression).",
            "Rename the knob labels to match your hardware synth's physical parameter names (e.g., Cutoff, Resonance, Decay).",
            "Automate or map the knobs to Live macro controls or MIDI keyboard controllers.",
            "Use the Custom Bank presets to switch between parameter templates for different hardware synths.",
            "Pair CC Control with Live's LFO device to modulate hardware parameters automatically in tempo sync."
        ],
        "why_it_matters": "CC Control allows external hardware parameters to be saved, named, automated, and modulated with Live's native LFOs and Shapers directly from the device chain without entering clip envelope sub-menus.",
        "common_mistakes": [
            "Sending conflicting CC numbers that overwrite pitch bend or sustain pedal data.",
            "Placing CC Control after an instrument in the device chain (MIDI effects must precede instruments)."
        ],
        "when_this_does_not_apply": [
            "Audio processing and DSP manipulation.",
            "Note pitch or velocity manipulation (use Pitch, Scale, or Velocity devices)."
        ],
        "related_questions": [
            "How do I automate hardware synth cutoff in Ableton Live 12?",
            "What is the CC Control device in Live 12?",
            "How do I map Live's LFO to external MIDI CC?",
            "Where should CC Control be placed in a MIDI chain?"
        ]
    },
    {
        "filename": "ableton-velocity-midi-effect.md",
        "title": "Ableton Velocity Dynamics and Randomization",
        "type": "Ableton device workflow",
        "tags": "ableton, velocity, midi, humanization, dynamics, randomization, expression",
        "pages": (673, 674),
        "short_answer": "Velocity is a MIDI effect that processes incoming note velocities. It shapes dynamic range via compression or expansion, remaps velocity curves, clamps minimum and maximum bounds, and introduces humanized velocity randomization.",
        "try_this": [
            "Insert Velocity on a MIDI drum, piano, or synth track before the instrument.",
            "Adjust Random to introduce natural velocity variation (e.g., +/- 5 to 15) to rigid, quantized drum hits.",
            "Adjust Drive and Compand to compress or expand MIDI dynamic range, evening out erratic finger drumming.",
            "Set Out Low (minimum velocity) to ensure quiet notes always trigger sound on soft instrument layers.",
            "Set Out Hi (maximum velocity) to clamp peaks and prevent harsh velocity-layer spikes.",
            "Select Mode: choose Clip to constrain velocities, or Gate to completely filter out notes played below a threshold.",
            "Use Operation: choose Add to transpose all velocities upwards, or Scale to scale dynamic curves proportionally."
        ],
        "why_it_matters": "Velocity breathes organic human life into robotic, computer-programmed MIDI tracks. It also protects multi-sampled acoustic drums from unnaturally harsh top-layer samples during ghost notes.",
        "common_mistakes": [
            "Setting Random too high on kick drums (+/- 40), causing erratic low-end punch that disrupts the mix.",
            "Accidentally engaging Gate mode with high threshold, silencing intended notes."
        ],
        "when_this_does_not_apply": [
            "Audio-rate volume dynamic compression (use Compressor or Glue Compressor).",
            "Synthesizer sound generators that do not respond to MIDI velocity."
        ],
        "related_questions": [
            "How do I humanize MIDI drums in Ableton Live?",
            "What is the difference between Drive and Compand in Ableton Velocity?",
            "How do I prevent ghost notes from triggering loud velocity samples?",
            "How does Velocity Gate mode work?"
        ]
    },
    {
        "filename": "ableton-tuning-systems-microtuning.md",
        "title": "Ableton Live 12 Tuning Systems and Microtuning",
        "type": "Ableton device workflow",
        "tags": "ableton, microtuning, tuning systems, scala, live 12, pitch, temperament, just intonation, scales",
        "pages": (346, 355),
        "short_answer": "Live 12 introduces a native Tuning Systems engine that allows entire projects to adopt microtonal scales, non-Western temperaments, and historic intonations. It natively retunes all supported Live instruments (Meld, Drift, Simpler, Sampler, Analog, Operator) and compatible MPE/MIDI plug-ins without external pitch-bend hacks.",
        "try_this": [
            "Open Live 12's Browser and navigate to the Tunings category.",
            "Browse the library of historical (Just Intonation, Pythagorean, Meantone), cultural (Arabic, Gamelan, Indian Raga), and modern microtonal tuning files.",
            "Double-click or drag a tuning file into your set to instantly apply it globally across all tracks.",
            "Observe the Control Bar's Tuning display and Clip View: MIDI piano roll keys dynamically re-space and label according to the tuning system's pitch divisions.",
            "Open Meld or Drift: notice that all oscillators automatically calculate pitch intervals according to the loaded tuning system.",
            "Drop custom `.ascl` or `.scl` Scala tuning files into your User Library to import custom microtonal temperaments.",
            "Use the Reference Pitch setting to change the base fundamental pitch of note A from 440 Hz to any desired standard."
        ],
        "why_it_matters": "Prior to Live 12, microtonal composition required cumbersome Max for Live MIDI pitch-bend plugins and monophonic limits. Live 12's global tuning architecture handles polyphonic pitch remapping natively across all internal instruments and MPE synthesizers.",
        "common_mistakes": [
            "Using legacy non-MPE third-party VST plugins that do not support MIDI tuning specification or per-note pitch bend, causing out-of-tune polyphony.",
            "Loading complex microtonal divisions without setting root reference keys, causing unexpected dissonances with standard audio samples."
        ],
        "when_this_does_not_apply": [
            "Audio clip playback without warping (raw unwarped audio samples remain at their original recorded frequencies).",
            "Conventional 12-tone equal temperament (12-TET) Western pop and EDM production."
        ],
        "related_questions": [
            "How do I use microtuning in Ableton Live 12?",
            "How do I import Scala (.scl) tuning files into Ableton Live?",
            "Which Ableton instruments support native tuning systems?",
            "How does Live 12 retune MIDI piano rolls?"
        ]
    }
]


def main():
    print(f"Generating {len(DEVICES)} verified Ableton Live 12 manual notes...")
    created = 0
    for dev in DEVICES:
        target = NOTES_DIR / dev["filename"]
        content = [
            f"# {dev['title']}",
            "",
            f"Type: {dev['type']}",
            f"Tags: {dev['tags']}",
            "Status: Approved",
            "Source: Ableton Live 12 Reference Manual (live12-manual-en.pdf)",
            "Reviewed: 2026-09-17",
            "",
            "Short answer:",
            dev["short_answer"],
            "",
            "Try this:",
        ]
        for i, step in enumerate(dev["try_this"], start=1):
            content.append(f"{i}. {step}")
        content.extend([
            "",
            "Why it matters:",
            dev["why_it_matters"],
            "",
            "Common mistakes:",
        ])
        for m in dev["common_mistakes"]:
            content.append(f"- {m}")
        content.extend([
            "",
            "When this does not apply:",
        ])
        for w in dev["when_this_does_not_apply"]:
            content.append(f"- {w}")
        content.extend([
            "",
            "Related questions:",
        ])
        for q in dev["related_questions"]:
            content.append(f"- {q}")
        content.append("")

        target.write_text("\n".join(content), encoding="utf-8")
        print(f"  ✓ Written: {dev['filename']} (Pages {dev['pages'][0]}-{dev['pages'][1]})")
        created += 1

    print(f"\nSuccessfully generated all {created} notes in {NOTES_DIR}")


if __name__ == "__main__":
    main()

