# Product Architecture Map

Current product path: `platform_bridge.handle_mix_analyze` →
`mix_review.analyze_wav` → `analysis_core.analyze_wav` → product decoder
(`audio_analysis.utils.audio_io_api.decode_audio_bytes`) → existing metrics,
flags, actions and KENN handoff/evidence. The bridge currently emits a small
measured evidence set and the full report path has legacy flags/advice.

V2-D's correct insertion point is immediately after decode/PCM normalisation
and before legacy `review_flags()` interpretation: measured candidates →
versioned gate → structured evidence → optional explanation. It must not
replace existing Mix Review metrics or connect to Automix.
