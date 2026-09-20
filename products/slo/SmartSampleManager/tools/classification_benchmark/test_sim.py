import torch
import torch.nn.functional as F
import numpy as np

def gelu(x):
    # PyTorch default GELU (tanh approximation or exact erf)
    return 0.5 * x * (1.0 + torch.erf(x / np.sqrt(2.0)))

def layer_norm(x, weight, bias, eps=1e-5):
    mean = x.mean(dim=-1, keepdim=True)
    var = ((x - mean) ** 2).mean(dim=-1, keepdim=True)
    return (x - mean) / torch.sqrt(var + eps) * weight + bias

def forward_cpp_sim(x, state_dict):
    # 1. fc1
    h = x @ state_dict["fc1.weight"].T + state_dict["fc1.bias"]
    h = layer_norm(h, state_dict["ln1.weight"], state_dict["ln1.bias"])
    h = gelu(h)

    def run_block(inp, prefix):
        w1 = state_dict[f"{prefix}.fc1.weight"]; b1 = state_dict[f"{prefix}.fc1.bias"]
        g1 = state_dict[f"{prefix}.ln1.weight"]; beta1 = state_dict[f"{prefix}.ln1.bias"]
        w2 = state_dict[f"{prefix}.fc2.weight"]; b2 = state_dict[f"{prefix}.fc2.bias"]
        g2 = state_dict[f"{prefix}.ln2.weight"]; beta2 = state_dict[f"{prefix}.ln2.bias"]

        s1 = gelu(layer_norm(inp @ w1.T + b1, g1, beta1))
        s2 = gelu(layer_norm(s1 @ w2.T + b2, g2, beta2))
        return inp + s2

    # 2. Block 1, 2, 3
    if "block1.fc1.weight" in state_dict:
        b1 = run_block(h, "block1")
        b2 = run_block(b1, "block2")
        b3 = run_block(b2, "block3")

        # ArcFace head
        h_norm = torch.norm(b3, p=2, dim=-1, keepdim=True).clamp(min=1e-12)
        w_norm = torch.norm(state_dict["arc_head.weight"], p=2, dim=-1, keepdim=True).clamp(min=1e-12)
        cos_sim = (b3 / h_norm) @ (state_dict["arc_head.weight"] / w_norm).T
        scale_factor = float(state_dict.get("scale_factor", 30.0))
        return cos_sim * scale_factor
    else:
        # Legacy V2/V3 architecture fallback
        res = gelu(layer_norm(gelu(layer_norm(h @ state_dict["res_fc1.weight"].T + state_dict["res_fc1.bias"], state_dict["res_ln1.weight"], state_dict["res_ln1.bias"])) @ state_dict["res_fc2.weight"].T + state_dict["res_fc2.bias"], state_dict["res_ln2.weight"], state_dict["res_ln2.bias"]))
        h = gelu(h + res)
        res2 = gelu(layer_norm(gelu(layer_norm(h @ state_dict["res2_fc1.weight"].T + state_dict["res2_fc1.bias"], state_dict["res2_ln1.weight"], state_dict["res2_ln1.bias"])) @ state_dict["res2_fc2.weight"].T + state_dict["res2_fc2.bias"], state_dict["res2_ln2.weight"], state_dict["res2_ln2.bias"]))
        h = gelu(h + res2)
        return (h @ state_dict["out.weight"].T + state_dict["out.bias"]) / state_dict.get("temperature", 1.0)

import os

script_dir = os.path.dirname(os.path.abspath(__file__))
ckpt_path = os.path.join(script_dir, "slo_classifier_v2.pt")
data_path = os.path.join(script_dir, "slo_embeddings_v2.npz")

def test_forward_sim():
    if not os.path.exists(ckpt_path) or not os.path.exists(data_path):
        return
    ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    state_dict = ckpt["state_dict"]

    data = np.load(data_path)
    X = torch.tensor(data["embeddings"][:10], dtype=torch.float32)

    sim_logits = forward_cpp_sim(X, state_dict)
    assert sim_logits.shape == (10, 16)
    print("Simulation output shape:", sim_logits.shape)
    print("Simulation output top-1 classes:", [ckpt["classes"][i] for i in sim_logits.argmax(dim=-1)])

if __name__ == "__main__":
    test_forward_sim()
