# Device factory: teaching KENN every parameter of every Live device

**Status (29 Sept 2026):** the tooling is built and tested against stand-ins. **0 of Live's 78 devices are measured or
qualified yet.** That needs Live open on your Mac; nothing in this file has run against real Live.

## What "KENN can edit it" means here

| Class | Example | What KENN needs before it will set it |
|---|---|---|
| Numeric, shown in a unit | Compressor Attack (ms), Auto Filter Frequency (Hz), Saturator Drive (dB) | a **qualified profile**: how Live's raw value maps to the displayed number |
| Chooser or switch | Compressor Model (Peak / RMS / Expand), Auto Release (Off / On) | a **qualified option table**: the label Live shows for each raw value |
| Bare number, no unit | many macros and internal values | nothing can be said in real units: KENN sets it by raw value only, and says so |
| Third-party plug-ins, devices inside racks | Pro-Q 3, a Rack's chains | not covered (parameter reads address top-level Live devices) |

KENN sees every parameter of every device already. What it refuses to do is *guess* what a number means: a value with
no qualified mapping is declined with "that control hasn't been measured in Live yet".

## The four steps (each one is safe to rerun)

1. **Set up a "device zoo" set.** A disposable Live set with one of each device you want, on ordinary tracks (not only
   returns or the master, and not inside racks). Give them their default names.
2. **Measure** (read-only, Live open, KENN companion stopped so the AbletonOSC port is free):
   `python3 tooling/scripts/measure_all_devices.py` writes `tooling/data/measured_devices/<device>.json`, one per device
   type, from Live's own display strings. `--only "EQ Eight,Compressor"` for a first wave; `--force` to redo one.
3. **Build candidates and see coverage** (offline):
   `python3 tooling/scripts/build_device_profiles.py --live-app "/Applications/Ableton Live 12 Suite.app"`
   writes `tooling/data/device_profile_candidates/`, and prints how many devices are measured of those installed, plus
   candidate profiles, choosers and unmapped parameters with the reason for each. Candidates are **not** loaded.
4. **Qualify** (writes to Live; disposable set, monitors low, KENN companion running):
   `python3 tooling/scripts/qualify_device_candidates.py` first, with no flag, only checks each proposal can be made.
   Then `--apply`. For every parameter it sets three values (about 20%, 50% and 80% of the range), reads Live's display
   string back, compares it with what the mapping predicted, and restores the original through KENN's confirmed undo.
   A dB control is never taken above 0 dB. A chooser has up to three options set and Live's own label must match each.
   Parameters that pass are written to `apps/backend/src/kenn/core/device_profiles/<device>.json` with their transcript in
   `tooling/data/device_qualification/`; `core/device_units.py` loads only entries that carry a passed qualification.
   `--device` and `--parameter` narrow a run. Commit the JSON: it is the record of what Live said.

After that, "set the Operator filter frequency to 2 kHz", "set the compressor model to RMS" and "turn auto release on"
work through the normal proposal → Apply → readback → receipt → undo path. Nothing else changes.

## Safety, as built

- Candidates never load; only a passed qualification does (`test_device_profile_files.py`).
- The hand-verified profiles in `device_units.py` win any clash, and the qualifier skips them.
- The device's own on/off, bypass and mute are still refused; the qualifier never toggles `Device On`.
- A value outside a control's range is still refused after conversion.
- Notes are checked against the measured ranges (`check_notes_against_measurements.py`), and parameter-reference notes
  can be generated from the same evidence (`build_parameter_reference.py`).

## Known limits

- Only devices on regular tracks can be qualified; returns and the master can be measured but not qualified by this tool.
- Relative changes ("up 3 dB") on a table or logarithmic control go through a display round trip, so they need a
  qualified profile too.
- A parameter whose display isn't a number, or is a bare number with no unit, is reported as unmapped and stays raw-only.
- Live's `str_for_value` precision limits how tight the check can be: the tolerance is half the last digit shown plus 1%
  (log) or 0.5% of the span (linear and tables).
