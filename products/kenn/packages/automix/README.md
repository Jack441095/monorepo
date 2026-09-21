# KENN AutoMix boundary

**Beta status: disabled.** This module calls
`Audio_Too/scripts/automix_local.py`, an external rendering pipeline that
does not exist in this standalone repository (and is not reachable without a
separate `Audio_Too` checkout). Calling `run_approved_local_automix(...)`
here will return a `status: "failed"` receipt with a clear error rather than
crash or silently do nothing -- see `docs/KENN_BETA_GAP_MATRIX.md` for the
classification and replacement plan (a KENN-owned local render pipeline has
not been built; this is out of scope for the current beta).

This is the product-owned safety boundary for a local, human-approved
AutoMix run, kept in place so the approval-gate, receipt, and output-path
safety contract are ready once a KENN-owned (or explicitly re-authorised
external) render engine exists. It calls the existing
`Audio_Too/scripts/automix_local.py` pipeline without modifying that
repository or copying its implementation.

The adapter is deliberately not an HTTP service. It accepts a local stems
directory, requires an explicit `approved=True` call before rendering, and
writes delivery artifacts outside `Audio_Too`. Audio is read locally and is
not uploaded, persisted by the adapter, or sent to an external service.

This is an engineering boundary, not a public product qualification. A public
portfolio surface must not expose unattended mix generation, arbitrary file
uploads, or the local delivery artifacts.

## Use

```python
from pathlib import Path

from adapter import run_approved_local_automix

receipt = run_approved_local_automix(
    Path("./stems"),
    approved=True,
    project_id="portfolio-demo",
)
```

Without `approved=True`, the adapter returns an `awaiting_human_approval`
receipt and does not call the engine.
