"""
Exports PANNs Cnn10 (audio embedding, 512D) to ONNX for use in
SampleManagerEngine, replacing the untrained placeholder model.

Model: Cnn10 from qiuqiangkong/audioset_tagging_cnn
Checkpoint: Cnn10_mAP=0.380.pth (25.2MB), from https://zenodo.org/record/3987831
License: MIT (code), trained on AudioSet (Google, CC BY 4.0) -- verified
    both directly against source, not from memory. See
    THIRD_PARTY_LICENSES.md for the full audit.
Trained hyperparameters (must match exactly or the mel-filterbank features
the model expects won't line up with what it learned):
    sample_rate=32000, window_size=1024, hop_size=320, mel_bins=64,
    fmin=50, fmax=14000, classes_num=527 (AudioSet ontology size)

Only the 512D embedding output is exported (the AudioSet classifier head
is discarded) -- this app uses it for acoustic similarity search, not
AudioSet tag classification.
"""
import sys
import torch
import torch.nn as nn

sys.path.insert(0, ".")
from pann_models_full import Cnn10


class Cnn10EmbeddingOnly(nn.Module):
    """Wraps Cnn10, exposing only its 512D embedding output (discards the
    527-way AudioSet classification head) -- ONNX export needs a single
    tensor output, not the dict Cnn10.forward() returns."""

    def __init__(self, cnn10: Cnn10):
        super().__init__()
        self.cnn10 = cnn10

    def forward(self, waveform: torch.Tensor) -> torch.Tensor:
        return self.cnn10(waveform)["embedding"]


def main():
    model = Cnn10(
        sample_rate=32000, window_size=1024, hop_size=320,
        mel_bins=64, fmin=50, fmax=14000, classes_num=527,
    )
    checkpoint = torch.load("Cnn10_mAP=0.380.pth", map_location="cpu", weights_only=False)
    model.load_state_dict(checkpoint["model"])
    model.eval()

    wrapped = Cnn10EmbeddingOnly(model)
    wrapped.eval()

    # 32kHz, matching the 5-second analysis window SampleManagerEngine already
    # uses for the ML embedding path (was 44100*5=220500 for the placeholder
    # model; PANNs needs 32000*5=160000 at its trained sample rate instead).
    dummy_input = torch.randn(1, 160000)

    with torch.no_grad():
        reference_output = wrapped(dummy_input)
    print(f"Reference embedding shape: {reference_output.shape}")
    assert reference_output.shape == (1, 512), "Expected a 512D embedding"

    torch.onnx.export(
        wrapped,
        dummy_input,
        "panns_cnn10_embedding.onnx",
        input_names=["input"],
        output_names=["output"],
        dynamic_axes={"input": {0: "batch", 1: "num_samples"}, "output": {0: "batch"}},
        opset_version=17,
    )
    print("Exported panns_cnn10_embedding.onnx")


if __name__ == "__main__":
    main()
