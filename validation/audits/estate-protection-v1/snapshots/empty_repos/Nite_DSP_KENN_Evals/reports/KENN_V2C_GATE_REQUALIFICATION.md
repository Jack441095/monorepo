# Gate Requalification

The frozen V2-B gate is evaluated unchanged first. It reaches 1.000 precision,
0.000 healthy FP, 0.769 recall, and 0.848 abstention on the audio-derived
holdout; derived headroom candidates abstain because V2-B admits only measured
candidate kinds.

`scope_context.v2c.1` is a separately versioned adjustment, not a V2-B
retune. It admits the evidence-backed headroom derivation only for
MIX_IN_PROGRESS, keeps MASTER/UNKNOWN headroom observational, and treats
alternating L/R material as context-required. Its holdout result is 1.000
precision, 1.000 recall for the three V2-C target families, 0.000 healthy FP,
and 0.803 abstention. It is qualified only on this synthetic audio-derived
corpus.
