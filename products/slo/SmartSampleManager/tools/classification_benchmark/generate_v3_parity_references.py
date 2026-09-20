import os
import sys
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import json

checkpoint_path = "/Volumes/Jack_Gandy_1TB_SSD/NITE_DSP/products/slo/SmartSampleManager/tools/classification_benchmark/slo_classifier_v3_all_packs.pt"
out_json_path = "/Volumes/Jack_Gandy_1TB_SSD/NITE_DSP/products/slo/SmartSampleManager/tools/classification_benchmark/parity_references.json"

checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
classes = [str(c) for c in checkpoint["classes"]]
state_dict = checkpoint["state_dict"]

class GatedResBlock(nn.Module):
    def __init__(self, dim):
        super().__init__()
        self.fc1 = nn.Linear(dim, dim)
        self.ln1 = nn.LayerNorm(dim)
        self.fc2 = nn.Linear(dim, dim)
        self.ln2 = nn.LayerNorm(dim)

    def forward(self, x):
        res = x
        h = F.gelu(self.ln1(self.fc1(x)))
        h = F.gelu(self.ln2(self.fc2(h)))
        return res + h

class ClassifierV3(nn.Module):
    def __init__(self, in_features=512, num_classes=16, hidden_dim=512):
        super().__init__()
        self.fc1 = nn.Linear(in_features, hidden_dim)
        self.ln1 = nn.LayerNorm(hidden_dim)
        self.block1 = GatedResBlock(hidden_dim)
        self.block2 = GatedResBlock(hidden_dim)
        self.block3 = GatedResBlock(hidden_dim)
        self.temperature = nn.Parameter(torch.ones(1))
        self.arc_head = nn.Linear(hidden_dim, num_classes, bias=False)

    def forward(self, x):
        h = F.gelu(self.ln1(self.fc1(x)))
        h = self.block1(h)
        h = self.block2(h)
        h = self.block3(h)
        w_norm = F.normalize(self.arc_head.weight, dim=1)
        x_norm = F.normalize(h, dim=1)
        logits = F.linear(x_norm, w_norm) * 30.0
        return logits

model = ClassifierV3(in_features=512, num_classes=len(classes))
model.load_state_dict(state_dict)
model.eval()

# Generate reference embeddings
np.random.seed(42)
num_samples = 10
references = []

for i in range(num_samples):
    emb = np.random.randn(512).astype(np.float32)
    emb = emb / np.linalg.norm(emb) # normalized 512D vector
    
    with torch.no_grad():
        t_emb = torch.tensor(emb).unsqueeze(0)
        logits = model(t_emb).squeeze().numpy()
        probs = F.softmax(torch.tensor(logits), dim=-1).numpy()
        pred_idx = int(np.argmax(probs))
        pred_class = classes[pred_idx]
        
    references.append({
        "filename": f"synthetic_sample_{i}.wav",
        "embedding": [float(x) for x in emb],
        "expected_logits": [float(x) for x in logits],
        "expected_probs": [float(x) for x in probs],
        "expected_subcategory": pred_class
    })

data = {
    "version": 3,
    "taxonomy_version": 1,
    "references": references
}

with open(out_json_path, "w") as f:
    json.dump(data, f, indent=2)

print(f"Generated {num_samples} parity references at {out_json_path}")
