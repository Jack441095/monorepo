Type: Game audio optimization
Tags: wwise, excessive cpu, cpu capture, cpu profiler, four cpu areas, physical voices, effects, codecs, pcm, vorbis, spatial audio, platform conversion
Status: Approved
Source title: Optimizing CPU Usage
Source creator: Audiokinetic
Source URL: https://www.audiokinetic.com/en/public-library/2024.1.8_8893/?id=optimizing_cpu&source=Help
Source version: Wwise 2024.1.8
Reviewed: 2026-07-01

# Wwise CPU, Codec, and Effects Optimization


Short answer:
Optimize Wwise CPU from profiler evidence. The main levers are concurrent physical voices, Effect instances, codec decoding, and Spatial Audio calculations; each must be tested on the target platform.

Try this:
1. Capture a repeatable worst-case scene and identify whether the peak comes from voices, effects, decoding, or spatial processing.
2. Reduce unnecessary physical voices with finite attenuation, playback limits, priority, and suitable virtual behavior.
3. Share bus Effects where sound design allows instead of instantiating the same processing on many voices.
4. Choose codecs per platform: PCM trades storage for low decode cost, while compressed formats reduce storage or memory at a CPU cost.
5. Simplify Spatial Audio geometry and diffraction edges, limit path-search distance with finite attenuation, and recapture the same scene.

Why it matters:
There is no universal Wwise CPU setting. Moving cost from storage to decoding or from voices to effects may help one platform and hurt another.

Common mistakes:
- Changing codec quality without measuring decode CPU, media size, and audible result together.
- Optimizing an average editor scene instead of a target-device worst case.

When this does not apply:
If the spike comes from game-thread integration, file I/O, or engine scheduling rather than the Wwise audio thread, authoring changes alone may not fix it.

Related questions:
- What should I inspect first when Wwise CPU spikes?
- Is PCM always faster than Vorbis in Wwise?
- How do Effect instances affect Wwise CPU?
- Why can complex Spatial Audio geometry increase CPU use?

Useful terms:
- Codec: A software or hardware component that compresses and decompresses data.
- Finite Attenuation: A technique used to control the volume of audio sources over distance, reducing the perceived level at a specified distance from the source.
- PCM (Pulse Code Modulation): A digital sound format where an analog signal is sampled and quantized into binary numbers.

Editor notes:
The editor has removed filler text, patron promotions, subscribe calls, and off-topic creator chatter. The production language used is UK-friendly. The steps are based on the provided source excerpt and grounded in the context of optimizing Wwise CPU usage.
