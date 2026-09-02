# Copyright (c) 2025-2026, NVIDIA CORPORATION.  All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Run the Hello PyTorch FedAvg job in simulation, POC, or production."""

import argparse
import shlex

from model import create_model

from nvflare.app_opt.pt.recipes.fedavg import FedAvgRecipe
from nvflare.recipe import PocEnv, ProdEnv, SimEnv, add_experiment_tracking, add_final_global_evaluation
from nvflare.recipe.utils import add_cross_site_evaluation

DEFAULT_BATCH_SIZE = 32
DEFAULT_CIFAR_LEARNING_RATE = 0.01
DEFAULT_EPOCHS = 1
DEFAULT_NUM_CLIENTS = 2
DEFAULT_NUM_ROUNDS = 2
DEFAULT_NUM_WORKERS = 0
DEFAULT_TEST_SIZE = 100
DEFAULT_TRAIN_SIZE = 200
DEFAULT_SYNTHETIC_LEARNING_RATE = 0.1
EXPORT_HELP = """NVFlare Recipe export options:
  --export                    Export the job instead of running it.
  --export-dir EXPORT_DIR     Parent directory for the exported job (default: ./fl_job).
"""


def define_parser() -> argparse.ArgumentParser:
    # Recipe consumes its system-level export flags before this parser runs, so
    # list them in the epilog to keep ``python job.py --help`` complete.
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=EXPORT_HELP,
    )
    parser.add_argument("--n_clients", type=int, default=DEFAULT_NUM_CLIENTS)
    parser.add_argument(
        "--env",
        choices=("sim", "poc", "prod"),
        default="sim",
        help="Execution environment: local simulation, local POC processes, or a provisioned production system.",
    )
    parser.add_argument(
        "--startup-kit",
        default=None,
        help="Path to an admin startup kit. Required with --env prod and unused for simulation or POC.",
    )
    parser.add_argument("--num_rounds", type=int, default=DEFAULT_NUM_ROUNDS)
    parser.add_argument("--batch_size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--epochs", type=int, default=DEFAULT_EPOCHS)
    parser.add_argument(
        "--learning_rate",
        type=float,
        default=None,
        help="Local learning rate. Defaults to 0.1 for synthetic data and 0.01 for CIFAR-10.",
    )
    parser.add_argument("--num_workers", type=int, default=DEFAULT_NUM_WORKERS)

    # Keep the zero-argument quickstart deterministic and offline. CIFAR-10 is
    # still available, but selecting it explicitly permits a dataset download.
    dataset_group = parser.add_mutually_exclusive_group()
    dataset_group.add_argument("--dataset", choices=("synthetic", "cifar10"), dest="dataset")
    dataset_group.add_argument(
        "--synthetic_data",
        action="store_const",
        const="synthetic",
        dest="dataset",
        help="Deprecated alias for --dataset synthetic.",
    )
    parser.set_defaults(dataset="synthetic")
    parser.add_argument("--train_size", type=int, default=DEFAULT_TRAIN_SIZE)
    parser.add_argument("--test_size", type=int, default=DEFAULT_TEST_SIZE)
    parser.add_argument("--train_script", type=str, default="client.py")
    parser.add_argument("--cross_site_eval", action="store_true")
    # Tracking is opt-in so the default run does not require TensorBoard.
    parser.add_argument(
        "--experiment_tracking",
        choices=("none", "tensorboard"),
        default="none",
        help="Optional experiment tracking backend. TensorBoard requires the tensorboard package.",
    )
    parser.add_argument("--enable_log_streaming", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument(
        "--launch_external_process",
        action="store_true",
        help="Run train_script in a separate subprocess instead of in-process.",
    )
    parser.add_argument(
        "--client_memory_gc_rounds",
        type=int,
        default=0,
        help="Release model params and run GC every N rounds to keep client RSS flat. 0 = disabled.",
    )

    return parser


def parse_args(argv=None):
    parser = define_parser()
    args = parser.parse_args(argv)
    if args.env == "prod" and not args.startup_kit:
        parser.error("--startup-kit is required with --env prod")
    if args.env != "prod" and args.startup_kit:
        parser.error("--startup-kit can only be used with --env prod")
    return args


def create_recipe(args):
    learning_rate = args.learning_rate
    if learning_rate is None:
        learning_rate = DEFAULT_SYNTHETIC_LEARNING_RATE if args.dataset == "synthetic" else DEFAULT_CIFAR_LEARNING_RATE
    train_args = [
        "--batch_size",
        str(args.batch_size),
        "--epochs",
        str(args.epochs),
        "--learning_rate",
        str(learning_rate),
        "--num_workers",
        str(args.num_workers),
        "--dataset",
        args.dataset,
    ]
    if args.dataset == "synthetic":
        train_args.extend(("--train_size", str(args.train_size), "--test_size", str(args.test_size)))
    if args.experiment_tracking != "none":
        train_args.append("--track_metrics")

    recipe = FedAvgRecipe(
        name="hello-pt",
        min_clients=args.n_clients,
        num_rounds=args.num_rounds,
        # Model can be specified as class instance or dict config:
        model=create_model(),
        # Alternative: model={"class_path": "model.SimpleNetwork", "args": {}},
        # For pre-trained weights: initial_ckpt="/server/path/to/pretrained.pt",
        train_script=args.train_script,
        train_args=shlex.join(train_args),
        launch_external_process=args.launch_external_process,
        client_memory_gc_rounds=args.client_memory_gc_rounds,
    )

    if args.experiment_tracking != "none":
        add_experiment_tracking(recipe, tracking_type=args.experiment_tracking)

    if args.cross_site_eval:
        # Full CSE also collects and evaluates each client's latest local model.
        add_cross_site_evaluation(recipe)
    else:
        # Always verify the persisted final global model in the basic quickstart.
        add_final_global_evaluation(recipe)

    if args.enable_log_streaming:
        recipe.enable_log_streaming()

    return recipe


def create_environment(args):
    """Construct the selected environment without changing the application recipe."""
    if args.env == "sim":
        return SimEnv(num_clients=args.n_clients)
    if args.env == "poc":
        return PocEnv(num_clients=args.n_clients)
    return ProdEnv(startup_kit_location=args.startup_kit)


def main(argv=None):
    args = parse_args(argv)
    recipe = create_recipe(args)
    env = create_environment(args)

    run = recipe.execute(env)
    # PocEnv downloads the result into its workspace. Retain that workspace so
    # the path printed below still exists after the POC services have stopped.
    result = run.get_result(clean_up=args.env != "poc")
    print()
    if args.env == "sim":
        # SimEnv runs synchronously but does not implement get_status(). A
        # normal return from execute/get_result means the simulation completed.
        print("Simulation completed successfully.")
    else:
        print("Job Status is:", run.get_status())
    print("Result can be found in :", result)
    print()
    return result


if __name__ == "__main__":
    main()
