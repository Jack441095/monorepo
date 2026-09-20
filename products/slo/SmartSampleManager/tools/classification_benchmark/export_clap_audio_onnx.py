#!/usr/bin/env python3
"""
Feasibility: export CLAP's AUDIO tower to ONNX and int8-quantise it.

The text tower is never used at inference (class centroids are precomputed),
so shipping it is pure weight. This exports only get_audio_features and
measures the three things that decide whether CLAP can ship: fp32 ONNX size,
int8 size, and whether the exported/quantised paths still match PyTorch.
"""
import os, time, numpy as np, torch
from transformers import ClapModel

MODEL = "clap_model_music"
SR = 48000

class AudioTower(torch.nn.Module):
    def __init__(self, clap):
        super().__init__(); self.clap = clap
    def forward(self, input_features, is_longer):
        return self.clap.get_audio_features(input_features=input_features, is_longer=is_longer).pooler_output

def main():
    from transformers import ClapProcessor
    m = ClapModel.from_pretrained(MODEL).eval()
    proc = ClapProcessor.from_pretrained(MODEL)
    # real preprocessed inputs to trace with
    a = [np.random.randn(SR*3).astype(np.float32)]
    feat = proc(audio=a, sampling_rate=SR, return_tensors="pt")
    keys = {k: feat[k] for k in feat if k in ("input_features","is_longer")}
    print("input keys:", {k: tuple(v.shape) for k,v in keys.items()})
    tower = AudioTower(m).eval()
    with torch.no_grad():
        ref = tower(keys["input_features"], keys.get("is_longer"))
    print("audio feature dim:", tuple(ref.shape))

    os.makedirs("clap_onnx", exist_ok=True)
    fp32 = "clap_onnx/clap_audio_fp32.onnx"
    torch.onnx.export(tower, (keys["input_features"], keys.get("is_longer")), fp32,
        input_names=["input_features","is_longer"], output_names=["audio_embed"],
        dynamic_axes={"input_features":{0:"batch"},"is_longer":{0:"batch"},"audio_embed":{0:"batch"}},
        opset_version=17, do_constant_folding=True)
    sz_fp32 = os.path.getsize(fp32)/1e6
    print(f"fp32 ONNX: {sz_fp32:.0f} MB")

    # verify ONNX matches PyTorch
    import onnxruntime as ort
    sess = ort.InferenceSession(fp32, providers=["CPUExecutionProvider"])
    ins = {"input_features": keys["input_features"].numpy()}
    if "is_longer" in keys: ins["is_longer"] = keys["is_longer"].numpy()
    t0=time.time(); oo = sess.run(None, ins)[0]; dt=time.time()-t0
    err = float(np.max(np.abs(oo - ref.numpy())))
    print(f"fp32 ONNX vs PyTorch max err: {err:.2e}  | 1-clip CPU latency {dt*1000:.0f} ms")

    # int8 dynamic quantization
    from onnxruntime.quantization import quantize_dynamic, QuantType
    int8 = "clap_onnx/clap_audio_int8.onnx"
    quantize_dynamic(fp32, int8, weight_type=QuantType.QInt8)
    sz_int8 = os.path.getsize(int8)/1e6
    sess8 = ort.InferenceSession(int8, providers=["CPUExecutionProvider"])
    o8 = sess8.run(None, ins)[0]
    err8 = float(np.max(np.abs(o8 - ref.numpy())))
    cos8 = float(np.dot(o8.ravel(), ref.numpy().ravel())/(np.linalg.norm(o8)*np.linalg.norm(ref.numpy())))
    print(f"int8 ONNX: {sz_int8:.0f} MB  ({sz_fp32/sz_int8:.1f}x smaller than fp32)")
    print(f"int8 vs PyTorch: max err {err8:.2e}, cosine {cos8:.5f}")
    print(f"\nPANNs ships at 23 MB. CLAP int8 audio tower: {sz_int8:.0f} MB.")

if __name__=="__main__": main()
