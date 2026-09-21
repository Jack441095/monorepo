# KENN AutoMix boundary

This is the product-owned boundary for a local, human-approved AutoMix run.
It calls the existing `Audio_Too/scripts/automix_local.py` pipeline without
modifying that repository or copying its implementation.

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
