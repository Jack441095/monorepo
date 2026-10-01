# Wave-1 device zoo: the set to build before Live night 1

**Written:** 2026-09-30 · **For:** Live night 1 (~2 h, the device factory wave) · **Task:** A2

Twelve regular tracks, one device each. Build it once and the night is measure → build → qualify with nothing to
prepare. The rehearsal in `tooling/scripts/prep_device_zoo.py` runs the whole pipeline against `FakeLiveBackend`
first, so the two hours are not spent discovering the set is wrong.

## The twelve tracks

Give each track the device's **default name** — `measure_all_devices.py` keys its evidence files and its `--only`
filter on the name Live reports, and the qualifier finds each device by that same string. Name the track after the
device too; the walkthrough is easier to read and nothing depends on it.

| # | Track name | Device | Drop in by hand? |
|---|---|---|---|
| 1 | EQ Eight | EQ Eight | no |
| 2 | Compressor | Compressor | no |
| 3 | Utility | Utility | **yes** |
| 4 | Limiter | Limiter | **yes** |
| 5 | Reverb | Reverb | **yes** |
| 6 | Hybrid Reverb | Hybrid Reverb | no |
| 7 | Delay | Delay | **yes** |
| 8 | Echo | Echo | no |
| 9 | Saturator | Saturator | no |
| 10 | Auto Filter | Auto Filter | no |
| 11 | Glue Compressor | Glue Compressor | no |
| 12 | Multiband Dynamics | Multiband Dynamics | no |

Three rules the scripts depend on:

- **Regular tracks only.** Nothing on a return, nothing on the master. `qualify_device_candidates.locate()`
  searches `state["tracks"]` and nothing else, so a device on a return is reported as *"not on a regular track in the
  open set"* and never qualifies.
- **Nothing inside a rack.** Parameter reads address top-level devices, so a rack's contents are invisible to the
  sweep. Drag the device out onto the track.
- **One of each.** `sweep()` keys on the device's class, so a second copy on another track is skipped and buys nothing.

### The four that have to be dragged in by hand

`DEVICE_INSERTION_ALLOWLIST` has ten names and four of these are not on it, so KENN cannot build this set by script:

- **Reverb** and **Delay** — AbletonOSC's browser search resolved `"Reverb"` to Convolution Reverb and `"Delay"` to
  Align Delay on real Live (2026-09-05). Inserting by name would put the wrong device in.
- **Limiter** — deliberately refused. The planner prompt and `validate_llm_plan` do not offer it, so adding it to the
  allowlist would widen a set that was narrowed on purpose.
- **Utility** — not a naming problem. The 2026-09-21 unit probe found `Utility | Gain` has no usable points and the
  real control is `Utility | Output`, which has no profile at all. Night 1 measures it.

Two devices already in the allowlist are **not** in wave 1: `Drum Buss` and `Roar` are hand-verified already, so
they come back in wave 2 if the target needs the breadth.

## Before the night

From `products/kenn`, with Live **closed**:

```
python3 tooling/scripts/prep_device_zoo.py
```

It checks every name against the exact browser names in `core/stock_devices.py`, prints which devices need a hand
drag, lists the parameters `device_units.py` already covers by hand (the qualifier skips those, so they will not
count towards the night's ≥ 40), and rehearses the sweep, the candidate build and the unapplied qualifier on
`FakeLiveBackend`.

The rehearsal's numbers are the ones it got on 2026-09-30: **12 of 12 devices measured, 35 candidate profiles, 17
choosers, 1 unmapped** (EQ Eight's Q, which Live shows as a bare `1.00` with no unit, so there is nothing to convert
to and KENN correctly leaves it raw-only). It makes every proposal without writing anything, which is what proves
each device is on a regular track.

## The night

Build the set, then from `products/kenn`:

1. **Companion stopped**, Live open, the set loaded:

   ```
   python3 tooling/scripts/measure_all_devices.py --only "EQ Eight,Compressor,Utility,Limiter,Reverb,Hybrid Reverb,Delay,Echo,Saturator,Auto Filter,Glue Compressor,Multiband Dynamics"
   ```

   Read-only. Writes `tooling/data/measured_devices/<device>.json`, one per device, from Live's own display strings.
   `--force` redoes one. Watch for `racks (n)` in the summary — a non-zero count means something is inside a rack and
   was not measured.

2. **Offline**, with the companion still stopped:

   ```
   python3 tooling/scripts/build_device_profiles.py --live-app "/Applications/Ableton Live 12 Suite.app"
   ```

   Prints the coverage table and how many of Live's installed devices still have no evidence.

3. **Companion running**, monitors low:

   ```
   python3 tooling/scripts/qualify_device_candidates.py
   ```

   Makes every proposal and writes nothing. This is the cheap run; do it before `--apply`.

4. Then `--apply`. Each parameter is set at three values, Live's display is read back and compared with what the
   mapping predicted, and the original value is restored through KENN's confirmed undo.

Passing parameters land in `core/device_profiles/<device>.json` with the transcript in
`tooling/data/device_qualification/`. **Commit both** — the JSON is the record of what Live said, and
`core/device_units.py` loads only entries carrying a passed qualification.

## Expected outcome, and the target

The week-1 exit is **≥ 12 devices swept and ≥ 40 parameters qualified**. Twelve swept is the whole wave above. The
≥ 40 has to come from the parameters that are *not* already hand-verified: 16 of the 20 existing profiles fall on
Compressor, Auto Filter, Saturator, Glue Compressor, EQ Eight, Echo and Hybrid Reverb, and the qualifier skips those.
If the night lands under 40, the shortfall is parameters on the twelve devices, not devices — send the count and the
`skipped` list back and wave 2 can be ordered from it.

## What to send back

- The `measure_all_devices.py` summary, including any `failed` and `racks` lines.
- The `build_device_profiles.py` coverage table.
- The `qualify_device_candidates.py --apply` `passed` / `failed` / `skipped` lists.
- Any parameter that failed with *"Live showed X, mapping predicted Y"* — that is a measured fact about the device
  and it goes in the note, not in a retry.