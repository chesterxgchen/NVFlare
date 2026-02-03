#!/usr/bin/env python3
"""
Generate a pre-trained checkpoint for testing initial_ckpt feature.
This creates a checkpoint with random weights for SimpleNetwork.
"""

import sys
import torch

# Add the hello-pt directory to the path
sys.path.insert(0, '../hello-world/hello-pt')

from model import SimpleNetwork


def main():
    print("Generating pre-trained checkpoint...")
    
    # Create model and initialize with random weights
    model = SimpleNetwork()
    
    # Optional: Train for a few iterations to make it more realistic
    # For now, just save the randomly initialized weights
    
    checkpoint_path = "pretrained_model.pt"
    torch.save(model.state_dict(), checkpoint_path)
    
    print(f"✓ Checkpoint saved to: {checkpoint_path}")
    print(f"  Model architecture: SimpleNetwork")
    print(f"  State dict keys: {list(model.state_dict().keys())}")
    print()
    
    # Verify it can be loaded
    model2 = SimpleNetwork()
    model2.load_state_dict(torch.load(checkpoint_path))
    print("✓ Checkpoint verified - can be loaded successfully")


if __name__ == "__main__":
    main()
