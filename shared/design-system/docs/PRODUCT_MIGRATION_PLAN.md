# NITE DSP — Product Migration Plan (SLO · KENN · Website)

**Status:** PLANNING ONLY. DS-I10/DS-I11/DS-I12 are NOT started. Execution requires explicit owner authorisation and, per OWNERSHIP.md, a claimed branch per product.

Read-only inspection basis: canonical workspace map (`../CANONICAL_WORKSPACE.md`), ownership policy (`../OWNERSHIP.md`), frozen backlog. No production files were read beyond repo metadata in this phase; file-level mapping below is derived from the canonical workspace map and must be re-verified at execution time.

---

## 1. SLO migration (DS-I10) — after SLO closeout

**Repo:** `Nite_DSP/Nite_DSP_01` (canonical `main`; UX stream `ux/slo-v3-premium-product`). **Prereqs:** DS-I06, DS-I07, DS-I08 complete (they are, as foundation).

Dependency-ordered phases:

1. **Token ingestion** — replace `DesignTokens.h` contents with `generated/cpp/NiteDesignTokens.h` include + alias shim; map every existing hardcoded colour to a `nite::design::ColourRole`. Grep-audit for residual hex literals (review failure per DS §15).
2. **LookAndFeel swap** — introduce `NiteLookAndFeel` subclass; register ColourIds from the documented bands; route buttons/tabs/scrollbars/text fields through shared primitives.
3. **Typography** — embed Inter Regular/Medium/Semibold + one mono; wire `TypeRole` scale; enable tabular figures in table/meter readouts.
4. **Category chips + LIST rows** — CategoryChip (dot+label), TableRow states (playing ▶ / selected copper edge+fill / favorite ★).
5. **MAP** — MapPoint with R-CVD-1 shape coding default-on; selected ring + label card; playing halo pulse 400ms single-shot; OOD dashed hollow; cluster expand 200ms.
6. **Inspector / Preferences / dialogs** — modal budget ≤10% copper, one primary action max.
7. **Localisation** — replace literal UI strings with resource keys via generated key constants; runtime switcher in Preferences; re-layout pass on locale change.

Risks: MAP >2k points render path (spike R3), damped pan/zoom behaviour, dashed handle hit-testing, HiDPI 1×–3× sweep.

## 2. KENN migration (DS-I11) — after SLO proves the component base

**Repo:** `Audio_Too` (`analysis/efficiency-and-streaming-core`, Thursday/KENN stream). Read-only mapping targets: UI layers rendering evidence panels, recommendation states, confidence display, Automix proposal UI.

Phases:

1. Severity badges → `kenn.severity.*` aliases with mandatory text chips (C-05).
2. ConfidenceIndicator — qualitative chip default, micro-bar secondary, exact % on demand (C-06); LOW gains "?" affordance.
3. AIProposal component — dashed copper + "provisional" tag → solid authoritative on accept (200ms transition); MACHINE PROPOSAL = PROVISIONAL grammar enforced in state machine.
4. Evidence/spectrum panels inherit viz grammar (§11): neutral graphs, reference dashed 5-4, deviation warning tint ≤8%.
5. Localisation keys for analysis labels (`analysis.low_mid_buildup`, …).

## 3. Website mapping (DS-I12)

**Repo:** `Nite_DSP/Nite_DSP_01-web-v3` (`web/nitedsp-world-class-v3`). Phases:

1. Import `generated/web/nite-tokens.css` custom properties; map existing CSS variables onto `--nite-*` names; delete orphaned hexes.
2. Typography scale-up (Display role permitted here only), editorial whitespace replacing plugin chrome; no fake window frames (DS §17).
3. Accent budget up to 12% on marketing surfaces; CTAs + key viz accents only.
4. Product imagery = genuine EMBER UI renders on EMBER backdrops.

## 4. Execution rules for all three

- Claim branch per OWNERSHIP.md before any write; verify remote/branch/HEAD first.
- Frozen global tokens may not be altered by product work (DS §21); products add alias layers only.
- Each phase lands behind its own commit series with golden-token validation in CI (`token_validator.py` + determinism check).
- Any spec contradiction discovered mid-migration: STOP that item, record it, escalate to design-system owner.
