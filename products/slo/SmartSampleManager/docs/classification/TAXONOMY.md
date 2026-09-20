# NITE DSP SLO — Taxonomy Audit

This document describes the taxonomy hierarchy, subcategory mapping rules, loop-vs-one-shot heuristics, and naming issues in the current SLO taxonomy engine.

## 1. The Core Hierarchy

The taxonomy maps the coarse `instrumentType` strings (from heuristics or DSP classification) to Ableton Live-compatible categories and subcategories.

| Coarse Type (`instrumentType`) | Category | Subcategory (One-Shot) | Subcategory (Loop) | Base Confidence |
| :--- | :--- | :--- | :--- | :--- |
| **Kick** | Drums | Kick | Drum Loop | 0.85 |
| **Snare** | Drums | Snare | Drum Loop | 0.80 |
| **Hi-Hat** | Drums | Hat | Drum Loop | 0.80 |
| **Clap** | Drums | Clap | Drum Loop | 0.80 |
| **Percussion** | Drums | Percussion | Drum Loop | 0.70 |
| **Bass** | Bass | Bass One-Shot | Bass Loop | 0.75 |
| **Synth** | Instruments | Synth | Synth Loop | 0.60 |
| **Vocal** | Vocals | Vocal Phrase | Vocal Loop | 0.70 |
| **Explosion** | FX | Impact | *N/A (One-Shot Only)* | 0.60 |
| **Impact** | FX | Impact | *N/A (One-Shot Only)* | 0.60 |
| **Laser** | FX | Riser | *N/A (One-Shot Only)* | 0.45 |
| **Powerup** | FX | FX | *N/A (One-Shot Only)* | 0.40 |
| **Jump** | FX | FX | *N/A (One-Shot Only)* | 0.40 |
| **Coin** | FX | FX | *N/A (One-Shot Only)* | 0.40 |
| **UI** | FX | FX | *N/A (One-Shot Only)* | 0.50 |
| **Footstep** | FX | Foley | *N/A (One-Shot Only)* | 0.60 |

### Special Loop Catch-All Mapping
If `instrumentType == "Loop"`:
* **Noise-like** (ZCR > 0.25 and Low Energy Ratio < 0.5):
  * **Category**: `Ambience`
  * **Subcategory**: `Atmosphere`
  * **Secondary Tags**: `{"Loop", "Atonal"}`
  * **Confidence**: `0.40`
* **Tonal/Rhythmic**:
  * **Category**: `Instruments`
  * **Subcategory**: `Music Loop`
  * **Secondary Tags**: `{"Loop"}`
  * **Confidence**: `0.40`

---

## 2. Loop vs. One-Shot Heuristics

Loop vs. one-shot detection is controlled by `AbletonTaxonomy::detectLoopVsOneShot(float durationSeconds, float decayTimeSeconds)`:

1. **Loop Conditions** (requires *both* to be true):
   * `durationSeconds > 1.5`
   * `decayTimeSeconds / durationSeconds > 0.6` (the energy is sustained across a high portion of the clip)
   * **Confidence**: `0.65`
2. **One-Shot Conditions**:
   * `durationSeconds <= 1.5` AND `decayTimeSeconds < 0.35` (short, fast-decaying)
   * **Confidence**: `0.60`
3. **Ambiguous Default**:
   * If neither is met, defaults to **One-Shot** (the most common type in libraries).
   * **Confidence**: `0.25`

---

## 3. Taxonomy Design Observations & Gaps

### Key and tempo presentation

The stored key keeps its musical mode (`B Major`, `C# Minor`) for search and
loop metadata. In producer-facing names and key fields, one-shots are rendered
as a pitch class only (`B`, `C#`) because a single hit does not establish a
major/minor scale. BPM is exposed for loop subcategories; one-shots and
sound-design assets remain tempo-unknown, including legacy rows that carried
the old 120 BPM fallback.

Tempo evidence follows a precedence chain: embedded metadata, an explicit
filename BPM marker, then a strict loop-plus-key filename convention such as
`Loop_110_Fm`, and finally acoustic estimation. For acoustic estimation, the
5-second embedding view is paired with a bounded 20-second tempo view for long
files; only estimates agreeing within 2 BPM are retained. A disagreement stays
unknown rather than presenting a confident half/double-time guess.

* **Hi-Hat Subcategory String**: The classification maps `Hi-Hat` type to subcategory `"Hat"`. While compact, this is a minor naming shift from the source label `Hi-Hat`.
* **Ambience Category**: It is used exclusively as a fallback for noisy loops (`Atmosphere`), which means standard field recording textures or tonal pads that aren't loops are not yet represented.
* **Overlapping / Vague Mapping**: `Synth` maps to `Instruments / Synth` or `Instruments / Synth Loop` with a relatively low confidence (`0.60`).
* **One-Shot Defaults**: The default fallback to one-shot when loop-vs-one-shot is ambiguous yields a low confidence (`0.25`), which correctly alerts the UI that the classification is a guess.
* **No Multi-Label Support**: The primary classification fields (`category` and `subcategory`) are single-valued, though the `secondaryTags` vector allows list-like tags (e.g. `{"One-Shot", "Atonal"}`).
