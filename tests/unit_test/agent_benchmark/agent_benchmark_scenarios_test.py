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

import hashlib
import json
from pathlib import Path

import yaml


def write_prompt_and_job(tmp_path: Path) -> tuple[Path, Path]:
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("Convert this job with the workflow named in the benchmark prompt.\n", encoding="utf-8")
    job = tmp_path / "ames"
    job.mkdir()
    job.joinpath("README.md").write_text("Synthetic job fixture.\n", encoding="utf-8")
    return prompt, job


def base_scenario(tmp_path: Path) -> dict:
    prompt, job = write_prompt_and_job(tmp_path)
    return {
        "name": "ci smoke scaffold",
        "prompt": prompt.name,
        "agents": [{"name": "codex", "models": ["gpt-test"]}],
        "comparison": {"type": "mode_ablation", "modes": ["without_skills", "with_skills"]},
        "workflows": [{"name": "SCAFFOLD"}],
        "jobs": [{"path": job.name, "scale": "small"}],
        "repeat_count": 2,
    }


def test_mode_ablation_expands_repeats_modes_and_target_record_paths(tmp_path):
    from harness.scenarios import compile_scenario

    raw = base_scenario(tmp_path)
    compilation = compile_scenario(raw, base_dir=tmp_path)
    scenario = compilation.scenario
    run_plan = compilation.run_plan
    entries = run_plan["entries"]

    expected_prompt_hash = hashlib.sha256((tmp_path / "prompt.txt").read_bytes()).hexdigest()
    assert scenario["name"] == "ci smoke scaffold"
    assert scenario["prompt"]["sha256"] == expected_prompt_hash
    assert run_plan["run_count"] == 4
    assert run_plan["comparison_group_count"] == 2
    assert [entry["mode"] for entry in entries] == [
        "without_skills",
        "with_skills",
        "without_skills",
        "with_skills",
    ]
    assert {entry["prompt_hash"] for entry in entries} == {expected_prompt_hash}
    assert entries[0]["record_dir"] == (
        "records/agent=codex/model=gpt_test/workflow=scaffold/job=ames/" "repeat=01/mode=without_skills/attempt=01"
    )
    assert entries[1]["skills_enabled"] is True
    assert entries[2]["repeat_index"] == 2
    assert run_plan["comparison_groups"][0]["compared_run_ids"] == ["run_00001", "run_00002"]


def test_compile_scenario_file_writes_scenario_and_run_plan(tmp_path):
    from harness.scenarios import compile_scenario_file

    raw = base_scenario(tmp_path)
    scenario_path = tmp_path / "scenario.yaml"
    scenario_path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    output_dir = tmp_path / "compiled"

    compilation = compile_scenario_file(scenario_path)
    compilation.write(output_dir)

    scenario_json = json.loads((output_dir / "scenario.json").read_text(encoding="utf-8"))
    run_plan_json = json.loads((output_dir / "run_plan.json").read_text(encoding="utf-8"))
    assert scenario_json["source_path"] == str(scenario_path.resolve())
    assert run_plan_json["source_path"] == str(scenario_path.resolve())
    assert run_plan_json["run_count"] == 4


def test_model_comparison_expands_comparison_models(tmp_path):
    from harness.scenarios import compile_scenario

    raw = base_scenario(tmp_path)
    raw["agents"] = [{"name": "codex"}]
    raw["comparison"] = {
        "type": "model_comparison",
        "agent": "codex",
        "mode": "with_skills",
        "models": ["gpt-a", "gpt-b"],
    }
    raw["repeat_count"] = 1

    run_plan = compile_scenario(raw, base_dir=tmp_path).run_plan

    assert run_plan["run_count"] == 2
    assert run_plan["comparison_group_count"] == 1
    assert [entry["agent_model"] for entry in run_plan["entries"]] == ["gpt-a", "gpt-b"]
    assert [entry["model_source"] for entry in run_plan["entries"]] == ["comparison", "comparison"]
    assert "model=gpt_a" in run_plan["entries"][0]["record_dir"]
    assert "model=gpt_b" in run_plan["entries"][1]["record_dir"]


def test_missing_job_scale_is_rejected(tmp_path):
    from harness.scenarios import ScenarioValidationError, compile_scenario

    raw = base_scenario(tmp_path)
    raw["jobs"][0].pop("scale")

    try:
        compile_scenario(raw, base_dir=tmp_path)
    except ScenarioValidationError as exc:
        assert "jobs[0].scale" in str(exc)
    else:
        raise AssertionError("scenario validation must require explicit job scale")


def test_known_pending_agent_is_rejected(tmp_path):
    from harness.scenarios import ScenarioValidationError, compile_scenario

    raw = base_scenario(tmp_path)
    raw["agents"] = [{"name": "hermes"}]

    try:
        compile_scenario(raw, base_dir=tmp_path)
    except ScenarioValidationError as exc:
        assert "BENCHMARK_AGENT='hermes'" in str(exc)
        assert "known but not implemented" in str(exc)
    else:
        raise AssertionError("known-pending agents should fail preflight")


def test_claude_scenario_requires_explicit_model(tmp_path):
    from harness.scenarios import ScenarioValidationError, compile_scenario

    raw = base_scenario(tmp_path)
    raw["agents"] = [{"name": "claude"}]
    raw["comparison"] = {"type": "one", "mode": "with_skills"}

    try:
        compile_scenario(raw, base_dir=tmp_path)
    except ScenarioValidationError as exc:
        assert "requires an explicit benchmark model" in str(exc)
        assert "CLAUDE_MODEL" in str(exc)
    else:
        raise AssertionError("Claude scenarios must require an explicit model")


def test_agent_comparison_requires_unambiguous_model_selection(tmp_path):
    from harness.scenarios import ScenarioValidationError, compile_scenario

    raw = base_scenario(tmp_path)
    raw["agents"] = [{"name": "codex", "models": ["gpt-a", "gpt-b"]}]
    raw["comparison"] = {"type": "agent_comparison", "mode": "with_skills", "agents": ["codex"]}

    try:
        compile_scenario(raw, base_dir=tmp_path)
    except ScenarioValidationError as exc:
        assert "ambiguous" in str(exc)
        assert "models_by_agent" in str(exc)
    else:
        raise AssertionError("agent comparison must reject ambiguous model selection")


def test_agent_comparison_models_by_agent_resolves_single_model(tmp_path):
    from harness.scenarios import compile_scenario

    raw = base_scenario(tmp_path)
    raw["agents"] = [{"name": "codex", "models": ["gpt-a", "gpt-b"]}]
    raw["comparison"] = {
        "type": "agent_comparison",
        "mode": "with_skills",
        "agents": ["codex"],
        "models_by_agent": {"codex": "gpt-b"},
    }
    raw["repeat_count"] = 1

    run_plan = compile_scenario(raw, base_dir=tmp_path).run_plan

    assert run_plan["run_count"] == 1
    assert run_plan["entries"][0]["agent_model"] == "gpt-b"
    assert run_plan["entries"][0]["model_source"] == "comparison.models_by_agent"
