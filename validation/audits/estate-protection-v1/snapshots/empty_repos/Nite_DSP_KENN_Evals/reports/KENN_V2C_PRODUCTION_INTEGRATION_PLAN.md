# Production Integration Plan

Do not integrate now: Audio_Too has active Thursday changes. If ownership later
becomes FREE, use a dedicated KENN branch with `KENN_MEASURED_GATE_V2C=off` by
default and rollback by disabling that flag.

Scope only: isolated measured clipping, sample-peak headroom, mix-wide L/R
candidate extraction, the versioned pure gate, evidence packets, and tests.
No Automix, DAW writes, UI redesign, or telemetry. Promotion requires the
feature flag, product regression suite, audio-derived regression fixture suite,
human review, and explicit branch ownership.
