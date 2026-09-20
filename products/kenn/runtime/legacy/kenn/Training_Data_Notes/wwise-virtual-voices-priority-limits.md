Type: Game audio optimization
Tags: wwise, virtual voices, physical voices, managed state, monitored voice, no audio processing, playback limit, priority, volume threshold, per game object, global limit, cpu
Status: Approved
Source title: Understanding Virtual Voices; Wwise 251 Voice Limits
Source creator: Audiokinetic
Source URL: https://www.audiokinetic.com/en/public-library/2024.1.7_8863/?id=concept_virtualvoices.html&source=SDK
Source version: Wwise 2024.1 / Wwise 251
Reviewed: 2026-07-01

# Wwise Virtual Voices, Priority, and Playback Limits


Short answer:
Playback limits control the total number of simultaneous physical instances, priority determines which instance survives when a limit is exceeded, and virtual voice behavior decides whether an inaudible or displaced voice retains its managed and monitored state without physical audio processing, is killed, resumes, or restarts later.

Try this:
1. Profile the peak physical-voice count during the worst gameplay scene.
2. Apply per-game-object limits to sources that can spam locally, such as repeated impacts from one enemy.
3. Set global limits on categories whose total count matters across the whole scene, such as debris or water drops.
4. Assign higher importance to intelligibility and gameplay-critical sounds; use distance-based priority offsets where appropriate.
5. Choose virtual behavior deliberately for finite one-shots versus loops, then verify that long-lived virtual voices are stopped.

Why it matters:
Concurrent physical voices have a direct CPU cost. Limits without sensible priority can remove the wrong sound, while careless Resume or Play From Beginning behavior can leave virtual voices alive indefinitely.

Common mistakes:
- Treating a virtual voice as free state: Wwise still manages and monitors it.
- Giving every object equal priority and letting newest/oldest rules make gameplay decisions accidentally.

When this does not apply:
Do not set limits from a generic number alone. Platform CPU, content density, listener count, and gameplay importance determine the useful budget.

Related questions:
- What is the difference between a physical and virtual voice in Wwise?
- Should a Wwise playback limit be global or per game object?
- How does Wwise decide which sound to virtualize?
- Why do virtual voices keep accumulating in my Wwise capture?
