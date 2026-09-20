# Podcast Delivery Loudness Targets

Type: Mastering workflow
Tags: podcast, loudness, lufs, true peak, apple podcasts, spotify, delivery, normalization, mastering, spoken word
Status: Approved

Short answer:
Podcast platforms auto-normalize loudness, so mixing to their target integrated loudness (measured in LUFS, not peak level) up front avoids either your show getting turned down and losing punch, or getting turned up and exposing noise/distortion. Apple Podcasts targets -16 LUFS (mono or stereo), Spotify targets -14 LUFS, and a common mono spoken-word target is around -19 LUFS; almost every platform also expects true peak at or below -1 dBTP so their own normalization doesn't clip.

Try this:
1. Edit and level the dialogue first (consistent speech level, gaps trimmed) before worrying about the final loudness number — loudness normalization can't fix a mix where quiet and loud sections wander.
2. Measure integrated LUFS across the whole episode, not a single loud line — a short peak reading isn't the same as the platform's normalization measurement.
3. If you're delivering to one primary platform, target that platform's LUFS number directly (e.g. -16 for Apple Podcasts). If delivering broadly, -16 to -19 LUFS is a safe middle ground that won't get turned down hard anywhere.
4. Apply a true-peak limiter with at least -1 dBTP headroom as the last step, after loudness is set — a compliant integrated LUFS with an uncontrolled true peak still risks inter-sample clipping on lossy encodes (MP3/AAC).
5. Re-measure after any export/transcode — lossy encoding can add a small amount of true-peak overshoot versus the source file.

Why it matters:
Being louder than a platform's target doesn't make an episode sound more competitive the way it might in music — the platform just turns it down to match everyone else, and any distortion or excess brightness added to chase loudness stays audible after that turn-down. Being much quieter than target risks the platform turning it up and exposing background noise, hum, or room tone that was previously masked.

Common mistakes:
- Mixing to a peak level (e.g. "peaks at -3 dBFS") instead of measuring integrated loudness — the two aren't the same thing, and a spoken-word file with big level swings can peak safely while still measuring far off the platform's real target.
- Skipping the true-peak check after loudness normalization — normalizing gain to hit an LUFS target can push true peak above a safe ceiling if the file wasn't already close to its final gain.
- Applying loudness normalization before finishing edits — re-editing after normalizing means re-measuring and re-normalizing again; do the loudness pass last.

Related questions:
- What LUFS should I mix my podcast to?
- Why did my episode sound quieter after Spotify/Apple Podcasts normalized it?
- What true peak ceiling is safe for podcast delivery?
- Is -16 LUFS too quiet for a podcast?
