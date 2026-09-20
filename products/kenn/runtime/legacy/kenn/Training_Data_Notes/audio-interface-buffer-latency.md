# Audio Interface Buffer Size and Latency

Type: Recording workflow
Tags: latency, buffer, audio interface, recording, cpu, ableton, monitoring
Status: Approved
Source: Audio_Too studio practice
Reviewed: 2026-07-01

Short answer:
Use a small buffer while recording and a larger buffer while mixing. Start around 64 or 128 samples for tracked performances, then move to 512 or 1024 samples when the session becomes CPU-heavy.

Try this:
1. Select the interface's native ASIO driver on Windows or Core Audio device on macOS rather than a generic driver.
2. Record at 64–128 samples when the computer remains stable; raise the buffer if clicks or dropouts appear.
3. Disable look-ahead limiters, linear-phase processors, oversampling, and other high-latency plugins on the monitored path.
4. Use direct monitoring when the interface supports it, understanding that performers will not hear native plugin processing on that path.
5. After tracking, raise the buffer to 512–1024 samples and restore mix-bus processing.

Why it matters:
Buffer size trades monitoring delay against CPU headroom. A low buffer is useful for performance; it is not a permanent quality setting and does not make an offline export sound better.

Related questions:
- Why is my microphone delayed in Ableton Live?
- What buffer size should I use while recording vocals?
- Why does my Ableton project crackle at a low buffer size?
- Does audio buffer size change export quality?
