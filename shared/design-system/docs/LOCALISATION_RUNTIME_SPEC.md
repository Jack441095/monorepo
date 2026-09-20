# NITE DSP — Localisation Runtime Spec

**Implements:** `../design_prototypes/ember/NITE_DSP_LOCALISATION_ARCHITECTURE_V1.md` (frozen)
**Code:** `tools/localisation.py` · **Base bundle:** `localisation/strings_en.json`

## Resource format

Flat JSON bundles `strings_<locale>.json`, dotted stable keys, `$meta` block. English (`en`) is the fallback locale and the contract reference. ICU-style plurals supported: `"{count, plural, one {# sample} other {# samples}}"`.

## Runtime contract (`LocalisationManager`)

| Capability | Behaviour |
|---|---|
| Lookup | `get(key)` — current locale → fallback locale → `MissingKeyError` |
| Diagnostics | every miss recorded `(locale, key)`; `missing_key_report()` |
| Runtime switch | `set_locale(locale)` — loads bundle on demand, notifies listeners; unknown locale returns False without notifying |
| Re-layout hook | `on_locale_changed(fn)` — UI layers run their re-layout pass here (risk R4 spike point) |
| Thread safety | `RLock` around bundle map + current locale; reads never block on I/O after load |

## Formatting rules (OD-6)

- **Technical units fixed everywhere:** `format_technical(v, unit)` for Hz/kHz/dB/LUFS/ms/BPM only; raises on non-technical units. `-9.4 LUFS` never becomes `-9,4 LUFS`.
- **Narrative numbers localise:** `format_decimal` (de/es/it/pt/fr comma decimals).
- **Percentages:** locale placement (`94%` / `94 %` French).
- **Dates:** ISO 8601 in technical contexts always.
- Machine schemas, taxonomy IDs, enum values, filenames: never localised.

## CJK policy data

Fallback chains per locale (ja/ko/zh-Hans), line-height ×1.20 for CJK runs, 10px floor strict, no ALL-CAPS assumptions, Latin tabular numerals retained in data contexts.

## RTL policy data

Mirror: sidebar, inspector position, toolbar order, list rows, text alignment, generic progress bars.
**Never mirror:** waveforms, timelines/spectrograms, meters, MAP coordinates, frequency axes (low Hz left), BPM/key values, playhead logic, transport glyphs.

## Text expansion budgets

de ×1.35 · fr ×1.30 · pt ×1.25 · es ×1.20 · ja ×0.85 — used by layout fixtures. Preference order: wrap > expand > icon-substitute > tooltip > ellipsis.
