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

from nvflare.tool.agent_skill_checks.lints import run_v1_lints


def test_process_metric_lint_requires_process_metrics(tmp_path):
    _write_skill(
        tmp_path,
        "nvflare-test-skill",
        {
            "skill_name": "nvflare-test-skill",
            "evals": [
                {
                    "id": "test-positive",
                    "prompt": "Use this test skill.",
                    "expected_output": "The skill runs.",
                    "files": [],
                    "assertions": ["The skill runs."],
                    "nvflare": {
                        "expected_skill": "nvflare-test-skill",
                        "mandatory_behavior": [{"id": "run-test", "description": "runs the test workflow"}],
                    },
                }
            ],
        },
    )

    result = run_v1_lints(tmp_path, checks=["skill-process-metric-lint"])

    assert result["status"] == "failed"
    assert result["findings"][0]["code"] == "skill-process-metric-missing"


def test_process_metric_lint_accepts_process_metrics(tmp_path):
    _write_skill(
        tmp_path,
        "nvflare-test-skill",
        {
            "skill_name": "nvflare-test-skill",
            "evals": [
                {
                    "id": "test-positive",
                    "prompt": "Use this test skill.",
                    "expected_output": "The skill runs.",
                    "files": [],
                    "assertions": ["The skill runs."],
                    "nvflare": {
                        "expected_skill": "nvflare-test-skill",
                        "mandatory_behavior": [{"id": "run-test", "description": "runs the test workflow"}],
                        "process_metrics": [
                            {
                                "id": "turns_to_acceptable",
                                "description": "number of turns before the result is acceptable",
                            }
                        ],
                    },
                }
            ],
        },
    )

    result = run_v1_lints(tmp_path, checks=["skill-process-metric-lint"])

    assert result["status"] == "ok"
    assert result["findings"] == []


def _write_skill(root, name, evals):
    skill_dir = root / name
    skill_dir.mkdir(parents=True)
    skill_dir.joinpath("SKILL.md").write_text(
        "---\n"
        f"name: {name}\n"
        "description: Test skill fixture.\n"
        'min_flare_version: "2.8.0"\n'
        "blast_radius: read_only\n"
        "---\n"
        "\n"
        "# Test Skill\n"
        "\n"
        "## Use When\n"
        "\n"
        "Use when testing skill process metrics.\n",
        encoding="utf-8",
    )
    evals_dir = skill_dir / "evals"
    evals_dir.mkdir()
    evals_dir.joinpath("evals.json").write_text(json.dumps(evals), encoding="utf-8")
    return skill_dir
