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
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

HAS_PT = importlib.util.find_spec("torch") is not None
pytestmark = pytest.mark.skipif(not HAS_PT, reason="PyTorch is not installed")
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
EXAMPLE_DIR = os.path.join(REPO_ROOT, "examples", "hello-world", "hello-pt")


@contextmanager
def _job_module_context():
    module_path = os.path.join(EXAMPLE_DIR, "job.py")
    spec = importlib.util.spec_from_file_location("hello_pt_job", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None

    original_model_module = sys.modules.pop("model", None)
    sys.path.insert(0, EXAMPLE_DIR)
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.path.pop(0)
        if original_model_module is not None:
            sys.modules["model"] = original_model_module
        else:
            sys.modules.pop("model", None)


def _load_job_module():
    with _job_module_context() as module:
        return module


def test_zero_flag_defaults_are_portable_and_bounded():
    job_module = _load_job_module()

    args = job_module.parse_args([])

    assert vars(args) == {
        "batch_size": 32,
        "client_memory_gc_rounds": 0,
        "cross_site_eval": False,
        "dataset": "synthetic",
        "enable_log_streaming": False,
        "env": "sim",
        "epochs": 1,
        "experiment_tracking": "none",
        "launch_external_process": False,
        "learning_rate": None,
        "n_clients": 2,
        "num_rounds": 2,
        "num_workers": 0,
        "startup_kit": None,
        "test_size": 100,
        "train_script": "client.py",
        "train_size": 200,
        "username": None,
    }


def test_legacy_synthetic_flag_keeps_selecting_the_default_dataset():
    job_module = _load_job_module()

    args = job_module.parse_args(["--synthetic_data"])

    assert args.dataset == "synthetic"


def test_environment_arguments_require_startup_kit_only_for_production(capsys):
    job_module = _load_job_module()

    with pytest.raises(SystemExit, match="2"):
        job_module.parse_args(["--env", "prod"])
    assert "--startup-kit is required with --env prod" in capsys.readouterr().err

    with pytest.raises(SystemExit, match="2"):
        job_module.parse_args(["--startup-kit", "/tmp/admin"])
    assert "--startup-kit can only be used with --env prod" in capsys.readouterr().err

    with pytest.raises(SystemExit, match="2"):
        job_module.parse_args(["--username", "researcher@example.com"])
    assert "--username can only be used with --env prod" in capsys.readouterr().err


def test_help_includes_recipe_export_options():
    job_module = _load_job_module()

    help_text = job_module.define_parser().format_help()

    assert "--export" in help_text
    assert "--export-dir EXPORT_DIR" in help_text


def test_environment_selection_uses_the_same_client_count(tmp_path):
    job_module = _load_job_module()

    sim_env = job_module.create_environment(job_module.parse_args(["--n_clients", "3"]))
    poc_env = job_module.create_environment(job_module.parse_args(["--env", "poc", "--n_clients", "3"]))

    startup_kit = tmp_path / "admin@nvidia.com"
    startup_kit.mkdir()
    prod_env = job_module.create_environment(
        job_module.parse_args(
            [
                "--env",
                "prod",
                "--startup-kit",
                str(startup_kit),
                "--username",
                "researcher@example.com",
                "--n_clients",
                "3",
            ]
        )
    )

    assert isinstance(sim_env, job_module.SimEnv)
    assert isinstance(poc_env, job_module.PocEnv)
    assert isinstance(prod_env, job_module.ProdEnv)
    assert sim_env.num_clients == poc_env.num_clients == 3
    assert prod_env.startup_kit_location == str(startup_kit)
    assert prod_env.username == "researcher@example.com"


def test_main_preserves_poc_result_and_reports_cached_status(tmp_path, monkeypatch, capsys):
    job_module = _load_job_module()
    result_dir = tmp_path / "poc-result"
    result_dir.mkdir()
    calls = []

    run = SimpleNamespace(
        get_result=lambda clean_up: calls.append(("get_result", clean_up)) or str(result_dir),
        get_status=lambda: calls.append(("get_status",)) or "FINISHED:COMPLETED",
    )
    env = object()
    recipe = SimpleNamespace(execute=lambda value: calls.append(("execute", value)) or run)
    monkeypatch.setattr(job_module, "create_recipe", lambda args: recipe)
    monkeypatch.setattr(job_module, "create_environment", lambda args: env)

    result = job_module.main(["--env", "poc"])

    assert result == str(result_dir)
    assert calls == [("execute", env), ("get_result", False), ("get_status",)]
    output = capsys.readouterr().out
    assert "Job Status is: FINISHED:COMPLETED" in output
    assert f"Result can be found in : {result_dir}" in output


def test_main_cleans_up_poc_if_deployment_fails(monkeypatch):
    job_module = _load_job_module()
    calls = []

    def fail_during_deployment(value):
        calls.append(("execute", value))
        raise RuntimeError("submission failed")

    env = SimpleNamespace(stop=lambda clean_up: calls.append(("stop", clean_up)))
    recipe = SimpleNamespace(execute=fail_during_deployment)
    monkeypatch.setattr(job_module, "create_recipe", lambda args: recipe)
    monkeypatch.setattr(job_module, "create_environment", lambda args: env)

    with pytest.raises(RuntimeError, match="submission failed"):
        job_module.main(["--env", "poc"])

    assert calls == [("execute", env), ("stop", True)]


def test_main_does_not_request_unsupported_simulation_status(tmp_path, monkeypatch, capsys):
    job_module = _load_job_module()
    result_dir = tmp_path / "simulation-result"
    result_dir.mkdir()
    calls = []

    def unsupported_status():
        raise AssertionError("SimEnv status must not be requested by the example")

    run = SimpleNamespace(
        get_result=lambda clean_up: calls.append(("get_result", clean_up)) or str(result_dir),
        get_status=unsupported_status,
    )
    env = object()
    recipe = SimpleNamespace(execute=lambda value: calls.append(("execute", value)) or run)
    monkeypatch.setattr(job_module, "create_recipe", lambda args: recipe)
    monkeypatch.setattr(job_module, "create_environment", lambda args: env)

    result = job_module.main([])

    assert result == str(result_dir)
    assert calls == [("execute", env), ("get_result", True)]
    output = capsys.readouterr().out
    assert "Simulation completed successfully." in output
    assert "Job Status is: None" not in output


def test_production_environment_exports_the_same_application(tmp_path, monkeypatch):
    with _job_module_context() as job_module:
        startup_kit = tmp_path / "admin@nvidia.com"
        startup_kit.mkdir()
        args = job_module.parse_args(["--env", "prod", "--startup-kit", str(startup_kit)])

        monkeypatch.chdir(EXAMPLE_DIR)
        recipe = job_module.create_recipe(args)
        env = job_module.create_environment(args)
        export_root = tmp_path / "job_config"
        recipe.export(job_dir=str(export_root), env=env)

    job_dir = tmp_path / "job_config" / "hello-pt"
    assert (job_dir / "meta.json").is_file()
    exported_python_files = {path.name for path in Path(job_dir).rglob("*.py")}
    assert {"client.py", "model.py", "prepare_data.py"} <= exported_python_files


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

    result = job_module.create_recipe(job_module.parse_args([]))

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
    args = job_module.parse_args(["--dataset", "cifar10", "--experiment_tracking", "tensorboard", "--cross_site_eval"])

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
