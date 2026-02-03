#!/usr/bin/env python3
"""
Simple local POC test without Docker.
Tests dict model config and checkpoint loading in a basic PocEnv.

This is a simpler test to verify the core functionality works before
adding Docker complexity.

IMPORTANT: This test uses a separate workspace to avoid Docker contamination.
"""

import argparse
import os
import shutil
import subprocess
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
    
    # Get POC workspace location
    from nvflare.tool.poc.poc_commands import get_poc_workspace
    poc_workspace = get_poc_workspace()
    
    print("Checking for running Docker containers...")
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", "name=flserver", "--filter", "name=site-", "-q"],
            capture_output=True, text=True, timeout=5
        )
        if result.stdout.strip():
            print("⚠ Found running Docker containers from previous tests. Stopping them...")
            subprocess.run(["docker", "rm", "-f", "flserver", "site-1", "site-2"], 
                          capture_output=True, timeout=10)
            print("✓ Docker containers stopped")
    except Exception as e:
        print(f"Warning: Could not check Docker: {e}")
    print()
    
    # Pre-download CIFAR10 dataset and generate checkpoint
    print("Preparing data (CIFAR10 + checkpoint)...")
    try:
        result = subprocess.run(["python", "prepare_data.py"], capture_output=True, text=True, timeout=120)
        if result.returncode == 0:
            print("✓ Data ready")
        else:
            print(f"Warning: Data preparation had issues: {result.stderr}")
    except Exception as e:
        print(f"Warning: Could not prepare data: {e}")
    print()
    
    # Clean up any existing POC workspace to avoid Docker contamination
    if os.path.exists(poc_workspace):
        print(f"Cleaning existing POC workspace: {poc_workspace}")
        shutil.rmtree(poc_workspace)
        print("✓ Workspace cleaned")
        print()
    
    print("=" * 80)
    print("Local POC Test (No Docker)")
    print("=" * 80)
    print(f"Workspace: {poc_workspace}")
    print(f"Clients: {args.n_clients}")
    print(f"Rounds: {args.num_rounds}")
    print(f"Dict config: {args.use_dict_config}")
    print(f"Checkpoint: {args.checkpoint if args.checkpoint else 'None'}")
    print()
    print("⚠ IMPORTANT: This test should NOT start Docker containers.")
    print("  If you see Docker starting, stop the test (Ctrl+C) and report the issue.")
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
    print("Starting Local POC Environment (processes only, no Docker)...")
    print("=" * 80)
    print()
    
    # Create PocEnv without docker_image (local processes only)
    env = PocEnv(num_clients=args.n_clients)
    
    try:
        run = recipe.execute(env)
        
        # Get status BEFORE cleanup (workspace must exist)
        status = run.get_status()
        result = run.get_result()
        
        print()
        print("=" * 80)
        print("Test Completed")
        print("=" * 80)
        print(f"Job Status: {status}")
        print(f"Results: {result}")
        print()
        
        # Check if successful (do this before cleanup)
        if "FINISHED:COMPLETED" in status:
            print("✓ Test PASSED")
            return_code = 0
        elif "FINISHED" in status and "EXCEPTION" not in status and "ERROR" not in status:
            print("✓ Test PASSED")
            return_code = 0
        else:
            print("✗ Test FAILED")
            print(f"  Status: {status}")
            return_code = 1
        
        return return_code
            
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
