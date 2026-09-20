# Ableton Live qualification evidence

`scripts/qualify_ableton_live.py` is a read-only probe. Its output schema is
`kenn.ableton_qualification.v1`.

`--mode real` calls the KENN OSC client and is allowed to pass only when Live
returns a connected snapshot with exact track indices and names. `--mode mock`
uses a deterministic fixture and is labelled `evidence_kind:
deterministic_mock`; it is useful for harness tests but cannot close the real
Live gate.

The captured `session_version` is a SHA-256 hash of the returned snapshot.
The probe does not mutate Live and does not claim write, readback, native undo,
timeout recovery, or crash/restart qualification.

Examples:

```bash
python3 scripts/qualify_ableton_live.py --mode mock
python3 scripts/qualify_ableton_live.py --mode real --output /tmp/kenn-live-qualification.json
```
