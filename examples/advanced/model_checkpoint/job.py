#!/usr/bin/env python3
"""
Test job.py that uses:
1. Dict model config instead of model instance
2. initial_ckpt parameter to load pre-trained weights

This tests the new recipe interface changes.
"""

import argparse

from model import SimpleNetwork

from nvflare.app_opt.pt.recipes.fedavg import FedAvgRecipe
from nvflare.recipe import add_experiment_tracking
from nvflare.recipe.utils import add_cross_site_evaluation


def define_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n_clients", type=int, default=2)
    parser.add_argument("--num_rounds", type=int, default=2)
    parser.add_argument("--batch_size", type=int, default=16)
    parser.add_argument("--train_script", type=str, default="client.py")
    parser.add_argument("--checkpoint", type=str, default="", 
                       help="Path to pre-trained checkpoint (use /workspace/pretrained_model.pt for Docker)")
    parser.add_argument("--cross_site_eval", action="store_true")
    parser.add_argument("--use_dict_config", action="store_true", 
                       help="Use dict model config instead of model instance")

    return parser.parse_args()


def main():
    args = define_parser()

    n_clients = args.n_clients
    num_rounds = args.num_rounds
    batch_size = args.batch_size

    # Choose model configuration based on flag
    if args.use_dict_config:
        print("=" * 80)
        print("Exporting Job with Dict Model Config")
        print("=" * 80)
        print(f"Model config: {{'path': 'model.SimpleNetwork'}}")
        if args.checkpoint:
            print(f"Checkpoint: {args.checkpoint}")
        print(f"Clients: {n_clients}")
        print(f"Rounds: {num_rounds}")
        print()
        
        initial_model = {
            "path": "model.SimpleNetwork",
            # "args": {}  # SimpleNetwork takes no args, so this is optional
        }
    else:
        print("=" * 80)
        print("Exporting Job with Model Instance")
        print("=" * 80)
        print(f"Model: SimpleNetwork()")
        if args.checkpoint:
            print(f"Checkpoint: {args.checkpoint}")
        print(f"Clients: {n_clients}")
        print(f"Rounds: {num_rounds}")
        print()
        
        from model import SimpleNetwork
        initial_model = SimpleNetwork()

    recipe = FedAvgRecipe(
        name="hello-pt-checkpoint-test",
        min_clients=n_clients,
        num_rounds=num_rounds,
        initial_model=initial_model,
        initial_ckpt=args.checkpoint if args.checkpoint else None,
        train_script=args.train_script,
        train_args=f"--batch_size {batch_size}",
    )
    add_experiment_tracking(recipe, tracking_type="tensorboard")

    if args.cross_site_eval:
        add_cross_site_evaluation(recipe)

    # Export job for external submission
    # Note: We use recipe.export() instead of recipe.execute(PocEnv()) because:
    # - PocEnv with docker_image runs ALL participants in Docker
    # - We want server-only Docker, so we manually start services and submit the exported job
    recipe.export(job_dir="/tmp/nvflare_job")
    
    job_dir = f"/tmp/nvflare_job/{recipe.name}"
    print("=" * 80)
    print(f"✓ Job Configuration Exported")
    print("=" * 80)
    print(f"Location: {job_dir}")
    print()
    print("Next steps:")
    print(f"  1. Start FL services (server + clients)")
    print(f"  2. Submit job: python submit_and_monitor.py -j {job_dir}")
    print(f"     or use CLI: nvflare job submit -j {job_dir}")
    print("=" * 80)
    print()


if __name__ == "__main__":
    main()
