# Copyright (c) 2026, NVIDIA CORPORATION.  All rights reserved.
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

import importlib.util
import os
import shlex
import sys
from types import SimpleNamespace

import pytest

HAS_PT = importlib.util.find_spec("torch") is not None
pytestmark = pytest.mark.skipif(not HAS_PT, reason="PyTorch is not installed")


def _load_job_module():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    example_dir = os.path.join(repo_root, "examples", "hello-world", "hello-pt")
    module_path = os.path.join(example_dir, "job.py")
    spec = importlib.util.spec_from_file_location("hello_pt_job", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None

    original_model_module = sys.modules.pop("model", None)
    sys.path.insert(0, example_dir)
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
        if original_model_module is not None:
            sys.modules["model"] = original_model_module
        else:
            sys.modules.pop("model", None)
    return module


def test_zero_flag_defaults_are_portable_and_bounded():
    job_module = _load_job_module()

    args = job_module.define_parser().parse_args([])

    assert vars(args) == {
        "batch_size": 32,
        "client_memory_gc_rounds": 0,
        "cross_site_eval": False,
        "dataset": "synthetic",
        "enable_log_streaming": False,
        "epochs": 1,
        "experiment_tracking": "none",
        "launch_external_process": False,
        "learning_rate": None,
        "n_clients": 2,
        "num_rounds": 2,
        "num_workers": 0,
        "test_size": 100,
        "train_script": "client.py",
        "train_size": 200,
    }


def test_legacy_synthetic_flag_keeps_selecting_the_default_dataset():
    job_module = _load_job_module()

    args = job_module.define_parser().parse_args(["--synthetic_data"])

    assert args.dataset == "synthetic"


def test_default_recipe_uses_final_global_evaluation_without_tracking(monkeypatch):
    job_module = _load_job_module()
    calls = []
    recipe = SimpleNamespace(enable_log_streaming=lambda: calls.append("log_streaming"))
    recipe_kwargs = {}

    def make_recipe(**kwargs):
        recipe_kwargs.update(kwargs)
        return recipe

    monkeypatch.setattr(job_module, "FedAvgRecipe", make_recipe)
    monkeypatch.setattr(job_module, "create_model", lambda: "model")
    monkeypatch.setattr(job_module, "add_final_global_evaluation", lambda value: calls.append(("final", value)))
    monkeypatch.setattr(job_module, "add_cross_site_evaluation", lambda value: calls.append(("cross", value)))
    monkeypatch.setattr(
        job_module,
        "add_experiment_tracking",
        lambda value, tracking_type: calls.append(("tracking", value, tracking_type)),
    )

    result = job_module.create_recipe(job_module.define_parser().parse_args([]))

    assert result is recipe
    assert recipe_kwargs["model"] == "model"
    assert recipe_kwargs["min_clients"] == 2
    assert recipe_kwargs["num_rounds"] == 2
    assert shlex.split(recipe_kwargs["train_args"]) == [
        "--batch_size",
        "32",
        "--epochs",
        "1",
        "--learning_rate",
        "0.1",
        "--num_workers",
        "0",
        "--dataset",
        "synthetic",
        "--train_size",
        "200",
        "--test_size",
        "100",
    ]
    assert calls == [("final", recipe)]


def test_cifar_and_tracking_remain_explicit_options(monkeypatch):
    job_module = _load_job_module()
    calls = []
    recipe = SimpleNamespace(enable_log_streaming=lambda: calls.append("log_streaming"))
    recipe_kwargs = {}

    def make_recipe(**kwargs):
        recipe_kwargs.update(kwargs)
        return recipe

    monkeypatch.setattr(job_module, "FedAvgRecipe", make_recipe)
    monkeypatch.setattr(job_module, "create_model", lambda: "model")
    monkeypatch.setattr(job_module, "add_final_global_evaluation", lambda value: calls.append(("final", value)))
    monkeypatch.setattr(job_module, "add_cross_site_evaluation", lambda value: calls.append(("cross", value)))
    monkeypatch.setattr(
        job_module,
        "add_experiment_tracking",
        lambda value, tracking_type: calls.append(("tracking", value, tracking_type)),
    )
    args = job_module.define_parser().parse_args(
        ["--dataset", "cifar10", "--experiment_tracking", "tensorboard", "--cross_site_eval"]
    )

    job_module.create_recipe(args)

    train_args = shlex.split(recipe_kwargs["train_args"])
    assert train_args == [
        "--batch_size",
        "32",
        "--epochs",
        "1",
        "--learning_rate",
        "0.01",
        "--num_workers",
        "0",
        "--dataset",
        "cifar10",
        "--track_metrics",
    ]
    assert calls == [("tracking", recipe, "tensorboard"), ("cross", recipe)]
