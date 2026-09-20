import os
import sys
import numpy as np
import torch

def export_v4_to_cpp(checkpoint_path, header_path):
    print(f"Loading V4 checkpoint from: {checkpoint_path}")
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    
    classes = [str(c) for c in checkpoint["classes"]]
    state_dict = checkpoint["state_dict"]
    
    print(f"Classes ({len(classes)}): {classes}")
    
    with open(header_path, "w") as f:
        f.write("#pragma once\n\n")
        f.write("// Automated weights export for Nite DSP SLO AcousticClassifier V4 (Hybrid 520D ArcFace Gated ResNet).\n")
        f.write("// Trained on all 33 sample packs (21,793 samples across 16 categories).\n")
        f.write("// DO NOT EDIT MANUALLY.\n\n")
        f.write("namespace AcousticWeights\n{\n")
        f.write("    constexpr int modelVersion = 4;\n")
        f.write("    constexpr int embeddingVersion = 1;\n")
        f.write("    constexpr int taxonomyVersion = 1;\n")
        f.write(f"    constexpr int numClasses = {len(classes)};\n")
        f.write("    constexpr int embeddingDim = 520;\n")
        f.write("    constexpr int hiddenDim = 512;\n")
        f.write("    constexpr float scaleFactor = 30.0f;\n\n")
        
        # classNames
        class_str = ", ".join([f'"{c}"' for c in classes])
        f.write(f"    inline const char* const classNames[numClasses] = {{ {class_str} }};\n\n")
        
        def write_matrix_2d(var_name, tensor):
            arr = tensor.numpy()
            shape = arr.shape
            f.write(f"    inline constexpr float {var_name}[{shape[0]}][{shape[1]}] = {{\n")
            for i in range(shape[0]):
                row_str = ", ".join([f"{val:.8f}f" for val in arr[i]])
                f.write(f"        {{ {row_str} }},\n")
            f.write("    };\n\n")

        def write_vector_1d(var_name, tensor):
            arr = tensor.numpy()
            f.write(f"    inline constexpr float {var_name}[{arr.shape[0]}] = {{\n")
            vec_str = ", ".join([f"{val:.8f}f" for val in arr])
            f.write(f"        {vec_str}\n")
            f.write("    };\n\n")

        # Layer 1: fc1 (512, 520) & ln1 (512,)
        write_matrix_2d("fc1_weights", state_dict["fc1.weight"])
        write_vector_1d("fc1_biases", state_dict["fc1.bias"])
        write_vector_1d("ln1_gamma", state_dict["ln1.weight"])
        write_vector_1d("ln1_beta", state_dict["ln1.bias"])
        
        # Blocks 1..3 (512, 512)
        for block_idx in range(1, 4):
            prefix = f"block{block_idx}"
            write_matrix_2d(f"{prefix}_fc1_weights", state_dict[f"{prefix}.fc1.weight"])
            write_vector_1d(f"{prefix}_fc1_biases", state_dict[f"{prefix}.fc1.bias"])
            write_vector_1d(f"{prefix}_ln1_gamma", state_dict[f"{prefix}.ln1.weight"])
            write_vector_1d(f"{prefix}_ln1_beta", state_dict[f"{prefix}.ln1.bias"])
            
            write_matrix_2d(f"{prefix}_fc2_weights", state_dict[f"{prefix}.fc2.weight"])
            write_vector_1d(f"{prefix}_fc2_biases", state_dict[f"{prefix}.fc2.bias"])
            write_vector_1d(f"{prefix}_ln2_gamma", state_dict[f"{prefix}.ln2.weight"])
            write_vector_1d(f"{prefix}_ln2_beta", state_dict[f"{prefix}.ln2.bias"])

        # Arc Head weights (16, 512)
        write_matrix_2d("arc_head_weights", state_dict["arc_head.weight"])
        
        f.write("}\n")

    print(f"Successfully exported V4 C++ header to {header_path}")

if __name__ == "__main__":
    ckpt = "/Volumes/Jack_Gandy_1TB_SSD/NITE_DSP/products/slo/SmartSampleManager/tools/classification_benchmark/slo_classifier_v4_hybrid.pt"
    out_header = "/Volumes/Jack_Gandy_1TB_SSD/NITE_DSP/products/slo/SmartSampleManager/Source/AcousticClassifierWeights.h"
    export_v4_to_cpp(ckpt, out_header)
