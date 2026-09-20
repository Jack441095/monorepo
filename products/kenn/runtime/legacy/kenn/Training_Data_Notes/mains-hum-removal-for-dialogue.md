# Mains Hum Removal For Dialogue

Type: Restoration workflow
Tags: hum, mains hum, 50hz, 60hz, notch filter, ground loop, electrical buzz, restoration
Status: Approved

Short answer:
A steady tone at 50 or 60 Hz plus harmonics (100/150/200 or 120/180/240 Hz) under a recording is electrical mains hum from a ground loop or nearby power supply, not room noise. Fix it with a narrow notch (or a dedicated hum-removal plugin) at those exact frequencies rather than broadband noise reduction.

Try this:
1. Find the exact hum frequency on a spectrum analyzer — a sharp spike at 50 or 60 Hz with evenly-spaced harmonics above it, not a raised broadband floor.
2. Apply a narrow notch (or a hum-removal/de-hum plugin) at the fundamental and each harmonic. Keep it narrow so it doesn't thin out the voice.
3. Prefer fixing the source next time — a ground-loop isolator or balanced cabling stops the hum being recorded at all.

Why it matters:
Hum is narrowband and periodic, so a targeted notch removes it with far less damage to the voice than broadband noise reduction, which is built for hiss and room tone, not a tonal buzz.

Related questions:
- Why does my recording have a buzzing or humming sound under the voice?
- What's the difference between 50 Hz and 60 Hz hum?
- Is a notch filter or a denoiser better for mains hum?
