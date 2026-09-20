#!/usr/bin/env python3
"""
Exports trained DeepResidualMLP PyTorch weights and centroids to C++ headers for SLO SmartSampleManager.
Generates:
1. AcousticClassifierWeights.h
2. AcousticClassifierCentroids.h
3. parity_references.json
"""

import os
import sys
import json
import numpy as np
import torch

def export_mlp(checkpoint_path, weights_out_h, centroids_out_h, parity_out_json, dataset_npz):
    ckpt = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    state_dict = ckpt["state_dict"]
    classes = ckpt["classes"]
    num_classes = len(classes)
    embed_dim = 512
    temp = float(state_dict.get("temperature", torch.tensor([1.0])).item())

    # Format class names
    class_names_str = ", ".join(f'"{c}"' for c in classes)

    def format_2d_array(tensor, name):
        arr = tensor.numpy() # [out_dim, in_dim]
        out_dim, in_dim = arr.shape
        lines = []
        for i in range(out_dim):
            row_str = ", ".join(f"{arr[i, j]:.8f}f" for j in range(in_dim))
            lines.append(f"        {{ {row_str} }}")
        block = ",\n".join(lines)
        return f"    inline constexpr float {name}[{out_dim}][{in_dim}] = {{\n{block}\n    }};\n"

    def format_1d_array(tensor, name):
        arr = tensor.numpy() # [dim]
        dim = arr.shape[0]
        row_str = ", ".join(f"{arr[i]:.8f}f" for i in range(dim))
        return f"    inline constexpr float {name}[{dim}] = {{ {row_str} }};\n"

    print("Formatting weights...")
    fc1_w = format_2d_array(state_dict["fc1.weight"], "fc1_weights")
    fc1_b = format_1d_array(state_dict["fc1.bias"], "fc1_biases")
    ln1_w = format_1d_array(state_dict["ln1.weight"], "ln1_gamma")
    ln1_b = format_1d_array(state_dict["ln1.bias"], "ln1_beta")

    b1_fc1_w = format_2d_array(state_dict["block1.fc1.weight"], "block1_fc1_weights")
    b1_fc1_b = format_1d_array(state_dict["block1.fc1.bias"], "block1_fc1_biases")
    b1_ln1_w = format_1d_array(state_dict["block1.ln1.weight"], "block1_ln1_gamma")
    b1_ln1_b = format_1d_array(state_dict["block1.ln1.bias"], "block1_ln1_beta")
    b1_fc2_w = format_2d_array(state_dict["block1.fc2.weight"], "block1_fc2_weights")
    b1_fc2_b = format_1d_array(state_dict["block1.fc2.bias"], "block1_fc2_biases")
    b1_ln2_w = format_1d_array(state_dict["block1.ln2.weight"], "block1_ln2_gamma")
    b1_ln2_b = format_1d_array(state_dict["block1.ln2.bias"], "block1_ln2_beta")

    b2_fc1_w = format_2d_array(state_dict["block2.fc1.weight"], "block2_fc1_weights")
    b2_fc1_b = format_1d_array(state_dict["block2.fc1.bias"], "block2_fc1_biases")
    b2_ln1_w = format_1d_array(state_dict["block2.ln1.weight"], "block2_ln1_gamma")
    b2_ln1_b = format_1d_array(state_dict["block2.ln1.bias"], "block2_ln1_beta")
    b2_fc2_w = format_2d_array(state_dict["block2.fc2.weight"], "block2_fc2_weights")
    b2_fc2_b = format_1d_array(state_dict["block2.fc2.bias"], "block2_fc2_biases")
    b2_ln2_w = format_1d_array(state_dict["block2.ln2.weight"], "block2_ln2_gamma")
    b2_ln2_b = format_1d_array(state_dict["block2.ln2.bias"], "block2_ln2_beta")

    b3_fc1_w = format_2d_array(state_dict["block3.fc1.weight"], "block3_fc1_weights")
    b3_fc1_b = format_1d_array(state_dict["block3.fc1.bias"], "block3_fc1_biases")
    b3_ln1_w = format_1d_array(state_dict["block3.ln1.weight"], "block3_ln1_gamma")
    b3_ln1_b = format_1d_array(state_dict["block3.ln1.bias"], "block3_ln1_beta")
    b3_fc2_w = format_2d_array(state_dict["block3.fc2.weight"], "block3_fc2_weights")
    b3_fc2_b = format_1d_array(state_dict["block3.fc2.bias"], "block3_fc2_biases")
    b3_ln2_w = format_1d_array(state_dict["block3.ln2.weight"], "block3_ln2_gamma")
    b3_ln2_b = format_1d_array(state_dict["block3.ln2.bias"], "block3_ln2_beta")

    arc_w = format_2d_array(state_dict["arc_head.weight"], "arc_head_weights")

    weights_header = f"""#pragma once

// Automated weights export for Nite DSP SLO AcousticClassifier V5.
// Deep Residual MLP trained on multi-vendor real audio corpus (15 vendors, 5,157 samples).
// DO NOT EDIT MANUALLY.

namespace AcousticWeights
{{
    constexpr int modelVersion = 4;
    constexpr int embeddingVersion = 1;
    constexpr int taxonomyVersion = 1;
    constexpr int numClasses = {num_classes};
    constexpr int embeddingDim = 520;
    constexpr int hiddenDim = 512;
    constexpr float scaleFactor = 30.0f;

    inline const char* const classNames[numClasses] = {{ {class_names_str} }};

{fc1_w}
{fc1_b}
{ln1_w}
{ln1_b}

{b1_fc1_w}
{b1_fc1_b}
{b1_ln1_w}
{b1_ln1_b}
{b1_fc2_w}
{b1_fc2_b}
{b1_ln2_w}
{b1_ln2_b}

{b2_fc1_w}
{b2_fc1_b}
{b2_ln1_w}
{b2_ln1_b}
{b2_fc2_w}
{b2_fc2_b}
{b2_ln2_w}
{b2_ln2_b}

{b3_fc1_w}
{b3_fc1_b}
{b3_ln1_w}
{b3_ln1_b}
{b3_fc2_w}
{b3_fc2_b}
{b3_ln2_w}
{b3_ln2_b}

{arc_w}
}}
"""

    with open(weights_out_h, "w") as f:
        f.write(weights_header)
    print(f"Exported weights header to {weights_out_h}")

    # Centroids
    centroids = ckpt.get("centroids")
    per_class_thresholds = ckpt.get("per_class_thresholds")
    if centroids is not None and per_class_thresholds is not None:
        centroids_lines = []
        for c in range(num_classes):
            row_str = ", ".join(f"{centroids[c, d]:.8f}f" for d in range(embed_dim))
            centroids_lines.append(f"        {{ {row_str} }}")
        centroids_block = ",\n".join(centroids_lines)
        thresh_str = ", ".join(f"{per_class_thresholds[c]:.8f}f" for c in range(num_classes))

        centroids_header = f"""#pragma once

// Multi-vendor calibrated OOD centroids for SLO AcousticClassifier V5.
// DO NOT EDIT MANUALLY.

namespace AcousticOodCentroids
{{
    static constexpr int numClasses = {num_classes};
    static constexpr int embeddingDim = {embed_dim};

    inline const char* const classNames[numClasses] = {{
        {class_names_str}
    }};

    static constexpr float oodCosineSimilarityThreshold = 0.75000000f;

    inline constexpr float perClassOodThreshold[numClasses] = {{
        {thresh_str}
    }};

    inline constexpr float centroids[numClasses][embeddingDim] = {{
{centroids_block}
    }};
}}
"""
        with open(centroids_out_h, "w") as f:
            f.write(centroids_header)
        print(f"Exported centroids header to {centroids_out_h}")

    # Generate Parity References
    if dataset_npz and os.path.exists(dataset_npz):
        from test_sim import forward_cpp_sim
        data = np.load(dataset_npz)
        embeddings = data["embeddings"]
        filenames = data.get("filenames", [f"sample_{i}.wav" for i in range(len(embeddings))])
        
        # Pick 50 diverse samples across classes
        parity_cases = []
        num_cases = min(50, len(embeddings))
        step = len(embeddings) // num_cases
        
        for idx in range(0, len(embeddings), step):
            if len(parity_cases) >= num_cases:
                break
            x_th = torch.tensor(embeddings[idx], dtype=torch.float32).unsqueeze(0)
            logits_th = forward_cpp_sim(x_th, state_dict).squeeze(0) # [16]
            probs_th = torch.softmax(logits_th, dim=-1)
            pred_idx = logits_th.argmax().item()
            pred_sub = classes[pred_idx]
            
            parity_cases.append({
                "filename": str(filenames[idx]),
                "embedding": [float(v) for v in embeddings[idx]],
                "expected_logits": [float(v) for v in logits_th.numpy()],
                "expected_probs": [float(v) for v in probs_th.numpy()],
                "predicted_subcategory": pred_sub
            })
            
        with open(parity_out_json, "w") as f:
            json.dump(parity_cases, f, indent=4)
        print(f"Exported {len(parity_cases)} parity reference cases to {parity_out_json}")

if __name__ == "__main__":
    if len(sys.argv) < 5:
        print("Usage: export_to_cpp_headers.py <checkpoint.pt> <weights_out.h> <centroids_out.h> <parity_out.json> [dataset.npz]")
        sys.exit(1)
    dataset = sys.argv[5] if len(sys.argv) > 5 else None
    export_mlp(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], dataset)
