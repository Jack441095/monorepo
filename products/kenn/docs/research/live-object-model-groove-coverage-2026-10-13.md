# Live Object Model groove coverage

Recorded: 13 October 2026. This is source evidence for a KENN implementation prompt, not a replacement work queue. `KENN_PLAN.md` remains the sole roadmap. No running Live session was accessed.

## Public API facts

Cycling '74's current Live Object Model reference identifies its target as Live 12.4.5. It describes classes, properties, functions, and object relationships, rather than promising access to every control visible in Live. Its class inventory includes `Groove` and `GroovePool`, but no `Browser` class. Documentation coverage must be distinguished from the installed Live version and the Python Remote Script bridge. [Live Object Model](https://docs.cycling74.com/apiref/lom/)

| Operation | Current public LOM evidence |
| --- | --- |
| Reach the pool | `Song.groove_pool`: get; available since Live 11.0. |
| Enumerate loaded grooves | `GroovePool.grooves`: get/observe; ordered from top to bottom, accessible by index. |
| Assign/read a clip's groove | `Clip.groove`: get/set/observe; available since Live 11.0. |
| Test whether a clip has a groove | `Clip.has_groove`: get only. |
| Adjust grid | `Groove.base`: get/set only; index values 0–5 mean quarter, eighth, eighth-triplet, sixteenth, sixteenth-triplet, and thirty-second note grids. |
| Adjust groove properties | `name`, `quantization_amount`, `random_amount`, `timing_amount`, `velocity_amount`: get/set/observe. |
| Adjust the set's amount | `Song.groove_amount`: get/set/observe, documented range 0.0–1.0. |

Sources: [Song](https://docs.cycling74.com/apiref/lom/song/), [GroovePool](https://docs.cycling74.com/apiref/lom/groovepool/), [Clip](https://docs.cycling74.com/apiref/lom/clip/), [Groove](https://docs.cycling74.com/apiref/lom/groove/).

The `Groove` page names its amount fields as floats without specifying numeric ranges or percentage conversions. KENN must qualify those units in its installed-version adapter before accepting writes; percentages cannot be inferred from the property names. `base` lacks documented observation support. [Groove](https://docs.cycling74.com/apiref/lom/groove/)

## Musical behavior and shared state

Ableton documents `.agr` files in the browser, drag-and-drop onto clips, and double-click loading into the Groove Pool. Grooves work on MIDI and audio; audio requires Warp. Pool parameter changes affect every clip using that groove. Global Amount scales Timing, Random, and Velocity across all grooves, with a UI ceiling of 130%. Commit moves MIDI notes or creates audio Warp Markers, then clears the clip's groove assignment. These are documented product behaviors, not proof of corresponding automation methods. [Using Grooves](https://www.ableton.com/en/live-manual/12/using-grooves/)

The UI's 130% ceiling and `Song.groove_amount`'s documented 0.0–1.0 range do not establish an exact conversion. Version-specific readback qualification is required. [Song](https://docs.cycling74.com/apiref/lom/song/), [Using Grooves](https://www.ableton.com/en/live-manual/12/using-grooves/)

For a request about one track, the implementation implication is to resolve its intended clips and inventory other users of a candidate groove before changing shared parameters. Assigning an existing groove is a narrower first step. Cloning must not be assumed available as the way to isolate edits.

## Unqualified operations

The inspected `GroovePool` reference lists no load, create, clone, or remove function, and the `Clip` function list contains no groove-commit function. Thus these operations are **undocumented in the inspected public LOM**, not proven impossible in Live. Their availability through the private Python Remote Script API remains unknown here; browser loading or UI operations need a separate, explicit qualification. Do not invent accessors such as `load_groove` or `commit_groove`, and do not advertise them merely because the UI supports the action. [GroovePool](https://docs.cycling74.com/apiref/lom/groovepool/), [Clip](https://docs.cycling74.com/apiref/lom/clip/)

## KENN bridge implications

The bundled [clip handler](../../integrations/ableton-osc/abletonosc/clip.py) exposes `has_groove` but comments out `groove` because OSC cannot encode the returned Live object. This is a transport seam, rather than evidence that Live lacks groove assignment. Reuse the existing retained-object, epoch, feature-handshake, and nonce-response patterns in [parameter_target.py](../../integrations/ableton-osc/abletonosc/parameter_target.py); keep Live objects inside the Remote Script and send typed serializable handles and snapshots.

A grounded first slice can enumerate the current pool, rank actual candidates using declared musical metadata, resolve exact clips, propose an assignment, read back the result, and preserve undo. Groove names alone do not establish genre suitability. An empty pool, ambiguous target, stale handle, unsupported version, or unqualified loader should yield a specific supported next step. Tests use the fake backend; real qualification follows [KENN's supervised disposable-session boundary](../../AGENTS.md).

## Scoped baseline verification

From `apps/backend`, `KENN_LIVE_BACKEND=fake PYTHONPATH=src:../../tooling .venv/bin/python -m pytest -q src/kenn/tests/test_live_song_and_track_capabilities.py -k groove` passed: 2 tests, 8 deselected. These existing tests cover global amount, not the proposed pool integration. The documented `.venv/bin/pytest` launcher has a pre-existing stale interpreter path; invoking pytest through the virtual environment's Python succeeded without changing the environment.
