# KENN MIX-REVIEW LISTENING VALIDITY PROTOCOL (R-03 second half — design, unrun)

Goal: prove the 9 qualified fault families match trained ears (agreement κ≥0.6),
or keep the "not qualified for pilot" label. Measurement side is fixed (58/58,
numpy BS.1770); this protocol tests *validity*, not code.

## Corpus (30 clips, ~90 min listening)
- 10 fault-injected synthetics (clip runs, -0.5dBFS hot, digital silence gap,
  6dB L/R imbalance, polarity flip, 30mV DC, -8 LUFS loud, +0.5dBTP hot,
  mono-incompatible wide, healthy control) — ground truth KNOWN by construction.
- 10 real authorized mixes (owner's library, private) — truth by panel consensus.
- 10 boundary cases from the engine's low-confidence tail (like R-01's shortlist
  method: rank `confidence`, take the bottom) — where the claim will live or die.

## Procedure (blind, per clip)
1. Listener gets WAV only (no engine output, no filename hints). Room: headphones
   + monitors, calibrated ~79dB. Form per clip: for each family
   [detected Y/N, severity none/low/high, 1-line note] + overall "would you
   flag this mix to a client? Y/N".
2. Two listeners minimum (owner + one engineer/producer). Engine report generated
   separately and joined AFTER all forms are frozen (CSV join on clip id).
3. Faults scored per family (9 rows × 30 clips), not per clip — a clip can carry
   multiple faults; each family gets its own κ.

## Metrics + thresholds
- Primary: Cohen's κ per family (engine detected vs listener majority), mean
  across families. Ship threshold: mean κ≥0.6 AND no family κ<0.3.
- Secondary: LUFS within ±1.0 of listener-perceived loudness rank order
  (rank correlation, not absolute — ears rank, meters read); true-peak
  direction (engine hot ⇒ listeners call it hot ≥80%).
- Kill: mean κ<0.4 → keep "not qualified", stop pilot talk, file per-family
  error analysis as the next research input.

## Deliverables
- `LISTENING_FORMS.csv` (frozen before join) + `LISTENING_VS_ENGINE.csv`
  (joined) + 1-page verdict. Store next to `mix-review/evaluation/`
  (new files only). Timebox: 1 day listening + half-day analysis.
