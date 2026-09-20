import os
import sys
import numpy as np
import torch

def export_v4_centroids(checkpoint_path, centroids_header_path):
    print(f"Loading V4 checkpoint for centroids: {checkpoint_path}")
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    
    classes = [str(c) for c in checkpoint["classes"]]
    centroids = checkpoint["centroids"]  # numpy array (16, 512)
    per_class_th = checkpoint["per_class_thresholds"] # numpy array (16,)
    
    with open(centroids_header_path, "w") as f:
        f.write("#pragma once\n\n")
        f.write("// Multi-vendor calibrated OOD centroids & thresholds for SLO AcousticClassifier V4.\n")
        f.write("// DO NOT EDIT MANUALLY.\n\n")
        f.write("namespace AcousticOodCentroids\n{\n")
        f.write(f"    constexpr int numClasses = {len(classes)};\n")
        f.write("    constexpr int embeddingDim = 512;\n\n")
        
        class_str = ", ".join([f'"{c}"' for c in classes])
        f.write(f"    inline const char* const classNames[numClasses] = {{ {class_str} }};\n\n")
        
        f.write("    inline constexpr float centroids[numClasses][embeddingDim] = {\n")
        for idx in range(len(classes)):
            c_vec = centroids[idx]
            norm = np.linalg.norm(c_vec)
            if norm > 1e-6:
                c_vec = c_vec / norm
            vec_str = ", ".join([f"{val:.8f}f" for val in c_vec])
            f.write(f"        {{ {vec_str} }},\n")
        f.write("    };\n\n")

        f.write("    inline constexpr float perClassOodThreshold[numClasses] = {\n")
        th_strs = [f"{float(th):.4f}f" for th in per_class_th]
        f.write("        " + ", ".join(th_strs) + "\n")
        f.write("    };\n")
        f.write("}\n")

    print(f"Successfully exported V4 centroids to {centroids_header_path}")

if __name__ == "__main__":
    ckpt = "/Volumes/Jack_Gandy_1TB_SSD/NITE_DSP/products/slo/SmartSampleManager/tools/classification_benchmark/slo_classifier_v4_hybrid.pt"
    out_centroids = "/Volumes/Jack_Gandy_1TB_SSD/NITE_DSP/products/slo/SmartSampleManager/Source/AcousticClassifierCentroids.h"
    export_v4_centroids(ckpt, out_centroids)
