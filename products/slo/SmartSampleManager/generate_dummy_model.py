import os
import torch
import torch.nn as nn

class DummyAudioEmbedder(nn.Module):
    def __init__(self):
        super().__init__()
        # Input size: 1 x 220500 (5 seconds at 44.1kHz)
        self.conv1 = nn.Conv1d(1, 16, kernel_size=15, stride=8, padding=7) # -> 16 x 27563
        self.conv2 = nn.Conv1d(16, 32, kernel_size=15, stride=8, padding=7) # -> 32 x 3446
        self.pool = nn.MaxPool1d(kernel_size=32, stride=32) # -> 32 x 107
        self.fc = nn.Linear(32 * 107, 512)
        
    def forward(self, x):
        # Input x shape: (batch_size, 220500)
        x = x.unsqueeze(1)
        x = torch.relu(self.conv1(x))
        x = torch.relu(self.conv2(x))
        x = self.pool(x)
        x = x.view(x.size(0), -1)
        x = self.fc(x)
        # Normalize embeddings to unit hypersphere
        x = torch.nn.functional.normalize(x, p=2, dim=1)
        return x

def main():
    model = DummyAudioEmbedder()
    model.eval()
    
    # 5 seconds of 44.1kHz audio = 220,500 samples
    dummy_input = torch.randn(1, 220500)
    
    output_dir = os.path.dirname(os.path.abspath(__file__))
    model_path = os.path.join(output_dir, "dummy_clap.onnx")
    
    print(f"Exporting dummy ONNX model to {model_path}...")
    torch.onnx.export(
        model,
        dummy_input,
        model_path,
        input_names=["input"],
        output_names=["output"],
        # Batch dimension must be dynamic so the engine can run batched inference
        # (multiple samples per Ort::Session::Run() call) instead of one at a time.
        dynamic_axes={"input": {0: "batch"}, "output": {0: "batch"}},
    )
    print("Export complete!")

if __name__ == "__main__":
    main()
