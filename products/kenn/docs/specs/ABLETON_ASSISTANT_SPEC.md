# KENN Ableton Assistant Specification

Status: internal qualification, not a release approval.

## Operating modes

* **Ask** answers from the indexed KENN audio/Ableton notes.
* **Inspect** reads a supplied WAV or an explicit, fresh Live snapshot.
* **Analyse** runs deterministic PCM measurements and reports evidence.
* **Suggest** separates measured fact, interpretation, possible cause, listening test, Ableton workflow, and uncertainty.
* **Assist** creates a bounded action proposal without executing it.
* **Execute** is the only mutation mode and requires an exact, unexpired, single-use confirmation token.
* **Auto** is disabled. It cannot silently mutate Live.

KENN must say when audio or Live state is absent. A filename, metadata, or model knowledge is not audio evidence.

## Execution pipeline

`Inspect -> Plan -> Propose -> Confirm -> Execute -> Read back -> Receipt -> Undo`

The current implementation owns the intent parser (`apps/backend/src/kenn/core/live_intent.py`), proposal boundary (`live_control_planner.py`), HMAC confirmation (`confirmation.py`), and executor (`live_executor.py`). The Remote Script is a separate integration boundary and must be validated in a real Live session.

## Supported initial writes

Volume, pan, mute, solo, arm, transport play/stop, and explicitly inspected device parameters are the intended initial set. Track/device/parameter names must come from Live state. Delete, overwrite, project replacement, clip loading, scene/device creation, and sidechain topology changes remain disabled for this qualification surface.

## Evidence rules

Measured facts are labelled as measurements. FFT peaks, resonance candidates, masking candidates, and harshness candidates are hypotheses, never proof. LUFS and true peak are not reported by the KENN-owned analyzer until calibrated reference tests exist.
