# AutoMix Reverb and Delay Send Levels

Type: AutoMix decision logic
Tags: automix, reverb, delay, send, plate, hall, room, decay, mix rules, spatial
Status: Approved
Source: studio/audio_analysis/audio_analysis/mixdown/mix_rules.py, mix_decision_engine.py (Audio Too codebase)
Reviewed: 2026-07-09

Short answer:
Every instrument rule in `INSTRUMENT_RULES` carries a fixed `reverb_send` (0.0–1.0, applied as a percentage in the decision log), `reverb_type` (room/plate/hall), `reverb_decay_s`, and `delay_send` (0.0–1.0). `generate_mix_plan()` copies these straight from the merged instrument+genre rule onto the stem's `StemMixConfig` — sends are not dynamically computed from the audio, they come from the declarative rules table.

Try this — default reverb sends by instrument:
1. Kick / sub bass / bass: 0% reverb send (dry, kept tight and mono).
2. Snare: 18% send, room reverb, 1.2s decay.
3. Hihat: 8% send, default room type.
4. Percussion: 18% send, plus a 5% delay send.
5. Vocal: 12% send, plate reverb, 1.6s decay, plus a 10% delay send (pop genre modifier raises this to 22% reverb / 15% delay for more polish).
6. Backing vocal: 28% send (room), plus 15% delay send — deliberately wetter than the lead vocal so it sits further back.
7. Synth lead: 15% send plus 12% delay send.
8. Synth pad: 30% send, hall reverb, 3.2s decay — the longest default decay of any instrument, consistent with pads being background/atmospheric.
9. Guitar: 12% send plus 3% delay.
10. Keys: 20% send plus 6% delay.
11. Strings: 35% send, hall reverb, 3.0s decay.
12. FX: 25% send plus 20% delay send — the highest delay send of any instrument category.
13. Ambient: 40% send (highest reverb send of any category) plus 10% delay.
14. Full drum bus: 5% send (kept mostly dry).

Genre modifiers change these per-genre — e.g. hip-hop drops vocal reverb to 8% but raises delay to 18% (slap-back delay is more idiomatic than big reverb in that genre); EDM raises synth_pad send to 35% and synth_lead to 20% reverb / 20% delay; cinematic raises strings to 45% and ambient to 50%; podcast sets vocal reverb and delay both to 0.0 (a dry, mono voice).

Why it matters:
The reverb/delay send table encodes front-to-back mix depth: low-frequency and transient-critical elements (kick, bass, sub, drum bus) stay dry so their transients and low-end stay tight and phase-coherent, while pads/strings/ambient are pushed further back in the soundstage with long, wide sends. Vocal sits in between — enough space to sound produced without smearing intelligibility.

Common mistakes:
- Reading `reverb_send` as a dB value — it is a 0.0–1.0 mix fraction, rendered in the decision log as a percentage (e.g. "Set plate reverb on 'vocal.wav' to 12%").
- Assuming reverb_type is genre-dependent by default — most genre modifiers only touch `reverb_send`/`delay_send` levels, not `reverb_type`, unless explicitly stated (e.g. synth_pad and strings default to hall, vocal defaults to plate, everything else defaults to room).

When this does not apply:
- If an instrument's rule has `reverb_send: 0.0` (kick, sub_bass, bass by default), no reverb line appears in the decision log for that stem — there is nothing to explain because AutoMix applied none.

Related questions:
- Why does the vocal use plate reverb instead of hall?
- Why is the drum bus reverb send so much lower than the snare's individually?
- How does the hip-hop genre modifier change vocal reverb vs. delay balance?
