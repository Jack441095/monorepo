# Measured device evidence

One JSON file per device, written by `tooling/scripts/measure_device_parameters.py` from Live's own display strings
(needs Live open with KENN's AbletonOSC; stop the KENN companion first so the reply port is free):

    python3 tooling/scripts/measure_device_parameters.py --index 3 --device-index 0 --out tooling/data/measured_devices/compressor.json

Two things read this folder:

- `knowledge/measured_facts.py` checks approved notes against these ranges (a note outside a measured range becomes a
  `note_vs_measured` contradiction; the measurement wins). `tooling/scripts/check_notes_against_measurements.py` runs
  it read-only.
- `tooling/scripts/build_parameter_reference.py --out <notes dir>` writes `measured-<device>-<n>.md` parameter notes
  (drafts until you pass `--approve`). The index labels those notes "Measured in Live", the top source tier.

Commit the JSON: it is the record of what Live said, on which date.
