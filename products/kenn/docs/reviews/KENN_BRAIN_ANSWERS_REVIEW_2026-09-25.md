# KENN's conversation brain: which answers read best?

**For:** Jack · **From:** the Stage 1 comparison on the GPU box, 25 Sept · **Decision:** local Qwen only (yours)

Same questions, three ways: KENN's current template answer, Qwen3 8B, and Qwen3 14B writing from the same notes.
The keyword checks rate them almost the same (template 79/84, 8B 78/84, 14B 78/84), so the choice comes down to
which reads like a good engineer. 8B is quicker and lighter (about 5 GB, which should fit your 16 GB Mac alongside Live; speed on the Mac is measured next); 14B (about 9 GB) is for the box GPU.

| | Checks passed | Model's answer used (passed) | Speed on the box GPU (p50 / p95) |
|---|---|---|---|
| template (no LLM) | 79/84 | 0 (0) | 0.16 s / 0.22 s |
| qwen3.5:4b | 78/84 | 37 (36) | 3.79 s / 4.81 s |
| kenn-brain-qwen3-8b | 78/84 | 42 (40) | 2.81 s / 3.66 s |
| kenn-brain-qwen3-14b | 78/84 | 43 (42) | 3.8 s / 4.96 s |

**Your call, per question:** which one would you want a tester to read? Then overall: 8B or 14B (or stay with the template for now).

## 1. Why does my bass disappear when the kick plays?

### Template (today) — 0.13 s

Diagnosis first:
The bass loses audibility when the kick plays.

What this is:
Usually a technical kick/bass interaction; how much audible ducking is desirable is a creative choice.

Most useful hypotheses to test:
Ordered by plausible impact, ease of testing, and reversibility—not certainty. Start with the first low-risk discriminator, then move on only if it does not explain the symptom.
1. Sidechain or volume ducking is too deep or too long — A kick-triggered compressor, shaper, or automation can keep the bass below audibility after the kick rather than merely making room for it.
   Test: Bypass the sidechain path at matched loudness, then restore it with less gain reduction and a shorter release. Compare only the kick-hit region.
   If confirmed: Use the minimum sidechain depth and release that clears the kick while letting the bass recover before the next musical note.
2. Fundamentals are masking or cancelling — Even without sidechain processing, overlapping low notes can hide the bass or reduce the summed low end through timing or polarity interaction.
   Test: Mute the kick briefly on the affected bass note, then compare mono, polarity, and tiny timing changes without changing level.
   If confirmed: Choose a low-frequency owner and adjust note length, octave, alignment, or frequency-specific space before applying a large EQ boost.
3. The bass has no audible harmonic cue on the target system — A sub-heavy bass can seem to disappear on phones or small speakers even when its deepest octave is present on full-range monitoring.
   Test: High-pass the mix temporarily and compare with a matched reference on a small speaker. If the bass role vanishes, it needs body above the sub range.
   If confirmed: Add controlled harmonics or body, then re-check that the apparent improvement is not simply louder overall.

Verification:
At matched loudness, the kick should have space and the bass should recover predictably on every hit in mono and on a small speaker.

Most useful question:
Is there a sidechain/volume-shaper on the bass, and does the loss last only for the kick transient or through the next note?

You could also ask:
- How do I sidechain in Ableton?
- What release time for sidechain compression?

### Qwen3 8B — 2.71 s

Short answer: Your bass disappears when the kick plays because of sidechain compression, phase cancellation, or masking — start by checking if sidechain is too deep or release too long, then test for phase issues.

Try this:  
1. Bypass the sidechain path at matched loudness, then restore it with less gain reduction and a shorter release. Compare only the kick-hit region.  
2. Mute the kick briefly on the affected bass note, then compare mono, polarity, and tiny timing changes without changing level.  
3. High-pass the mix temporarily and compare with a matched reference on a small speaker. If the bass role vanishes, it needs body above the sub range.

Why it matters: Kick and bass low-end overlap is a common mixing challenge. Sidechain compression can create audible pumping, while phase cancellation or masking can make the bass disappear when the kick hits — especially if they’re sharing the same frequency range or out of phase.

You could also ask:  
- Is there a sidechain/volume-shaper on the bass, and does the loss last only for the kick transient or through the next note?  
- How do I check kick and bass phase?  
- What release time for sidechain compression?

Sources:
- Sidechain Bass To Kick (sidechain-bass-to-kick.md)
- Should A Kick Be In Key With The Bass (kick-tuning-with-bass.md)
- Kick Bass Balance And Phase (kick-bass-balance-phase.md)

### Qwen3 14B — 3.5 s

Short answer: Your bass may be disappearing due to sidechain compression or phase cancellation between the kick and bass. Check the sidechain settings and phase alignment.

Try this:
1. Bypass the sidechain compressor on the bass track and listen for the bass during the kick. If it returns, adjust the sidechain depth and release time.
2. Mute the kick and listen to the bass in mono. If the bass is audible without the kick, check for phase issues by inverting the kick’s phase and listening for cancellation.
3. High-pass the bass slightly to remove sub frequencies that may be clashing with the kick, then check if the bass is more present.

Why it matters: The kick and bass often compete in the low-end frequency range. If they are not properly spaced in frequency or time, or if phase cancellation occurs, the bass can become masked or inaudible during the kick transient. Sidechain compression, if too aggressive, can also cause the bass to duck too much or not recover quickly enough.

You could also ask:
- How do I check kick and bass phase?
- Should I sidechain bass to the kick?

Sources:
- Sidechain Bass To Kick (sidechain-bass-to-kick.md)
- Should A Kick Be In Key With The Bass (kick-tuning-with-bass.md)
- Kick Bass Balance And Phase (kick-bass-balance-phase.md)

**Best:** [ ] template  [ ] 8B  [ ] 14B

## 2. clip automation in session view

### Template (today) — 0.15 s

Here is the practical Ableton version.
→ Hands-on. Live workflow:

In Ableton Live, the direct solution is:
Clip envelopes in Ableton Live 12 allow non-destructive modulation of mixer parameters, device controls, and audio samples during playback. They enable precise control over volume, pan, pitch, and more, with real-time automation capabilities.

Here is the step-by-step setup in Live:
1. Select a clip in Session View and press 'E' to open the envelope editor.
2. Click 'Add Envelope' and choose 'Mixer Volume' to modulate clip volume.
3. Set attack time to 0.01s, sustain to 0.5s, release to 0.1s.
4. Draw an envelope curve to shape the volume over the clip duration.
5. Enable 'Link to Clip' to apply changes to the original sample.

Live safety:
Duplicate or save the track first, make one device or routing change at a time, then A/B in Live before committing.

Live check:
Try the move on a duplicate track or blank Live Set, then A/B with the device or routing bypassed.

What to avoid while routing this device:
Avoid changing several devices at once; make one move, listen, then continue.

Why this workflow works in Ableton:
Clip envelope automation enables precise control over audio dynamics and spatial positioning. By modulating mixer parameters, you can create complex stereo imaging and dynamic range. This technique is essential for live performance and studio production, allowing real-time adjustments without altering the original audio.

→ Try it on a duplicate track, then A/B. If this is not what you needed, I can walk through the routing or device setup.

You could also ask:
- How to link clip envelopes to multiple devices?
- What are the best practices for using clip envelopes with MIDI clips?

### Qwen3 8B — 2.92 s

Short answer: Clip envelopes in Ableton Live 12 allow non-destructive modulation of mixer parameters, device controls, and audio samples during playback. They enable precise control over volume, pan, pitch, and more, with real-time automation capabilities.

Try this:
1. Select a clip in Session View and press 'E' to open the envelope editor.  
2. Click 'Add Envelope' and choose 'Mixer Volume' to modulate clip volume.  
3. Set attack time to 0.01s, sustain to 0.5s, release to 0.1s.  
4. Draw an envelope curve to shape the volume over the clip duration.  
5. Enable 'Link to Clip' to apply changes to the original sample.  

Live safety:  
Duplicate or save the track first, make one device or routing change at a time, then A/B in Live before committing.

Why it matters:  
Clip envelope automation enables precise control over audio dynamics and spatial positioning. By modulating mixer parameters, you can create complex stereo imaging and dynamic range. This technique is essential for live performance and studio production, allowing real-time adjustments without altering the original audio.

You could also ask:  
- How to link clip envelopes to multiple devices?  
- What are the best practices for using clip envelopes with MIDI clips?  
- Can clip envelopes be used to control reverb send levels?

Sources:
- Clip Envelope Automation in Session View (ableton12-session-view-pt3.md)
- Clip Automation Basics (clip-automation-basics.md)
- Clip Envelopes In Ableton (ableton-clip-envelopes.md)

### Qwen3 14B — 3.72 s

Short answer:  
Clip envelopes in Ableton Live 12 let you non-destructively automate mixer parameters, device controls, and audio samples during playback — ideal for shaping volume, pan, and more in real time.

Try this:  
1. Select a clip in Session View and press 'E' to open the envelope editor.  
2. Click 'Add Envelope' and choose a parameter like 'Mixer Volume' to modulate.  
3. Set attack, sustain, and release times to define the envelope shape.  
4. Draw the envelope curve to control the parameter over the clip’s duration.  
5. Enable 'Link to Clip' to apply the envelope to the original sample.

Why it matters:  
Clip envelope automation gives you precise control over dynamics and spatial positioning without altering the original audio. This is key for both live performance and studio production, enabling real-time adjustments and complex stereo imaging.

You could also ask:  
- How to link clip envelopes to multiple devices?  
- What are the best practices for using clip envelopes with MIDI clips?  
- Can clip envelopes be used to control reverb send levels?

Sources:
- Clip Envelope Automation in Session View (ableton12-session-view-pt3.md)
- Clip Automation Basics (clip-automation-basics.md)
- Clip Envelopes In Ableton (ableton-clip-envelopes.md)

**Best:** [ ] template  [ ] 8B  [ ] 14B

## 3. when should I freeze and flatten tracks

### Template (today) — 0.16 s

Here is the practical Ableton version.
→ Hands-on. Live workflow:

In Ableton Live, the direct solution is:
Freezing temporarily renders a track's devices and clips to audio to reduce CPU load — you can unfreeze later to edit. Flattening permanently replaces the track content with the rendered audio and removes the devices. Bounce in Place (Live 12) renders a track to a new audio track while keeping the original.

Here is the step-by-step setup in Live:
1. To Freeze: right-click the track header and choose Freeze Track. The track turns to a cached audio file — you cannot edit devices or MIDI while frozen, but CPU load drops to nearly zero for that track.
2. To Unfreeze: right-click the frozen track and choose Unfreeze Track. Everything goes back to how it was, devices and all.
3. To Flatten: right-click a frozen track and choose Flatten. This permanently replaces the MIDI clips and devices with the rendered audio. The devices are removed. This cannot be undone after saving and closing.
4. Always duplicate the track before flattening if you might want to go back. Drag the track header while holding Cmd (Mac) or Ctrl (Windows) to duplicate it, then freeze and flatten the copy.
5. Bounce in Place (Live 12): right-click a track and choose Bounce Track in Place. This creates a new audio track with the rendered audio and keeps the original track (deactivated). It is the safest commit option.
6. Freeze heavy synths (Serum, Diva, Wavetable with unison) and tracks with many effects first — these are the biggest CPU consumers.

Live safety:
Duplicate or save the track first, make one device or routing change at a time, then A/B in Live before committing.

Live check:
Try the move on a duplicate track or blank Live Set, then A/B with the device or routing bypassed.

What to avoid while routing this device:
Avoid changing several devices at once; make one move, listen, then continue.

Why this workflow works in Ableton:
Freezing and flattening are essential for managing CPU in large sessions. Freeze when you are still arranging; flatten when you are done with a sound and ready to mix. Bounce in Place gives you the best of both — committed audio with an undo path.

→ Try it on a duplicate track, then A/B. If this is not what you needed, I can walk through the routing or device setup.

You could also ask:
- How do I reduce CPU load in Ableton?
- What is the difference between freeze and flatten?

### Qwen3 8B — 2.83 s

Short answer: Freeze tracks while arranging to reduce CPU load and keep edits possible; flatten when you're done with a sound and ready to mix. Bounce in Place (Live 12) is the safest commit option.

Try this:
1. Freeze tracks with heavy synths (Serum, Diva, Wavetable with unison) or many effects first — these are the biggest CPU consumers.
2. Duplicate the track before flattening to preserve the original, then freeze and flatten the copy.
3. Use Bounce in Place (Live 12) to render a track to a new audio track while keeping the original deactivated — this is the safest commit option.

Why it matters: Freezing and flattening are essential for managing CPU in large sessions. Freeze when you're still arranging; flatten when you're done with a sound and ready to mix. Bounce in Place gives you the best of both — committed audio with an undo path.

Live safety: Always duplicate the track before flattening. Make one device or routing change at a time, then A/B test before committing.

You could also ask:
- How do I reduce CPU load in Ableton?
- What is the difference between freeze and flatten?

Sources:
- Freeze, Flatten, and Bounce (freeze-flatten-bounce.md)
- Reducing CPU Load In Ableton (cpu-saving.md)
- Resampling In Ableton (resampling-in-ableton.md)

### Qwen3 14B — 4.22 s

Short answer: Freeze tracks while arranging to reduce CPU load without losing editability; flatten when you're done with a sound and ready to mix, as it permanently replaces devices with audio. Bounce in Place offers a safe middle ground.

Try this:
1. Freeze a track by right-clicking the track header and choosing Freeze Track — this reduces CPU load while keeping the ability to edit later.
2. When you're satisfied with the sound and no further edits are needed, duplicate the track (Cmd/Ctrl + drag the header), freeze the copy, then flatten it to permanently replace the devices with audio.
3. For a safe commit, use Bounce in Place (right-click the track and choose Bounce Track in Place) — this creates a new audio track with the rendered sound, leaving the original track intact.

Why it matters: Freezing and flattening help manage CPU usage and streamline your session. Freezing is ideal during the arranging phase, where you might still want to tweak sounds, while flattening is best for finalizing tracks before mixing. Bounce in Place provides a non-destructive way to commit audio without losing the original track.

You could also ask:
- How do I reduce CPU load in Ableton?
- What is the difference between freeze and flatten?
- Can I freeze a return track?

Sources:
- Freeze, Flatten, and Bounce (freeze-flatten-bounce.md)
- Reducing CPU Load In Ableton (cpu-saving.md)
- Resampling In Ableton (resampling-in-ableton.md)

**Best:** [ ] template  [ ] 8B  [ ] 14B

## 4. what should I do next if my track arrangement feels boring

### Template (today) — 0.17 s

Here is the Ableton version in plain English.
→ Hands-on. Live workflow:

The concept:
Improve an arrangement by controlling energy in sections, not by adding more sounds everywhere. Use contrast, automation, fills, risers, mutes, and small changes before section boundaries so the listener feels movement.

Why it works:
Many unfinished tracks are not missing another plugin. They need clearer contrast, fewer competing parts, and deliberate movement between sections.

Try it:
1. Label the timeline into intro, build, drop, breakdown, second drop, and outro, or use equivalent song sections.
2. Mute anything that does not support the main idea of each section.
3. Add one transition cue before important changes: a fill, reverse, riser, silence, filter sweep, or automation move.
4. Make the drop or chorus feel bigger by reducing energy just before it.

Live safety:
Duplicate or save the track first, make one device or routing change at a time, then A/B in Live before committing.

Live check:
Try the move on a duplicate track or blank Live Set, then A/B with the device or routing bypassed.

What to avoid while routing this device:
Avoid changing several devices at once; make one move, listen, then continue.

→ Try it on a duplicate track, then A/B. If this is not what you needed, I can walk through the routing or device setup.

You could also ask:
- What should I do next if my track feels boring?
- How do I make a drop feel bigger?

### Qwen3 8B — 2.3 s

Short answer: Use automation, contrast, and transitions to create movement — don’t just add more sounds.  
Try this:  
1. Label your arrangement with sections (intro, build, drop, etc.) using Locators.  
2. Automate filters, reverb, or delay feedback during transitions to build tension.  
3. Remove or thin one key element before the drop so its return feels bigger.  
4. Add a short silence or drum fill before the drop to create impact.  
5. Simplify the arrangement after the drop to focus on the main idea.  

Why it matters: Boring arrangements often lack contrast and deliberate movement. By automating changes and simplifying sections, you guide the listener’s attention and create emotional peaks and valleys.  

You could also ask:  
- How do I make a drop feel bigger?  
- What should I do next if my track feels boring?

Sources:
- Live Keyboard Shortcuts (Part 2) - Efficient Track and Arrangement Control (ableton12-live-keyboard-shortcuts-pt2.md)
- Arrangement Energy And Transitions (arrangement-energy-and-transitions.md)
- Arrangement Build Ups Drops And Tension (arrangement-build-ups-drops-tension.md)

### Qwen3 14B — 3.0 s

Short answer: Make your arrangement feel more dynamic by introducing contrast, using automation, and adding subtle transitions — don’t just add more sounds.

Try this:
1. Label your arrangement sections (intro, verse, chorus, drop, etc.) using Locators in the arrangement ruler.
2. Mute or reduce elements in sections that don’t support the main idea — e.g., strip back to just vocals and one instrument in a verse.
3. Add a transition before a drop: a silence, fill, riser, or filter sweep to build tension.

Why it matters: A boring arrangement often lacks contrast and movement. By simplifying sections and using deliberate transitions, you guide the listener’s attention and create a more engaging flow.

You could also ask:
- How do I make a drop feel bigger?
- What should I do next if my track feels boring?

Sources:
- Live Keyboard Shortcuts (Part 2) - Efficient Track and Arrangement Control (ableton12-live-keyboard-shortcuts-pt2.md)
- Arrangement Energy And Transitions (arrangement-energy-and-transitions.md)
- Arrangement Build Ups Drops And Tension (arrangement-build-ups-drops-tension.md)

**Best:** [ ] template  [ ] 8B  [ ] 14B

## 5. EQ before or after compression?

### Template (today) — 0.14 s

Here is the practical production version.
→ Let's trace the symptom.

Here is the recommended production technique:
Use corrective EQ before compression when you need to remove rumble, harsh resonances, or low-mid build-up that would trigger the compressor badly. Use tone-shaping EQ after compression when you want to add brightness, body, or polish once the dynamics are controlled. It is normal to use both: cleanup EQ -> compressor -> tone EQ.

Try this workflow in your next session:
1. Start with level balance first so you are not using EQ or compression to fix a fader problem.
2. Put a cleanup EQ before the compressor and remove obvious rumble, mud, or harsh peaks.
3. Set the compressor after that so it reacts to the useful signal rather than unwanted low end or resonances.
4. Add a second gentle EQ after compression if the part needs more presence, weight, or air.
5. Bypass each stage at matched loudness; keep the move only if the part sits better in the mix.
6. On a mix bus, keep both moves small. Heavy EQ into heavy compression usually means the balance needs fixing earlier.

Diagnosis boundary:
Start from the audible symptom, change one variable at a time, and verify at matched loudness before adding another processor.

Listening check:
Bypass and compare at matched loudness; the change should solve the symptom without making another range worse.

Avoid these common production mistakes:
Avoid processing the loudest-looking problem first if the real issue is masking, arrangement, or level balance.

Why this makes a difference in your mix:
EQ and compression order changes what the compressor hears. Cutting problem frequencies first can make compression smoother, while EQ after compression is better for final tone.

→ Try that change, then tell me if the symptom shifted or stayed. That tells us what to try next.

You could also ask:
- Mix bus compression before or after EQ?
- Should I cut lows before compressing vocals?

### Qwen3 8B — 2.65 s

Short answer: Use corrective EQ before compression to remove problematic frequencies that trigger the compressor, and use tone-shaping EQ after compression to add character once dynamics are controlled.  

Try this:  
1. Start by balancing levels to avoid using EQ or compression to fix fader issues.  
2. Place a cleanup EQ before the compressor to remove rumble, mud, or harsh peaks.  
3. Set the compressor after the cleanup EQ so it reacts to the clean, useful signal.  
4. Add a gentle tone EQ after compression if you need more presence, weight, or air.  
5. Bypass each stage at matched loudness to verify if the change improves the mix.  
6. On a mix bus, keep both EQ and compression subtle—heavy processing often indicates a balance issue earlier in the chain.  

Why it matters:  
The order of EQ and compression affects how the compressor reacts to the signal. Cleaning up problematic frequencies before compression ensures the compressor works on the intended sound, not unwanted noise or resonances. EQ after compression is ideal for fine-tuning the tone once dynamics are controlled.  

You could also ask:  
- Should I cut lows before compressing vocals?  
- Mix bus compression before or after EQ?

Sources:
- EQ Before Or After Compression (eq-before-after-compression.md)
- Mix Bus EQ Compression Order (mix-bus-eq-compression-order.md)
- EQ Eight Mixing Basics (eq-eight-mixing-basics.md)

### Qwen3 14B — 3.36 s

Short answer:  
Use corrective EQ before compression to clean up problematic frequencies, and use tone-shaping EQ after compression to enhance the sound once dynamics are controlled. It’s common to use both in sequence: cleanup EQ → compressor → tone EQ.

Try this:  
1. Ensure your track levels are balanced before applying any EQ or compression.  
2. Insert a corrective EQ before the compressor and remove rumble, mud, or harsh peaks.  
3. Insert a second, gentler EQ after the compressor to add presence, weight, or air.  
4. Bypass each EQ stage at matched loudness to compare and ensure the changes improve the sound without introducing new issues.

Why it matters:  
The order of EQ and compression affects how the compressor reacts to the signal. Corrective EQ before compression helps the compressor focus on the desired dynamics, while tone-shaping EQ after compression allows you to sculpt the final sound without affecting the compressor’s behavior.

You could also ask:  
- Should I cut lows before compressing vocals?  
- Mix bus compression before or after EQ?

Sources:
- EQ Before Or After Compression (eq-before-after-compression.md)
- Mix Bus EQ Compression Order (mix-bus-eq-compression-order.md)
- EQ Eight Mixing Basics (eq-eight-mixing-basics.md)

**Best:** [ ] template  [ ] 8B  [ ] 14B

## 6. What Arrangement View shortcuts should I learn first?

### Template (today) — 0.19 s

Here is the Ableton version in plain English.
→ Hands-on. Live workflow:

The concept:
Use Arrangement View shortcuts to move quickly around the timeline: duplicate sections, loop a range, zoom to selection, add locators, and split clips without breaking the creative flow. Keep shortcuts focused on navigation and editing first, then automation once the structure is working.

Why it works:
Arrangement work gets slow when every edit requires dragging around the timeline. Shortcuts make it easier to test structure, compare sections, and make client revisions without losing the musical idea.

Try it:
1. Select a section and duplicate it to test structure changes quickly.
2. Use split at the playhead to separate verse, chorus, breakdown, or transition ideas.
3. Set locators for major song sections so you can jump around the arrangement.
4. Loop a small range while editing transitions or automation moves.

Live safety:
Duplicate or save the track first, make one device or routing change at a time, then A/B in Live before committing.

Live check:
Try the move on a duplicate track or blank Live Set, then A/B with the device or routing bypassed.

What to avoid while routing this device:
Avoid changing several devices at once; make one move, listen, then continue.

→ Try it on a duplicate track, then A/B. If this is not what you needed, I can walk through the routing or device setup.

You could also ask:
- How do I work faster in Arrangement View?
- What shortcuts matter most for editing a song structure?

### Qwen3 8B — 2.0 s

Short answer:  
Learn the shortcuts for duplicating sections, splitting clips at the playhead, and setting locators first — these let you test structure and edit without dragging the timeline.  

Try this:  
1. Select a section and press **Ctrl + D** (Windows) / **Cmd + D** (Mac) to duplicate it.  
2. Press **Ctrl + Shift + S** (Windows) / **Cmd + Shift + S** (Mac) to split the clip at the playhead.  
3. Click the **Locator** button in the top toolbar and press **L** to set a locator at the playhead.  

Why it matters:  
These shortcuts reduce the need for manual timeline navigation, letting you focus on creative decisions rather than repetitive editing.  

You could also ask:  
- How do I loop a range for editing transitions?  
- Can I use locators to mark song sections for mixing?

Sources:
- Arrangement View Shortcuts (arrangement-view-shortcuts.md)
- Ableton Live 12 - First Steps: Learn View & Info View Setup (ableton12-first-steps-pt1.md)
- Live Keyboard Shortcuts (Part 2) - Efficient Track and Arrangement Control (ableton12-live-keyboard-shortcuts-pt2.md)

### Qwen3 14B — 3.9 s

Short answer:  
Learn shortcuts for navigation and editing first — like duplicating sections, looping ranges, zooming to selection, adding locators, and splitting clips — to maintain creative flow and speed up workflow.

Try this:  
1. Use **Cmd/Ctrl + D** to duplicate a selected section for quick structure testing.  
2. Press **Cmd/Ctrl + L** to loop a selected range while fine-tuning transitions or automation.  
3. Use **Cmd/Ctrl + Z** to zoom to the current selection for focused editing.  
4. Press **Cmd/Ctrl + M** to add a locator at the current playhead position for easy navigation.  
5. Use **Cmd/Ctrl + S** to split clips at the playhead, separating verse, chorus, or transition ideas cleanly.

Why it matters:  
Arrangement work gets slow when every edit requires dragging around the timeline. Shortcuts make it easier to test structure, compare sections, and make client revisions without losing the musical idea.

Live safety:  
Duplicate or save the track first, make one device or routing change at a time, then A/B in Live before committing.

You could also ask:  
- How do I work faster in Arrangement View?  
- What shortcuts matter most for editing a song structure?  
- How should I mark sections before mixing?

Sources:
- Arrangement View Shortcuts (arrangement-view-shortcuts.md)
- Ableton Live 12 - First Steps: Learn View & Info View Setup (ableton12-first-steps-pt1.md)
- Live Keyboard Shortcuts (Part 2) - Efficient Track and Arrangement Control (ableton12-live-keyboard-shortcuts-pt2.md)

**Best:** [ ] template  [ ] 8B  [ ] 14B

## 7. How do I mix vocal doubles adlibs and delay throws without clutter?

### Template (today) — 0.17 s

I would approach the session like this.
→ Let's trace the symptom.

Here are the steps:
1. Keep the lead vocal as the clearest and most central element.
2. Pan or widen doubles more than the lead, but turn them down until they support rather than distract.
3. Use adlibs for call-and-response, transitions, and final chorus lift.
4. Automate delay throws at phrase endings instead of leaving delay loud all the way through.
5. High-pass and low-pass throws so they do not mask the next line.
6. Mute doubles/adlibs occasionally; if the song does not lose energy, they may be too busy.

Why this works:
Vocal layers make a record feel finished when they guide energy through the arrangement. Too many constant layers make the hook harder to understand and push mud into the sides and effects returns.

Listening check:
Bypass and compare at matched loudness; the change should solve the symptom without making another range worse.

Diagnosis boundary:
Start from the audible symptom, change one variable at a time, and verify at matched loudness before adding another processor.

Avoid these common production mistakes:
Avoid processing the loudest-looking problem first if the real issue is masking, arrangement, or level balance.

→ Try that change, then tell me if the symptom shifted or stayed. That tells us what to try next.

You could also ask:
- How loud should vocal doubles be?
- Where should I use delay throws?

### Qwen3 8B — 2.72 s

Short answer: Use doubles, adlibs, and throws to support the lead vocal, not compete with it. Keep the lead clear, tuck doubles under key phrases, automate delay throws into gaps, and EQ effects so they add width and excitement without muddying the lyric.

Try this:
1. Keep the lead vocal as the clearest and most central element.
2. Pan or widen doubles more than the lead, but turn them down until they support rather than distract.
3. Use adlibs for call-and-response, transitions, and final chorus lift.
4. Automate delay throws at phrase endings instead of leaving delay loud all the way through.
5. High-pass and low-pass throws so they do not mask the next line.
6. Mute doubles/adlibs occasionally; if the song does not lose energy, they may be too busy.

Why it matters: Vocal layers make a record feel finished when they guide energy through the arrangement. Too many constant layers make the hook harder to understand and push mud into the sides and effects returns.

Diagnosis boundary: This is an objective/technical issue. The solution lies in level balance, panning, EQ, and automation to ensure vocal layers complement rather than clutter the mix.

Sources:
- Vocal Doubles Adlibs And Throws (vocal-doubles-adlibs-throws.md)
- Vocal Width Without Mud (vocal-width-without-mud.md)
- Vocal Delay Throws and Send Automation (vocal-delay-throws-automation.md)

### Qwen3 14B — 3.64 s

Short answer: Keep the lead vocal clear, automate delay throws into gaps, and EQ effects so they add width and excitement without muddying the lyric.

Try this:
1. Keep the lead vocal as the clearest and most central element.
2. Pan or widen doubles more than the lead, but turn them down until they support rather than distract.
3. Use adlibs for call-and-response, transitions, and final chorus lift.
4. Automate delay throws at phrase endings instead of leaving delay loud all the way through.
5. High-pass and low-pass throws so they do not mask the next line.
6. Mute doubles/adlibs occasionally; if the song does not lose energy, they may be too busy.

Why it matters: Vocal layers make a record feel finished when they guide energy through the arrangement. Too many constant layers make the hook harder to understand and push mud into the sides and effects returns.

You could also ask:
- How loud should vocal doubles be?
- Where should I use delay throws?

Sources:
- Vocal Doubles Adlibs And Throws (vocal-doubles-adlibs-throws.md)
- Vocal Width Without Mud (vocal-width-without-mud.md)
- Vocal Delay Throws and Send Automation (vocal-delay-throws-automation.md)

**Best:** [ ] template  [ ] 8B  [ ] 14B

## 8. What does crest factor and spectrum balance tell me in the Mix Review Lab?

### Template (today) — 0.19 s

Here is the mix-review path I would use.
→ Let's trace the symptom.

The concept:
Use mix-review metrics as clues, not final judgement. Peak, RMS, crest factor, spectrum balance, stereo spread, and perceived loudness can point to problems, but the fix should still be confirmed by level-matched listening against references.

Why it works:
Analysis helps find blind spots, but meters cannot tell you the musical role of each element. The best mix-review workflow combines objective clues with reference listening and targeted fixes.

Try it:
1. If peak is high but RMS is low, look for uncontrolled transients or too much headroom loss from one element.
2. If crest factor is very low, check whether compression, clipping, or limiting has flattened the groove.
3. If low mids dominate the spectrum, check bass, kick, lower vocal body, reverb returns, and master bus buildup.
4. If high end looks excessive, check cymbals, sibilance, distortion, and bright reverbs on headphones.

Diagnosis boundary:
Start from the audible symptom, change one variable at a time, and verify at matched loudness before adding another processor.

Listening check:
Bypass and compare at matched loudness; the change should solve the symptom without making another range worse.

Common pitfalls to avoid in this mix stage:
Avoid processing the loudest-looking problem first if the real issue is masking, arrangement, or level balance.

→ Try that change, then tell me if the symptom shifted or stayed. That tells us what to try next.

You could also ask:
- What does crest factor tell me about a mix?
- How should I use a spectrum analyser for mix feedback?

### Qwen3 8B — 2.82 s

Short answer:  
Crest factor and spectrum balance are clues, not final judgements. A low crest factor suggests compression, clipping, or limiting that flattens dynamics, while a dominant low-mid spectrum indicates buildup from bass, kick, vocal body, or reverb. Always confirm fixes with level-matched listening against references.

Try this:  
1. If crest factor is very low, check for over-compression, clipping, or limiting that might have flattened the groove.  
2. If low mids dominate the spectrum, inspect the bass, kick, lower vocal body, reverb returns, and master bus for buildup.  
3. Compare the mix to a level-matched reference to ensure the changes don’t mask other issues or distort the musical role of elements.

Why it matters:  
Crest factor and spectrum balance help identify dynamic control and frequency imbalances, but they don’t replace the need for reference listening. The goal is to use these metrics as starting points, not as definitive answers, to guide targeted fixes without over-processing.

Diagnosis boundary:  
This is an objective/technical issue. The metrics provide measurable data, but the final decision on how to address them is subjective and depends on the musical context and reference listening.  

You could also ask:  
- What does the Mix Review Lab mean by low-mid buildup?  
- How should I use a spectrum analyser for mix feedback?

Sources:
- Mix Review Metrics Interpretation (mix-review-metrics-interpretation.md)
- Mix Review Revision Priorities (mix-review-revision-priorities.md)
- Using iZotope Reference Tracks for Mix Balance & Dynamic Range (izotope-4-popular-mixing-reference-tracks-and-why-they-work-pt1.md)

### Qwen3 14B — 3.78 s

Short answer:  
Crest factor and spectrum balance in the Mix Review Lab highlight dynamic range and frequency distribution issues. A low crest factor suggests compression or limiting may be flattening dynamics, while an unbalanced spectrum may point to frequency masking or buildup — but always confirm with level-matched listening.

Try this:  
1. Check the crest factor: if it’s low, bypass your master bus compressor/limiter and see if the dynamics return.  
2. Analyse the spectrum balance: solo individual tracks (bass, kick, vocals) to identify if any are overpowering others.  
3. Compare your mix to a reference at the same loudness to see if the imbalance is audible.

Why it matters:  
Crest factor reflects the ratio between peak and average levels, indicating how dynamic or compressed your mix feels. Spectrum balance shows where energy is concentrated — too much in one range can cause muddiness or harshness. These metrics are tools, not rules, and must be confirmed with listening to ensure they align with the mix’s intended feel and clarity.

You could also ask:  
- How should I use a spectrum analyser for mix feedback?  
- What does the Mix Review Lab mean by low-mid buildup?

Sources:
- Mix Review Metrics Interpretation (mix-review-metrics-interpretation.md)
- Mix Review Revision Priorities (mix-review-revision-priorities.md)
- Using iZotope Reference Tracks for Mix Balance & Dynamic Range (izotope-4-popular-mixing-reference-tracks-and-why-they-work-pt1.md)

**Best:** [ ] template  [ ] 8B  [ ] 14B


## Decision (25 Sept)

**Qwen3 8B.** The owner delegated the choice. 8B matched 14B on the content checks, is a third faster, and needs about
half the memory (5 GB against 9 GB), which matters on a 16 GB Mac that is also running Live. The side-by-side
answers above are still worth a read for tone before the style fine-tune.
