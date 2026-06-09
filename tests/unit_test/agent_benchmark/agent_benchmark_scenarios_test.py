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
    job.mkdir(exist_ok=True)
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
        "records/agent=codex/model=gpt_test/workflow=scaffold/job=ames/" "repeat=01/mode=without_skills"
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


def test_prompt_path_must_stay_inside_scenario_directory(tmp_path):
    from harness.scenarios import ScenarioValidationError, compile_scenario

    base_dir = tmp_path / "scenario"
    base_dir.mkdir()
    raw = base_scenario(base_dir)
    outside_prompt = tmp_path / "outside_prompt.txt"
    outside_prompt.write_text("secret prompt\n", encoding="utf-8")
    raw["prompt"] = str(outside_prompt)

    try:
        compile_scenario(raw, base_dir=base_dir)
    except ScenarioValidationError as exc:
        assert "Prompt file must stay within scenario directory" in str(exc)
    else:
        raise AssertionError("absolute prompt paths outside the scenario directory should be rejected")


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


def test_model_comparison_dedupes_overlapping_top_level_models(tmp_path):
    from harness.scenarios import compile_scenario

    raw = base_scenario(tmp_path)
    raw["agents"] = [{"name": "codex", "models": ["gpt-a", "gpt-b"]}]
    raw["comparison"] = {
        "type": "model_comparison",
        "agent": "codex",
        "mode": "with_skills",
        "models": ["gpt-a", "gpt-b"],
    }
    raw["repeat_count"] = 1

    run_plan = compile_scenario(raw, base_dir=tmp_path).run_plan

    assert "model=gpt_a/" in run_plan["entries"][0]["record_dir"]
    assert "model=gpt_b/" in run_plan["entries"][1]["record_dir"]


def test_model_slug_fallback_avoids_unhandled_missing_key():
    from harness.scenarios import model_slug_for

    assert model_slug_for({"models": {}}, "codex", "gpt-test") == "gpt_test"


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


def test_fail_fast_requires_boolean(tmp_path):
    from harness.scenarios import ScenarioValidationError, compile_scenario

    raw = base_scenario(tmp_path)
    raw["fail_fast"] = "false"

    try:
        compile_scenario(raw, base_dir=tmp_path)
    except ScenarioValidationError as exc:
        assert "fail_fast must be a boolean" in str(exc)
    else:
        raise AssertionError("scenario validation must reject string fail_fast values")


def test_resource_policy_non_integer_values_are_validation_errors(tmp_path):
    from harness.scenarios import ScenarioValidationError, compile_scenario

    raw = base_scenario(tmp_path)
    raw["resource_policy"] = {"small": {"agent_timeout_seconds": "fast"}}

    try:
        compile_scenario(raw, base_dir=tmp_path)
    except ScenarioValidationError as exc:
        assert "resource_policy.small.agent_timeout_seconds" in str(exc)
        assert "must be an integer greater than 0" in str(exc)
    else:
        raise AssertionError("non-integer scenario resource policy values should fail validation")

    job_policy_case = tmp_path / "job-policy"
    job_policy_case.mkdir()
    raw = base_scenario(job_policy_case)
    raw["jobs"][0]["resource_policy"] = {"agent_timeout_seconds": None}

    try:
        compile_scenario(raw, base_dir=tmp_path)
    except ScenarioValidationError as exc:
        assert "jobs[0].resource_policy.agent_timeout_seconds" in str(exc)
        assert "must be an integer greater than 0" in str(exc)
    else:
        raise AssertionError("non-integer job resource policy values should fail validation")


def test_resource_policy_rejects_bool_and_non_positive_values(tmp_path):
    from harness.scenarios import ScenarioValidationError, compile_scenario

    raw = base_scenario(tmp_path)
    raw["resource_policy"] = {"small": {"agent_timeout_seconds": False}}

    try:
        compile_scenario(raw, base_dir=tmp_path)
    except ScenarioValidationError as exc:
        assert "resource_policy.small.agent_timeout_seconds" in str(exc)
        assert "must be an integer greater than 0" in str(exc)
    else:
        raise AssertionError("boolean resource policy values should fail validation")

    zero_case = tmp_path / "zero-policy"
    zero_case.mkdir()
    raw = base_scenario(zero_case)
    raw["jobs"][0]["resource_policy"] = {"container_timeout_seconds": 0}

    try:
        compile_scenario(raw, base_dir=zero_case)
    except ScenarioValidationError as exc:
        assert "jobs[0].resource_policy.container_timeout_seconds" in str(exc)
        assert "must be an integer greater than 0" in str(exc)
    else:
        raise AssertionError("zero resource policy values should fail validation")


def test_prompt_file_size_guard_rejects_large_prompt(tmp_path):
    from harness.scenarios import MAX_PROMPT_BYTES, ScenarioValidationError, compile_scenario

    raw = base_scenario(tmp_path)
    prompt_path = tmp_path / raw["prompt"]
    with prompt_path.open("wb") as stream:
        stream.truncate(MAX_PROMPT_BYTES + 1)

    try:
        compile_scenario(raw, base_dir=tmp_path)
    except ScenarioValidationError as exc:
        assert "Prompt file exceeds max size" in str(exc)
    else:
        raise AssertionError("scenario prompt files should be size-limited before read_bytes")


def test_prompt_file_size_guard_uses_read_bytes_length(tmp_path, monkeypatch):
    from harness.scenarios import MAX_PROMPT_BYTES, ScenarioValidationError, compile_scenario

    raw = base_scenario(tmp_path)
    prompt_path = tmp_path / raw["prompt"]
    original_read_bytes = Path.read_bytes

    def fake_read_bytes(path):
        if path == prompt_path:
            return b"x" * (MAX_PROMPT_BYTES + 1)
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", fake_read_bytes)

    try:
        compile_scenario(raw, base_dir=tmp_path)
    except ScenarioValidationError as exc:
        assert "Prompt file exceeds max size" in str(exc)
    else:
        raise AssertionError("scenario prompt files should be capped by bytes read, not a stale stat")


def test_validate_path_budget_uses_longest_path_not_lexicographic_max():
    from harness.scenarios import ScenarioValidationError, validate_path_budget

    short_late_path = "zz"
    long_early_path = "a" * 80
    budget = len(str(Path("results") / "path-budget" / short_late_path)) + 1

    try:
        validate_path_budget(
            "path budget",
            [{"artifact_paths": {"short": short_late_path, "long": long_early_path}}],
            budget,
        )
    except ScenarioValidationError as exc:
        assert long_early_path in str(exc)
        assert "path_budget" in str(exc)
    else:
        raise AssertionError("path budget validation must check the longest rendered artifact path")


def test_validate_path_budget_can_use_actual_result_root():
    from harness.scenarios import ScenarioValidationError, validate_path_budget

    result_root = Path("r" * 40)
    artifact_path = "short.txt"
    synthetic_budget = len(str(Path("results") / "path-budget" / artifact_path)) + 1

    try:
        validate_path_budget(
            "path budget",
            [{"artifact_paths": {"short": artifact_path}}],
            synthetic_budget,
            result_root=result_root,
        )
    except ScenarioValidationError as exc:
        assert str(result_root) in str(exc)
    else:
        raise AssertionError("path budget validation should include the actual result root when provided")


def test_quality_gate_failures_reports_missing_final_exit_as_not_recorded():
    from harness.scenarios import quality_gate_failures

    failures = quality_gate_failures(
        {"agent_process_passed": True, "source_input_immutable_policy": {"status": "pass"}},
        {},
        0,
    )

    assert "final_container_exit_code=not_recorded" in failures
    assert "final_container_exit_code=None" not in failures


def test_quality_gate_failures_derives_missing_required_validation_metric():
    from harness.scenarios import quality_gate_failures

    record = {
        "agent_process_passed": True,
        "final_container_exit_code": 0,
        "source_input_immutable_policy": {"status": "pass"},
        "quality_signals": {
            "job_guidance_primary_validation_metric": {
                "expected_primary_metric": "AUROC",
                "metric_value_available": False,
                "reported_validation_metric": {"name": None, "value": None, "reported_values": []},
            }
        },
    }

    failures = quality_gate_failures({}, record, 0)

    assert "required_validation_metric_status=missing" in failures


def test_quality_gate_failures_derives_critical_quality_check_failure():
    from harness.scenarios import quality_gate_failures

    record = {
        "agent_process_passed": True,
        "final_container_exit_code": 0,
        "source_input_immutable_policy": {"status": "pass"},
        "quality_checks": [{"severity": "critical", "status": "fail"}],
    }

    failures = quality_gate_failures({}, record, 0)

    assert "critical_quality_checks_failed" in failures


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


def test_execute_run_plan_writes_canonical_records_repeat_and_scenario_summary(tmp_path, monkeypatch):
    from harness.common import write_json
    from harness.host import runner
    from harness.scenarios import compile_scenario

    raw = base_scenario(tmp_path)
    raw["repeat_count"] = 1
    raw["path_budget"] = 400
    compilation = compile_scenario(raw, base_dir=tmp_path)
    result_root = tmp_path / "results"

    def fake_run_case(config, *, logs=(), prefix=None):
        records_dir = config.result_dir / "records"
        records_dir.mkdir(parents=True, exist_ok=True)
        write_json(
            config.result_dir / "run_summary.json",
            {
                "mode": config.mode,
                "agent": config.agent,
                "agent_model": config.agent_model,
                "skills_enabled": config.use_preinstalled_skills,
                "agent_elapsed_seconds": 2 if config.use_preinstalled_skills else 3,
                "token_count": 10,
                "agent_process_passed": True,
                "final_container_exit_code": 0,
                "source_input_immutable_policy": {"status": "pass"},
            },
        )
        write_json(config.result_dir / "container_exit_code.json", {"exit_code": 0})
        write_json(records_dir / f"{config.mode}_agent_record.json", {"mode": config.mode})
        write_json(
            records_dir / f"{config.mode}_record.json",
            {
                "mode": config.mode,
                "agent": config.agent,
                "agent_model": config.agent_model,
                "agent_process_passed": True,
                "final_container_exit_code": 0,
                "source_input_immutable_policy": {"status": "pass"},
                "process_metrics": {
                    "agent_elapsed_seconds": 2 if config.use_preinstalled_skills else 3,
                    "elapsed_seconds": 2 if config.use_preinstalled_skills else 3,
                    "token_count": 10,
                    "agent_exit_code": 0,
                },
            },
        )
        return 0

    monkeypatch.setattr(runner, "run_case_safely", fake_run_case)

    statuses, summary = runner.execute_run_plan(compilation, result_root=result_root)

    first_record_dir = result_root / compilation.run_plan["entries"][0]["record_dir"]
    assert statuses == {"run_00001": 0, "run_00002": 0}
    assert (result_root / "scenario.json").is_file()
    assert (result_root / "run_plan.json").is_file()
    assert (first_record_dir / "record_summary.json").is_file()
    assert (first_record_dir / "benchmark_record.json").is_file()
    assert (first_record_dir.parent / "repeat_summary.json").is_file()
    assert not (result_root / "without_skills").exists()
    assert summary["status"] == "ok"
    assert summary["aggregate_results"]["winner"]["label"] == "with_skills"
    assert (result_root / "reports" / "scenario_report.md").is_file()


def test_comparison_group_summary_ignores_non_numeric_token_count():
    from harness.scenarios import comparison_group_summary

    group = {
        "comparison_group_id": "group_001",
        "comparison_type": "mode_ablation",
        "compared_run_ids": ["run_00001", "run_00002"],
    }
    runs_by_id = {
        "run_00001": {
            "run_id": "run_00001",
            "mode": "without_skills",
            "quality_gate_passed": True,
            "agent_elapsed_seconds": 2,
            "token_count": {"bad": "shape"},
        },
        "run_00002": {
            "run_id": "run_00002",
            "mode": "with_skills",
            "quality_gate_passed": True,
            "agent_elapsed_seconds": 3,
            "token_count": 1,
        },
    }

    summary = comparison_group_summary(group, runs_by_id)

    assert summary["winner"]["run_id"] == "run_00001"


def test_replay_result_root_regenerates_agent_parser_artifacts(tmp_path):
    from harness.agents.registry import load_agent_adapter
    from harness.common import write_json
    from harness.host.runner import replay_result_root
    from harness.scenarios import compile_scenario

    raw = base_scenario(tmp_path)
    raw["agents"] = [{"name": "claude", "models": ["claude-test"]}]
    raw["comparison"] = {"type": "one", "mode": "with_skills"}
    raw["repeat_count"] = 1
    compilation = compile_scenario(raw, base_dir=tmp_path)
    result_root = tmp_path / "captured"
    compilation.write(result_root)
    entry = compilation.run_plan["entries"][0]
    record_dir = result_root / entry["record_dir"]
    record_dir.mkdir(parents=True)
    adapter = load_agent_adapter("claude")
    raw_events = [
        {
            "type": "assistant",
            "message": {
                "content": [{"type": "tool_use", "name": "Bash", "input": {"command": "python job.py"}}],
                "usage": {"input_tokens": 1, "output_tokens": 2},
            },
        },
        {
            "type": "result",
            "subtype": "success",
            "result": "done",
            "usage": {"input_tokens": 4, "output_tokens": 5},
            "total_cost_usd": 0.01,
        },
    ]
    with (record_dir / "agent_events.jsonl").open("w", encoding="utf-8") as stream:
        for event in raw_events:
            stream.write(json.dumps(adapter.normalize_event(json.dumps(event))) + "\n")
    write_json(record_dir / "run_summary.json", {"agent_process_passed": True, "final_container_exit_code": 0})
    write_json(record_dir / "container_exit_code.json", {"exit_code": 0})
    records_dir = record_dir / "records"
    records_dir.mkdir()
    write_json(records_dir / "with_skills_record.json", {"agent_process_passed": True, "final_container_exit_code": 0})

    summary = replay_result_root(result_root)

    usage = json.loads((record_dir / "agent_usage.json").read_text(encoding="utf-8"))
    activity = json.loads((record_dir / "agent_activity.json").read_text(encoding="utf-8"))
    assert usage["total_tokens"] == 9
    assert usage["cost"] == 0.01
    assert activity["commands"] == ["python job.py"]
    assert (record_dir / "record_summary.json").is_file()
    assert summary["completed_run_count"] == 1
    assert (result_root / "reports" / "scenario_report.json").is_file()
