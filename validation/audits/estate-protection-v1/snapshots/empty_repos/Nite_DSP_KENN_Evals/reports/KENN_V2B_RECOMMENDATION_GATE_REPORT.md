# Recommendation Gate

The pure V2-B gate is `benchmark/recommendation_gate.py`. Its output states
are `NO_ACTION_RECOMMENDED`, `INSUFFICIENT_EVIDENCE`, `CONTEXT_REQUIRED`,
`OBSERVATION_ONLY`, and `RECOMMENDATION_JUSTIFIED`; actions are ABSTAIN,
OBSERVE, RECOMMEND, and STRONG_RECOMMEND.

It has no filesystem, model, DAW, network, logging, or mutable-global effects.
Only measured candidates can progress. Near-silence/short material abstains;
context-sensitive candidates with known confounders require context; and
non-persistent context-sensitive conditions remain observations.

This is the proposed integration boundary: measurement → candidate → gate →
optional prose. An LLM may render a permitted decision but cannot escalate it.
