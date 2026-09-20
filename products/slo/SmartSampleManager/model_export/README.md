# Model export tooling

Reproduces `../Models/panns_cnn10_embedding.onnx` from the original PANNs
Cnn10 checkpoint. See `../Models/README.md` for what the model is, its
license, and how its output was verified (numerical parity + acoustic
meaningfulness checks).

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt

# Fetch the trained checkpoint (25MB) and its model-definition source --
# not committed to the repo, this script re-downloads them each time:
curl -sL -o pann_models_full.py https://raw.githubusercontent.com/qiuqiangkong/audioset_tagging_cnn/master/pytorch/models.py
curl -sL -o pytorch_utils.py https://raw.githubusercontent.com/qiuqiangkong/audioset_tagging_cnn/master/pytorch/pytorch_utils.py
curl -sL -o "Cnn10_mAP=0.380.pth" "https://zenodo.org/record/3987831/files/Cnn10_mAP%3D0.380.pth?download=1"

./.venv/bin/python export_cnn10.py
# -> panns_cnn10_embedding.onnx + panns_cnn10_embedding.onnx.data
# Copy both into ../Models/ to replace the shipped model.
```

`pann_models_full.py` and `pytorch_utils.py` in this directory are commited
as-fetched (unmodified, straight from the upstream repo at the commit this
was built against) for reproducibility, in case upstream changes later.
The checkpoint itself (`.pth`, 25MB) and the venv are not committed --
regenerate via the curl command above.
