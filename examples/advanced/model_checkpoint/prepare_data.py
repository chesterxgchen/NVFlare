#!/usr/bin/env python3
"""
Prepare data for model_checkpoint test:
1. Download CIFAR10 dataset (avoids race condition when multiple clients start)
2. Generate a pre-trained checkpoint file
"""

import sys
import torch
import torchvision
from torchvision.transforms import Compose, Normalize, ToTensor

# Add the hello-pt directory to the path
sys.path.insert(0, '../../hello-world/hello-pt')
from model import SimpleNetwork

DATASET_PATH = "/tmp/nvflare/data"


def download_cifar10():
    """Download CIFAR10 dataset to avoid race condition."""
    print("=" * 80)
    print("Downloading CIFAR10 Dataset")
    print("=" * 80)
    print(f"Dataset location: {DATASET_PATH}")
    print()
    
    # Download dataset
    transform = Compose([ToTensor(), Normalize((0.5, 0.5, 0.5), (0.5, 0.5, 0.5))])
    
    print("Downloading training set...")
    train_set = torchvision.datasets.CIFAR10(
        root=DATASET_PATH,
        train=True,
        download=True,
        transform=transform
    )
    print(f"✓ Training set: {len(train_set)} samples")
    
    print("Downloading test set...")
    test_set = torchvision.datasets.CIFAR10(
        root=DATASET_PATH,
        train=False,
        download=True,
        transform=transform
    )
    print(f"✓ Test set: {len(test_set)} samples")
    print()


def generate_checkpoint():
    """Generate a random pre-trained checkpoint."""
    checkpoint_path = "pretrained_model.pt"
    
    print("=" * 80)
    print("Generating Pre-trained Checkpoint")
    print("=" * 80)
    
    # Create model and initialize with random weights
    model = SimpleNetwork()
    
    # Save checkpoint
    torch.save(model.state_dict(), checkpoint_path)
    
    print(f"✓ Checkpoint saved to: {checkpoint_path}")
    print(f"  Model architecture: SimpleNetwork")
    print(f"  State dict keys: {list(model.state_dict().keys())}")
    print()
    
    # Verify it can be loaded
    model2 = SimpleNetwork()
    model2.load_state_dict(torch.load(checkpoint_path))
    print("✓ Checkpoint verified - can be loaded successfully")
    print()


if __name__ == "__main__":
    print()
    print("=" * 80)
    print("Preparing Data for Model Checkpoint Test")
    print("=" * 80)
    print()
    
    # Download CIFAR10 dataset
    download_cifar10()
    
    # Generate checkpoint
    generate_checkpoint()
    
    print("=" * 80)
    print("✓ Data Preparation Complete")
    print("=" * 80)
    print(f"CIFAR10: {DATASET_PATH}/cifar-10-batches-py/")
    print(f"Checkpoint: pretrained_model.pt")
    print()
