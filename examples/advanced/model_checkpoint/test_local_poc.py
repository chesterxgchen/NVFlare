#!/usr/bin/env python3
"""
Simple local POC test without Docker.
Tests dict model config and checkpoint loading in a basic PocEnv.

This is a simpler test to verify the core functionality works before
adding Docker complexity.
"""

import argparse
import os
import sys

from model import SimpleNetwork

from nvflare.app_opt.pt.recipes.fedavg import FedAvgRecipe
from nvflare.recipe import PocEnv, add_experiment_tracking


def generate_checkpoint(checkpoint_path: str):
    """Generate a simple checkpoint file."""
    import torch
    
    print(f"Generating checkpoint at: {checkpoint_path}")
    model = SimpleNetwork()
    torch.save(model.state_dict(), checkpoint_path)
    print(f"✓ Checkpoint generated: {checkpoint_path}")


def main():
    parser = argparse.ArgumentParser(description="Local POC test for dict config + checkpoint")
    parser.add_argument("--n_clients", type=int, default=2, help="Number of clients")
    parser.add_argument("--num_rounds", type=int, default=2, help="Number of rounds")
    parser.add_argument("--use_dict_config", action="store_true", help="Use dict model config")
    parser.add_argument("--checkpoint", type=str, default="", help="Path to checkpoint file")
    
    args = parser.parse_args()
    
    print("=" * 80)
    print("Local POC Test (No Docker)")
    print("=" * 80)
    print(f"Clients: {args.n_clients}")
    print(f"Rounds: {args.num_rounds}")
    print(f"Dict config: {args.use_dict_config}")
    print(f"Checkpoint: {args.checkpoint if args.checkpoint else 'None'}")
    print()
    
    # Generate checkpoint if path provided and file doesn't exist
    if args.checkpoint and not os.path.exists(args.checkpoint):
        generate_checkpoint(args.checkpoint)
        print()
    
    # Choose model configuration
    if args.use_dict_config:
        print("Using dict model config: {'path': 'model.SimpleNetwork'}")
        initial_model = {"path": "model.SimpleNetwork"}
    else:
        print("Using model instance: SimpleNetwork()")
        initial_model = SimpleNetwork()
    
    print()
    
    # Create recipe
    recipe = FedAvgRecipe(
        name="hello-pt-local-test",
        min_clients=args.n_clients,
        num_rounds=args.num_rounds,
        initial_model=initial_model,
        initial_ckpt=args.checkpoint if args.checkpoint else None,
        train_script="client.py",
        train_args="--batch_size 16",
    )
    add_experiment_tracking(recipe, tracking_type="tensorboard")
    
    # Run in local POC environment (no Docker)
    print("=" * 80)
    print("Starting Local POC Environment...")
    print("=" * 80)
    print()
    
    env = PocEnv(num_clients=args.n_clients)
    
    try:
        run = recipe.execute(env)
        
        print()
        print("=" * 80)
        print("Test Completed")
        print("=" * 80)
        print(f"Job Status: {run.get_status()}")
        print(f"Results: {run.get_result()}")
        print()
        
        # Check if successful
        status = run.get_status()
        if "FINISHED" in status and "EXCEPTION" not in status:
            print("✓ Test PASSED")
            return 0
        else:
            print("✗ Test FAILED")
            print(f"  Status: {status}")
            return 1
            
    except Exception as e:
        print()
        print("=" * 80)
        print("✗ Test FAILED with Exception")
        print("=" * 80)
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
