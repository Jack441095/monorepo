# Distorted Master Troubleshooting

Type: Mastering troubleshooting workflow
Tags: mastering, distortion, clipping, limiter, true peak, loudness, crest factor, headroom, mix bus
Status: Approved

Short answer:
If a master is distorting, reduce level before changing tone. Find whether the distortion comes from the mix bus, a clipper, a limiter, saturation, or inter-sample peaks, then recover loudness only after punch and clarity return.

Try this:
1. Turn the limiter input or mix bus gain down 1-3 dB and level-match the bypass.
2. Bypass master processing from the end backwards: limiter, clipper, saturator, bus compressor, then mix bus EQ.
3. Watch true peak or output ceiling; keep a safety ceiling around -1 dBTP for streaming-style exports.
4. If crest factor is very low, back off limiting or clipping before adding EQ.
5. If only the kick or snare distorts, clip-gain or soften that transient instead of crushing the whole master.
6. Re-check loudness after the distortion is gone; a cleaner master that is slightly quieter often translates better.

Why it matters:
Distortion on the master is usually a gain-staging or dynamics problem. Chasing loudness first can make the track smaller, harsher, and harder to fix later.

Related questions:
- Why does my master sound distorted?
- How much limiting is too much?
- Should I use a clipper before a limiter?
