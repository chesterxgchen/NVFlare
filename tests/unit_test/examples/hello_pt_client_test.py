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
import sys
from collections import Counter

import pytest

HAS_PT = importlib.util.find_spec("torch") is not None
pytestmark = pytest.mark.skipif(not HAS_PT, reason="PyTorch is not installed")


def _load_hello_pt_module(file_name: str, module_name: str):
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    example_dir = os.path.join(repo_root, "examples", "hello-world", "hello-pt")
    module_path = os.path.join(example_dir, file_name)
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None

    original_modules = {name: sys.modules.pop(name, None) for name in ("model", "prepare_data")}
    sys.path.insert(0, example_dir)
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
        for name, original_module in original_modules.items():
            if original_module is not None:
                sys.modules[name] = original_module
            else:
                sys.modules.pop(name, None)
    return module


def test_hello_pt_evaluate_rejects_empty_data_loader():
    client_module = _load_hello_pt_module("client.py", "hello_pt_client")

    with pytest.raises(ValueError, match="Evaluation data_loader produced no samples"):
        client_module.evaluate(net=None, data_loader=[], device="cpu")


def test_synthetic_data_is_deterministic_and_disjoint_by_site_and_split():
    import torch

    data_module = _load_hello_pt_module("prepare_data.py", "hello_pt_prepare_data")
    dataset_type = data_module.SyntheticImageDataset

    train_1 = dataset_type(site_name="site-1", split="train", size=20)
    train_1_repeat = dataset_type(site_name="site-1", split="train", size=20)
    train_2 = dataset_type(site_name="site-2", split="train", size=20)
    eval_1 = dataset_type(site_name="site-1", split="eval", size=20)

    assert torch.equal(train_1.images, train_1_repeat.images)
    assert torch.equal(train_1.labels, train_1_repeat.labels)
    assert not torch.equal(train_1.images, train_2.images)
    assert not torch.equal(train_1.images, eval_1.images)

    id_sets = [set(dataset.sample_ids) for dataset in (train_1, train_2, eval_1)]
    assert all(left.isdisjoint(right) for index, left in enumerate(id_sets) for right in id_sets[index + 1 :])


def test_synthetic_data_is_balanced_and_encodes_the_label():
    data_module = _load_hello_pt_module("prepare_data.py", "hello_pt_prepare_signal")
    dataset = data_module.SyntheticImageDataset(site_name="site-1", split="train", size=100)

    assert Counter(dataset.labels.tolist()) == {label: 10 for label in range(data_module.NUM_CLASSES)}
    for image, label_tensor in dataset:
        label = label_tensor.item()
        row = 2 + (label // 5) * 16
        column = 1 + (label % 5) * 6
        assert image[:, row : row + 5, column : column + 5].mean().item() == pytest.approx(1.0)


def test_model_initialization_is_reproducible():
    import torch

    model_module = _load_hello_pt_module("model.py", "hello_pt_model")

    # Recipes reconstruct the serialized model class on the server, so direct
    # construction must be reproducible as well as the helper function.
    first = model_module.SimpleNetwork().state_dict()
    second = model_module.create_model().state_dict()

    assert first.keys() == second.keys()
    assert all(torch.equal(first[name], second[name]) for name in first)
