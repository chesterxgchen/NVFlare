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
import json
import os
import sys
from contextlib import contextmanager

import pytest

from nvflare.recipe import SimEnv

HAS_PT = importlib.util.find_spec("torch") is not None
pytestmark = pytest.mark.skipif(not HAS_PT, reason="PyTorch is not installed")

INTEGRATION_TEST_ROOT = os.path.dirname(os.path.dirname(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(INTEGRATION_TEST_ROOT))
EXAMPLE_DIR = os.path.join(REPO_ROOT, "examples", "hello-world", "hello-pt")


@contextmanager
def _load_job_module():
    module_path = os.path.join(EXAMPLE_DIR, "job.py")
    spec = importlib.util.spec_from_file_location("hello_pt_quickstart_job", module_path)
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
    return module


def test_zero_flag_hello_pt_produces_learned_loadable_final_model(tmp_path, monkeypatch):
    import torch

    with _load_job_module() as job_module:
        monkeypatch.chdir(EXAMPLE_DIR)
        existing_pythonpath = os.environ.get("PYTHONPATH")
        source_pythonpath = REPO_ROOT if not existing_pythonpath else os.pathsep.join((REPO_ROOT, existing_pythonpath))
        monkeypatch.setenv("PYTHONPATH", source_pythonpath)
        recipe = job_module.create_recipe(job_module.define_parser().parse_args([]))
        env = SimEnv(num_clients=2, workspace_root=str(tmp_path / "simulation"))

        run = recipe.execute(env)
        result_path = run.get_result()

    server_run_dir = os.path.join(result_path, "server", "simulate_job")
    with open(os.path.join(server_run_dir, "metrics", "round_metrics.jsonl")) as metrics_file:
        first_round = json.loads(next(metrics_file))
    first_round_metrics = {metric["name"]: metric["value"] for metric in first_round["aggregated_metrics"]}
    initial_accuracy = first_round_metrics["accuracy"]

    with open(os.path.join(server_run_dir, "cross_site_val", "cross_val_results.json")) as results_file:
        final_results = json.load(results_file)
    final_accuracies = [site_results["SRV_FL_global_model.pt"]["accuracy"] for site_results in final_results.values()]

    assert set(final_results) == {"site-1", "site-2"}
    # These functional thresholds are calibrated to the quickstart's fixed
    # model/data seeds and three-round default, not to arbitrary initialization
    # or hyperparameters. The seeded run has margin above both boundaries.
    assert initial_accuracy <= 20.0
    assert min(final_accuracies) >= 60.0
    assert min(final_accuracies) >= initial_accuracy + 40.0

    artifact_path = os.path.join(server_run_dir, "app_server", "FL_global_model.pt")
    artifact = torch.load(artifact_path, map_location="cpu", weights_only=True)
    assert artifact["model"]
