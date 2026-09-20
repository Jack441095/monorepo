# Wwise Conversion Loop Clicks Sample Rate And Restarting Events

Type: Game audio troubleshooting workflow
Tags: wwise, ableton, game audio, loop, loops, seamless in ableton, click, clicks, conversion, converted, sample rate, sample-rate, resample, codec, wav, source wav, clean wav, streaming, loop point, zero crossing, crossfade, platform, restarting event, restart, continuous, ambience, troubleshooting
Status: Approved
Source title: Ableton Live 12 Manual - Audio Clips, Tempo, and Warping; Wwise 101
Source creator: Ableton and Audiokinetic
Source URL: https://www.ableton.com/en/live-manual/12/audio-clips-tempo-and-warping/

Short answer:
If a loop is clean in Ableton but clicks after Wwise conversion, compare the source WAV against the converted platform asset. Check loop points, codec, sample-rate conversion, streaming chunking, and whether Wwise is restarting an Event instead of looping one continuous sound.

Restarting Events:
For continuous ambience, let Wwise loop the sound continuously when possible instead of repeatedly restarting the ambience Event from the game. Reposting an Event can create audible seams, retrigger fades, reset randomization, or stack voices depending on the implementation.

Try this:
1. Prove the exported WAV loops cleanly by re-importing it into Ableton and looping it for a minute.
2. Confirm the file starts and ends at the intended loop boundaries with no hidden silence or tail cutoff.
3. Check the source and target sample rates; avoid unnecessary resampling when the project has an agreed delivery rate.
4. Review Wwise conversion settings for the target platform, especially codec, sample rate, channel count, and streaming behavior.
5. If the converted preview clicks but the source WAV does not, test a PCM conversion to separate codec artifacts from edit problems.
6. Inspect whether implementation is repeatedly posting the Event instead of letting Wwise loop the sound.
7. For ambience, prefer a slightly longer natural loop over a tiny loop that exposes the seam on every repeat.
8. Document BPM, loop length, source sample rate, intended Wwise looping behavior, and whether the asset is meant to stream.

Check:
Do not add a limiter to hide a loop click. Fix the edit, conversion, or implementation loop behavior.

Why it matters:
Conversion can reveal weak loop boundaries or introduce platform-specific artifacts. KENN should ask whether the source, converted asset, and runtime behavior all loop the same way.

Related questions:
- My loop is seamless in Ableton but clicks after Wwise conversion.
- Can sample-rate conversion make a Wwise loop click?
- Should Wwise restart my ambience Event or loop it continuously?
- Should my game keep restarting a Wwise ambience Event or let Wwise loop the sound continuously?
