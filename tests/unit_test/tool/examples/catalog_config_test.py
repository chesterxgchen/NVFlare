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

import json
from pathlib import Path

from nvflare.app_common.fdn.catalog.site.site_config import DatasetBinding, load_site_config


def test_checked_in_example_catalog_inputs_are_valid_and_minimal():
    root = Path(__file__).resolve().parents[4] / "examples/advanced/federated-catalog/config"
    paths = [path for site in ("site-1", "site-2") for path in (root / site).glob("catalog_site*.json")]
    assert len(paths) == 2
    for path in paths:
        raw = json.loads(path.read_text())
        assert set(raw) == (
            {"format_version", "default_connector", "studies"}
            if path.parent.name == "site-1"
            else {"format_version", "default_connector"}
        )
        site = load_site_config(path)
        assert site.default_connector in {"parquet", "sql"}


def test_example_sites_each_declare_their_own_reader():
    root = Path(__file__).resolve().parents[4] / "examples/advanced/federated-catalog/config"
    site = load_site_config(root / "site-1/catalog_site.json")
    assert site.default_connector == "parquet"
    assert site.bindings("default") == {"lab_results": DatasetBinding("csv"), "visits": DatasetBinding("csv")}
    assert load_site_config(root / "site-2/catalog_site.json").default_connector == "sql"


def test_example_publication_policies_are_separate_from_reader_configuration():
    from nvflare.app_common.fdn.catalog.site.policy import load_policy

    root = Path(__file__).resolve().parents[4] / "examples/advanced/federated-catalog/config"
    for site in ("site-1", "site-2"):
        policy = load_policy(root / site / "catalog_policy.json")
        assert policy.datasets["omop"].share
        assert set(policy.datasets) == ({"omop", "lab_results", "visits"} if site == "site-1" else {"omop"})
