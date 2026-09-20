# Jack Gandy Studio Monitoring Setup

Type: Personal studio workflow
Tags: jack, monitoring, speakers, kh120, neumann, sonarworks, calibration, acoustics, room correction
Status: Approved
Source: Jack Gandy Personal Workflow
Reviewed: 2026-07-07

Short answer:
Jack Gandy's monitoring setup uses **Neumann KH 120** active studio monitors. To guarantee an accurate frequency response and resolve room acoustic anomalies, he calibrates the monitors using **Sonarworks Reference** (SoundID Reference) calibration software.

Try this:
1. Position the Neumann KH 120 monitors to form an equilateral triangle with your listening position.
2. Run Sonarworks Reference calibration using the measurement microphone to map the room's frequency response.
3. Keep the Sonarworks correction profile active on your system output (or inside a dedicated monitor controller plugin slot in your DAW).
4. **CRITICAL**: Remember to bypass the Sonarworks correction plugin when exporting files from Ableton, otherwise the correction curve will be printed onto the final audio file!

Why it matters:
Even high-end monitors like the KH 120s can have major frequency dips or boosts caused by room acoustics and reflections. Applying a calibration curve flattens these response peaks and valleys, giving the engineer a neutral listening environment so their mixes translate accurately to other sound systems.

Common mistakes:
- Forgetting to bypass Sonarworks when bouncing or exporting the mix, which prints the speaker correction curve directly onto the client's file.

When this does not apply:
- When mixing solely on calibrated reference headphones (where a headphone-specific calibration profile is used instead).

Related questions:
- What monitors does Jack Gandy use?
- How does Jack calibrate his speakers?
- Why do my exports sound thin/boomy (forgetting to bypass Sonarworks)?
