# Changelog — NITE DSP Design System

All notable changes to the design system are documented here.
Format follows Keep a Changelog; versioning follows DS §21 change control
(1.0.x = clarifications, accessibility corrections, documentation fixes — no identity change).

## [1.0.1] — 2026-08-22

### Fixed (accessibility correction)

- **`color.text.tertiary`: `#6E675E` → `#827B71`.** The frozen 1.0.0 spec claimed tertiary text
  achieved "≥4.6:1" on base; measured WCAG 2.x relative-luminance contrast was **3.53:1** — a
  contradiction with both the claim and the accessibility requirement for its role.

### Design decision record

**Role of tertiary text.** DS §3.2 defines it as the "contrast floor for readable metadata";
DS §7/§11 use it for units at −1px, 9–10px mono grid labels, captions and secondary UI copy.
This is normal body-size text (well under 18pt/14pt-bold), so **WCAG 2.x AA SC 1.4.3
(Contrast Minimum) applies: ≥4.5:1**. The large-text exception (≥3:1, SC 1.4.6) does not apply.

**Measured math (WCAG 2.x relative luminance).**
Base `#0C0B09` luminance L = 0.003372.

| Token | Hex | Ratio on base | Spec claim | AA body (≥4.5) |
|---|---|---|---|---|
| text.primary | `#EDE8E0` | 16.13 | 15 | pass |
| text.secondary | `#A39B8F` | 7.16 | 7 | pass |
| text.tertiary (1.0.0) | `#6E675E` | **3.53** | 4.6 | **fail** |
| text.tertiary (1.0.1) | `#827B71` | **4.70** | 4.7 | pass |

(`#6E675E` also fell below floor on raised surfaces: 3.35 on `#14120F`, 3.14 on `#1C1915`,
3.24 on hover `#191612`, 3.04 on modal `#201C16`. `#827B71` clears ≥4.5 on base and remains
the readable-metadata floor per spec intent; metadata on lighter raised surfaces should be
verified per-component.)

**Correction selection.** Constraint: meet ≥4.6:1 (spec's own floor) with margin, keep hue
family, minimal lightness shift, no other token touched. Tertiary sits in HSL space at
hue ≈ 34°, saturation ≈ 0.078, lightness 0.400. A pure-lightness lift of +0.072 (L → 0.472)
at constant hue/saturation yields `#827B71` at **4.70:1** — the smallest whole-hex step that
clears the floor with margin while remaining visibly "one step dimmer than secondary"
(preserving the primary > secondary > tertiary hierarchy). Candidates between were rejected:
`#807970` = 4.58 (below the spec's own 4.6), `#817A70` = 4.64 (margin < 0.05).

**Scope guard.** Only `color.text.tertiary` changed value; `contrastOnBase` metadata updated
to the measured 4.7. All other frozen colours byte-identical. Validator golden snapshot
updated via the sanctioned 1.0.x route (DS §21); version bumped 1.0.0 → 1.0.1; `frozen`
remains true with freeze date unchanged.

## [1.0.0] — 2026-08-22

- Initial frozen release of EMBER — Warm Technical Minimalism.
