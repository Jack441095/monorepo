# True Peak and Inter-Sample Clipping

Type: Mastering workflow
Tags: true peak, inter-sample peak, limiter, clipping, mastering, codec, loudness
Status: Approved
Source: Audio_Too studio practice
Reviewed: 2026-07-01

Short answer:
True-peak metering estimates peaks that can occur between stored samples during playback or codec conversion. Use a true-peak limiter and leave suitable ceiling margin when delivering lossy or streaming formats.

Try this:
1. Place a true-peak meter after the final limiter and measure the complete rendered file.
2. Enable the limiter's true-peak or oversampled mode for final delivery when available.
3. Use roughly -1 dBTP as a practical streaming starting point, then follow any explicit client or platform specification.
4. Recheck loud masters after AAC or MP3 encoding because codec conversion can create new overs.
5. Do not lower the ceiling blindly to solve audible distortion; reduce limiting or repair clipped source material when distortion remains.

Why it matters:
A sample-peak meter can show no clipping while reconstruction exceeds 0 dBFS. Margin reduces playback and encoding failures, but it does not repair an over-limited master.

Related questions:
- What is the difference between sample peak and true peak?
- Why does my master clip after MP3 conversion?
- What limiter ceiling should I use for streaming?
- Does a true-peak limiter fix a distorted master?
