# Healthy False-Positive Forensics

V2-A's 50/50 healthy/control failures are detector aggregation failures:
over-compressed (LRA) fired 240 times in 240 cases, resonance produced 789
events, and informational THD clipping appeared on controls despite the
product's own warning that this metric is not valid for complex mixes. Other
frequent healthy flags were low-mid build-up and over-widened air.

| Root cause class | Finding |
|---|---|
| Measurement validity | Polyphonic THD is explicitly outside its valid domain. |
| Threshold/context | LRA, resonance, band energy, and width lack healthy/context calibration. |
| Duplicate derivation | Several resonance events can describe one material condition. |
| Recommendation eagerness | Every product flag is effectively action-bearing. |
| Fixture ambiguity | Intentional bright/dense/panned controls are valid engineering choices. |

V2-B does not retune product thresholds. The experimental gate consumes
candidate scores and gives abstention semantic meaning first.
