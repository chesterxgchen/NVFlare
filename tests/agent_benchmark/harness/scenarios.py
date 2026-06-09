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

"""Scenario parsing, validation, and run-plan expansion for agent benchmarks."""

from __future__ import annotations

import argparse
import hashlib
import re
import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml

from .agents.registry import load_agent_adapter
from .common import load_json, write_json
from .modes import mode_spec
from .quality_signals import critical_quality_checks_failed, required_validation_metric_status
from .reports.scenario_report import write_scenario_report

SCHEMA_VERSION = "1"
COMPARISON_MODE_ABLATION = "mode_ablation"
COMPARISON_AGENT = "agent_comparison"
COMPARISON_MODEL = "model_comparison"
COMPARISON_ONE = "one"
COMPARISON_TYPES = {COMPARISON_MODE_ABLATION, COMPARISON_AGENT, COMPARISON_MODEL, COMPARISON_ONE}
JOB_SCALES = {"small", "medium", "large"}
DEFAULT_PATH_BUDGET = 240
MAX_PROMPT_BYTES = 4 * 1024 * 1024
SLUG_VISIBLE_LENGTH = 48

DEFAULT_RESOURCE_POLICIES: dict[str, dict[str, int]] = {
    "small": {
        "agent_timeout_seconds": 30 * 60,
        "container_timeout_seconds": 40 * 60,
        "result_size_budget_bytes": 1 * 1024 * 1024 * 1024,
    },
    "medium": {
        "agent_timeout_seconds": 90 * 60,
        "container_timeout_seconds": 120 * 60,
        "result_size_budget_bytes": 5 * 1024 * 1024 * 1024,
    },
    "large": {
        "agent_timeout_seconds": 240 * 60,
        "container_timeout_seconds": 300 * 60,
        "result_size_budget_bytes": 20 * 1024 * 1024 * 1024,
    },
}

DEFAULT_QUALITY_GATE = {
    "agent_process_passed": True,
    "final_container_exit_code": 0,
    "source_input_modified": False,
    "required_validation_metric_status": ["present", "not_required"],
    "critical_quality_checks_failed": False,
}
DEFAULT_WINNER_POLICY = "median_agent_elapsed_seconds_then_tokens_with_quality_gate"
SUMMARY_RUN_FIELDS = (
    "run_id",
    "sequence",
    "scenario_name",
    "comparison_type",
    "comparison_group_id",
    "agent",
    "agent_model",
    "workflow",
    "job_name",
    "job_slug",
    "job_path",
    "job_scale",
    "repeat_index",
    "mode",
    "skills_enabled",
    "prompt_hash",
    "record_dir",
)


class ScenarioValidationError(ValueError):
    """Raised when a scenario cannot produce a valid run plan."""


@dataclass(frozen=True)
class ScenarioCompilation:
    scenario: dict[str, Any]
    run_plan: dict[str, Any]

    def write(self, output_dir: str | Path) -> None:
        path = Path(output_dir)
        path.mkdir(parents=True, exist_ok=True)
        write_json(path / "scenario.json", self.scenario)
        write_json(path / "run_plan.json", self.run_plan)


@dataclass(frozen=True)
class AgentSpec:
    name: str
    models: tuple[str, ...]
    default_model: str


@dataclass(frozen=True)
class ModelSpec:
    name: str
    source: str


@dataclass(frozen=True)
class WorkflowSpec:
    name: str


@dataclass(frozen=True)
class JobSpec:
    path: Path
    name: str
    scale: str
    resource_policy: dict[str, int]


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]


def slug_base(value: str) -> tuple[str, bool]:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_")
    return normalized[:SLUG_VISIBLE_LENGTH].rstrip("_"), len(normalized) > SLUG_VISIBLE_LENGTH


def slugify(value: str, *, force_hash: bool = False) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_")
    hash_input = normalized or str(value) or "empty"
    suffix = stable_hash(hash_input)
    if not normalized:
        return f"item_{suffix}"
    visible = normalized[:SLUG_VISIBLE_LENGTH].rstrip("_")
    if force_hash or len(normalized) > SLUG_VISIBLE_LENGTH:
        return f"{visible}_{suffix}"
    return visible


def unique_slug_map(values: Iterable[str]) -> dict[str, str]:
    ordered = list(dict.fromkeys(str(value) for value in values))
    bases: dict[str, list[str]] = {}
    truncated: dict[str, bool] = {}
    for value in ordered:
        base, was_truncated = slug_base(value)
        base = base or "item"
        bases.setdefault(base, []).append(value)
        truncated[value] = was_truncated
    result = {}
    for value in ordered:
        base, _was_truncated = slug_base(value)
        base = base or "item"
        result[value] = slugify(value, force_hash=truncated[value] or len(bases[base]) > 1)
    return result


def require_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ScenarioValidationError(f"{label} must be a mapping")
    return value


def require_non_empty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ScenarioValidationError(f"{label} must be a non-empty string")
    return value.strip()


def as_list(value: Any, label: str) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    raise ScenarioValidationError(f"{label} must be a list")


def model_list(value: Any, label: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, list):
        items = value
    else:
        raise ScenarioValidationError(f"{label} must be a string or list of strings")
    models = tuple(require_non_empty_string(item, label) for item in items)
    if len(set(models)) != len(models):
        raise ScenarioValidationError(f"{label} contains duplicate model names")
    return models


def resolve_path(value: str, base_dir: Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else base_dir / path


def load_yaml_file(path: str | Path) -> dict[str, Any]:
    scenario_path = Path(path)
    try:
        raw = yaml.safe_load(scenario_path.read_text(encoding="utf-8")) or {}
    except OSError as exc:
        raise ScenarioValidationError(f"Could not read scenario file {scenario_path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ScenarioValidationError(f"Scenario file {scenario_path} must contain a YAML object")
    return raw


def resolve_prompt(raw: Mapping[str, Any], base_dir: Path, *, allow_external_prompt: bool = False) -> dict[str, Any]:
    value = raw.get("prompt_path") or raw.get("prompt_file") or raw.get("prompt")
    if isinstance(value, dict):
        if value.get("template") and not value.get("path"):
            raise ScenarioValidationError("prompt templates are not implemented in this scenario-engine slice")
        value = value.get("path")
    prompt_text = require_non_empty_string(value, "prompt path")
    prompt_path = resolve_path(prompt_text, base_dir)
    base_root = base_dir.resolve()
    resolved_prompt_path = prompt_path.resolve()
    if not allow_external_prompt and not resolved_prompt_path.is_relative_to(base_root):
        raise ScenarioValidationError(f"Prompt file must stay within scenario directory {base_root}: {prompt_path}")
    if not prompt_path.is_file():
        raise ScenarioValidationError(f"Prompt file must exist: {prompt_path}")
    try:
        prompt_bytes = prompt_path.read_bytes()
    except OSError as exc:
        raise ScenarioValidationError(f"Could not read prompt file {prompt_path}: {exc}") from exc
    if len(prompt_bytes) > MAX_PROMPT_BYTES:
        raise ScenarioValidationError(
            f"Prompt file exceeds max size {MAX_PROMPT_BYTES} bytes: {prompt_path} ({len(prompt_bytes)} bytes)"
        )
    return {
        "path": str(resolved_prompt_path),
        "source_type": "file",
        "sha256": hashlib.sha256(prompt_bytes).hexdigest(),
        "bytes": len(prompt_bytes),
    }


def resolve_agents(raw: Mapping[str, Any]) -> tuple[dict[str, AgentSpec], list[dict[str, Any]]]:
    agents_raw = as_list(raw.get("agents"), "agents")
    if not agents_raw:
        raise ScenarioValidationError("agents must contain at least one agent")
    agents: dict[str, AgentSpec] = {}
    resolved = []
    for index, item in enumerate(agents_raw):
        if isinstance(item, str):
            name = item
            models = ()
        else:
            data = require_mapping(item, f"agents[{index}]")
            name = require_non_empty_string(data.get("name"), f"agents[{index}].name")
            models = model_list(data.get("models", data.get("model")), f"agents[{index}].models")
        if name in agents:
            raise ScenarioValidationError(f"Duplicate agent entry: {name}")
        try:
            adapter = load_agent_adapter(name)
        except ValueError as exc:
            raise ScenarioValidationError(str(exc)) from exc
        try:
            default_model = adapter.default_model if models else adapter.model_from_env({})
        except ValueError as exc:
            raise ScenarioValidationError(str(exc)) from exc
        spec = AgentSpec(name=name, models=models, default_model=default_model)
        agents[name] = spec
        resolved.append(
            {
                "name": name,
                "models": list(models),
                "default_model": default_model,
                "model_source_when_unspecified": "adapter_default",
            }
        )
    return agents, resolved


def resolve_workflows(raw: Mapping[str, Any]) -> tuple[list[WorkflowSpec], list[dict[str, Any]]]:
    workflows_raw = as_list(raw.get("workflows"), "workflows")
    if not workflows_raw:
        raise ScenarioValidationError("workflows must contain at least one workflow")
    workflows = []
    for index, item in enumerate(workflows_raw):
        if isinstance(item, str):
            name = item
        else:
            data = require_mapping(item, f"workflows[{index}]")
            name = data.get("name")
        workflows.append(WorkflowSpec(require_non_empty_string(name, f"workflows[{index}].name")))
    if len({item.name for item in workflows}) != len(workflows):
        raise ScenarioValidationError("workflows contains duplicate names")
    return workflows, [{"name": item.name} for item in workflows]


def _integer_policy_overrides(raw: Mapping[str, Any], field_path: str) -> dict[str, int]:
    overrides = {}
    for key, value in raw.items():
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ScenarioValidationError(f"{field_path}.{key} must be an integer greater than 0; got {value!r}")
        overrides[str(key)] = value
    return overrides


def resource_policy_for(
    scale: str, scenario_raw: Mapping[str, Any], job_raw: Mapping[str, Any], job_policy_path: str
) -> dict[str, int]:
    policy = dict(DEFAULT_RESOURCE_POLICIES[scale])
    scenario_policy = scenario_raw.get("resource_policy") or {}
    if isinstance(scenario_policy, dict):
        global_overrides = scenario_policy.get(scale) or {}
        if isinstance(global_overrides, dict):
            policy.update(_integer_policy_overrides(global_overrides, f"resource_policy.{scale}"))
    job_policy = job_raw.get("resource_policy") or {}
    if isinstance(job_policy, dict):
        policy.update(_integer_policy_overrides(job_policy, job_policy_path))
    return policy


def resolve_jobs(raw: Mapping[str, Any], base_dir: Path) -> tuple[list[JobSpec], list[dict[str, Any]]]:
    jobs_raw = as_list(raw.get("jobs"), "jobs")
    if not jobs_raw:
        raise ScenarioValidationError("jobs must contain at least one job")
    jobs = []
    resolved = []
    for index, item in enumerate(jobs_raw):
        data = require_mapping(item, f"jobs[{index}]")
        path_value = require_non_empty_string(data.get("path"), f"jobs[{index}].path")
        path = resolve_path(path_value, base_dir).resolve()
        if not path.is_dir():
            raise ScenarioValidationError(f"Job path must be an existing directory: {path}")
        scale = data.get("scale", data.get("job_scale"))
        scale = require_non_empty_string(scale, f"jobs[{index}].scale")
        if scale not in JOB_SCALES:
            raise ScenarioValidationError(f"jobs[{index}].scale must be one of: {', '.join(sorted(JOB_SCALES))}")
        name = require_non_empty_string(data.get("name") or path.name, f"jobs[{index}].name")
        policy = resource_policy_for(scale, raw, data, f"jobs[{index}].resource_policy")
        jobs.append(JobSpec(path=path, name=name, scale=scale, resource_policy=policy))
        resolved.append({"name": name, "path": str(path), "scale": scale, "resource_policy": policy})
    return jobs, resolved


def resolve_repeat_count(raw: Mapping[str, Any]) -> int:
    value = raw.get("repeat_count", 1)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ScenarioValidationError("repeat_count must be a positive integer")
    return value


def resolve_fail_fast(raw: Mapping[str, Any]) -> bool:
    value = raw.get("fail_fast", False)
    if not isinstance(value, bool):
        raise ScenarioValidationError(f"fail_fast must be a boolean; got {value!r}")
    return value


def resolve_path_budget(raw: Mapping[str, Any]) -> int:
    value = raw.get("path_budget", DEFAULT_PATH_BUDGET)
    if isinstance(value, bool) or not isinstance(value, int) or value < 80:
        raise ScenarioValidationError("path_budget must be an integer >= 80")
    return value


def validate_mode(mode: Any, label: str) -> str:
    mode_name = require_non_empty_string(mode, label)
    try:
        mode_spec(mode_name)
    except ValueError as exc:
        raise ScenarioValidationError(str(exc)) from exc
    return mode_name


def validate_comparison(raw: Mapping[str, Any], agents: Mapping[str, AgentSpec]) -> dict[str, Any]:
    comparison = require_mapping(raw.get("comparison"), "comparison")
    comparison_type = require_non_empty_string(comparison.get("type"), "comparison.type")
    if comparison_type not in COMPARISON_TYPES:
        raise ScenarioValidationError(
            f"comparison.type must be one of: {', '.join(sorted(COMPARISON_TYPES))}; got {comparison_type}"
        )
    resolved = dict(comparison)
    if comparison_type == COMPARISON_MODE_ABLATION:
        modes = [
            validate_mode(item, "comparison.modes[]") for item in as_list(comparison.get("modes"), "comparison.modes")
        ]
        if not modes:
            raise ScenarioValidationError("comparison.modes must contain at least one mode")
        if len(set(modes)) != len(modes):
            raise ScenarioValidationError("comparison.modes contains duplicate modes")
        resolved["modes"] = modes
    elif comparison_type == COMPARISON_ONE:
        resolved["mode"] = validate_mode(comparison.get("mode"), "comparison.mode")
    elif comparison_type == COMPARISON_AGENT:
        resolved["mode"] = validate_mode(comparison.get("mode"), "comparison.mode")
        compared_agents = [
            item if isinstance(item, str) else require_mapping(item, "comparison.agents[]").get("name")
            for item in as_list(comparison.get("agents"), "comparison.agents")
        ]
        compared_agents = [require_non_empty_string(item, "comparison.agents[]") for item in compared_agents]
        if not compared_agents:
            raise ScenarioValidationError("comparison.agents must contain at least one agent")
        if len(set(compared_agents)) != len(compared_agents):
            raise ScenarioValidationError("comparison.agents contains duplicate agents")
        for agent in compared_agents:
            if agent not in agents:
                raise ScenarioValidationError(f"comparison.agents includes {agent!r}, but agents does not define it")
        resolved["agents"] = compared_agents
    elif comparison_type == COMPARISON_MODEL:
        agent = require_non_empty_string(comparison.get("agent"), "comparison.agent")
        if agent not in agents:
            raise ScenarioValidationError(f"comparison.agent {agent!r} is not listed in agents")
        resolved["agent"] = agent
        resolved["mode"] = validate_mode(comparison.get("mode"), "comparison.mode")
        models = model_list(comparison.get("models"), "comparison.models")
        if not models:
            raise ScenarioValidationError("comparison.models must contain at least one model")
        resolved["models"] = list(models)
    return resolved


def agent_model_options(agent: AgentSpec) -> list[ModelSpec]:
    if agent.models:
        return [ModelSpec(name=model, source="scenario") for model in agent.models]
    return [ModelSpec(name=agent.default_model, source="adapter_default")]


def resolve_agent_comparison_models(
    comparison: Mapping[str, Any], agents: Mapping[str, AgentSpec]
) -> dict[str, ModelSpec]:
    explicit = comparison.get("models_by_agent") or {}
    if explicit and not isinstance(explicit, dict):
        raise ScenarioValidationError("comparison.models_by_agent must be a mapping")
    resolved = {}
    for agent_name in comparison["agents"]:
        if agent_name in explicit:
            models = model_list(explicit[agent_name], f"comparison.models_by_agent.{agent_name}")
            if len(models) != 1:
                raise ScenarioValidationError(
                    f"comparison.models_by_agent.{agent_name} must resolve to exactly one model"
                )
            resolved[agent_name] = ModelSpec(models[0], "comparison.models_by_agent")
            continue
        agent = agents[agent_name]
        if len(agent.models) > 1:
            raise ScenarioValidationError(
                f"agent_comparison model selection is ambiguous for {agent_name}; "
                "use comparison.models_by_agent or configure exactly one top-level model"
            )
        if len(agent.models) == 1:
            resolved[agent_name] = ModelSpec(agent.models[0], "scenario")
        else:
            resolved[agent_name] = ModelSpec(agent.default_model, "adapter_default")
    return resolved


def artifact_paths(record_dir: str) -> dict[str, str]:
    return {
        "record_dir": record_dir,
        "record_summary": f"{record_dir}/record_summary.json",
        "agent_events": f"{record_dir}/agent_events.jsonl",
        "agent_usage": f"{record_dir}/agent_usage.json",
        "agent_activity": f"{record_dir}/agent_activity.json",
        "agent_last_message": f"{record_dir}/agent_last_message.txt",
        "agent_stderr": f"{record_dir}/agent_stderr.txt",
        "agent_record": f"{record_dir}/agent_record.json",
        "benchmark_record": f"{record_dir}/benchmark_record.json",
        "input_delta_manifest": f"{record_dir}/input_delta_manifest.json",
        "workspace_delta_manifest": f"{record_dir}/workspace_delta_manifest.json",
    }


def record_dir_for(
    *,
    agent_slug: str,
    model_slug: str,
    workflow_slug: str,
    job_slug: str,
    repeat_index: int,
    mode: str,
) -> str:
    return (
        f"records/agent={agent_slug}/model={model_slug}/workflow={workflow_slug}/job={job_slug}/"
        f"repeat={repeat_index:02d}/mode={mode}"
    )


def model_slug_for(slugs: Mapping[str, Mapping[str, str]], agent_name: str, model_name: str) -> str:
    return slugs["models"].get(f"{agent_name}\0{model_name}") or slugify(model_name)


def build_run_entry(
    *,
    scenario_name: str,
    comparison_type: str,
    comparison_group_id: str,
    sequence: int,
    agent: AgentSpec,
    model: ModelSpec,
    workflow: WorkflowSpec,
    job: JobSpec,
    mode: str,
    repeat_index: int,
    prompt: Mapping[str, Any],
    slugs: Mapping[str, Mapping[str, str]],
) -> dict[str, Any]:
    spec = mode_spec(mode)
    agent_slug = slugs["agents"][agent.name]
    model_slug = model_slug_for(slugs, agent.name, model.name)
    workflow_slug = slugs["workflows"][workflow.name]
    job_slug = slugs["jobs"][job.name]
    record_dir = record_dir_for(
        agent_slug=agent_slug,
        model_slug=model_slug,
        workflow_slug=workflow_slug,
        job_slug=job_slug,
        repeat_index=repeat_index,
        mode=mode,
    )
    return {
        "run_id": f"run_{sequence:05d}",
        "sequence": sequence,
        "scenario_name": scenario_name,
        "comparison_type": comparison_type,
        "comparison_group_id": comparison_group_id,
        "agent": agent.name,
        "agent_slug": agent_slug,
        "agent_model": model.name,
        "agent_model_slug": model_slug,
        "model_source": model.source,
        "workflow": workflow.name,
        "workflow_slug": workflow_slug,
        "job_name": job.name,
        "job_slug": job_slug,
        "job_path": str(job.path),
        "job_scale": job.scale,
        "resource_policy": job.resource_policy,
        "repeat_index": repeat_index,
        "repeat_id": f"{repeat_index:02d}",
        "mode": mode,
        "mode_label": spec.label,
        "skills_enabled": spec.skills_enabled,
        "prompt_source": prompt["path"],
        "prompt_hash": prompt["sha256"],
        "prompt_bytes": prompt["bytes"],
        "record_dir": record_dir,
        "artifact_paths": artifact_paths(record_dir),
    }


def slug_context(
    agents: Mapping[str, AgentSpec],
    workflows: list[WorkflowSpec],
    jobs: list[JobSpec],
    comparison: Mapping[str, Any],
) -> dict[str, dict[str, str]]:
    model_values_by_agent: dict[str, list[str]] = {}

    def append_model(agent_name: str, model_name: str) -> None:
        values = model_values_by_agent.setdefault(agent_name, [])
        if model_name not in values:
            values.append(model_name)

    for agent in agents.values():
        for model in agent.models or (agent.default_model,):
            append_model(agent.name, model)
    if comparison.get("type") == COMPARISON_MODEL:
        agent_name = str(comparison["agent"])
        for model in comparison["models"]:
            append_model(agent_name, str(model))
    if comparison.get("type") == COMPARISON_AGENT and isinstance(comparison.get("models_by_agent"), dict):
        for agent_name, value in comparison["models_by_agent"].items():
            for model in model_list(value, f"comparison.models_by_agent.{agent_name}"):
                append_model(str(agent_name), model)
    model_slugs = {}
    for agent_name, values in model_values_by_agent.items():
        per_agent = unique_slug_map(values)
        for value, slug in per_agent.items():
            model_slugs[f"{agent_name}\0{value}"] = slug
    return {
        "agents": unique_slug_map(agent.name for agent in agents.values()),
        "models": model_slugs,
        "workflows": unique_slug_map(workflow.name for workflow in workflows),
        "jobs": unique_slug_map(job.name for job in jobs),
    }


def append_group(
    *,
    groups: list[dict[str, Any]],
    entries: list[dict[str, Any]],
    group_index: int,
    group_axes: dict[str, Any],
    compared_entries: list[dict[str, Any]],
    comparison_type: str,
) -> None:
    group_id = f"group_{group_index:05d}"
    for entry in compared_entries:
        entry["comparison_group_id"] = group_id
        entries.append(entry)
    groups.append(
        {
            "comparison_group_id": group_id,
            "comparison_type": comparison_type,
            "group_axes": group_axes,
            "compared_run_ids": [entry["run_id"] for entry in compared_entries],
        }
    )


def expand_run_plan(
    *,
    scenario_name: str,
    comparison: Mapping[str, Any],
    agents: Mapping[str, AgentSpec],
    workflows: list[WorkflowSpec],
    jobs: list[JobSpec],
    repeat_count: int,
    prompt: Mapping[str, Any],
    path_budget: int,
) -> dict[str, Any]:
    comparison_type = str(comparison["type"])
    slugs = slug_context(agents, workflows, jobs, comparison)
    entries: list[dict[str, Any]] = []
    groups: list[dict[str, Any]] = []
    sequence = 0
    group_index = 0

    def next_entry(**kwargs: Any) -> dict[str, Any]:
        nonlocal sequence
        sequence += 1
        return build_run_entry(
            scenario_name=scenario_name,
            comparison_type=comparison_type,
            sequence=sequence,
            prompt=prompt,
            slugs=slugs,
            **kwargs,
        )

    if comparison_type in {COMPARISON_MODE_ABLATION, COMPARISON_ONE}:
        modes = comparison.get("modes") if comparison_type == COMPARISON_MODE_ABLATION else [comparison["mode"]]
        for agent in agents.values():
            for model in agent_model_options(agent):
                for workflow in workflows:
                    for job in jobs:
                        for repeat_index in range(1, repeat_count + 1):
                            group_index += 1
                            compared = [
                                next_entry(
                                    comparison_group_id="",
                                    agent=agent,
                                    model=model,
                                    workflow=workflow,
                                    job=job,
                                    mode=mode,
                                    repeat_index=repeat_index,
                                )
                                for mode in modes
                            ]
                            append_group(
                                groups=groups,
                                entries=entries,
                                group_index=group_index,
                                group_axes={
                                    "agent": agent.name,
                                    "agent_model": model.name,
                                    "workflow": workflow.name,
                                    "job_slug": slugs["jobs"][job.name],
                                    "repeat_index": repeat_index,
                                },
                                compared_entries=compared,
                                comparison_type=comparison_type,
                            )
    elif comparison_type == COMPARISON_AGENT:
        model_by_agent = resolve_agent_comparison_models(comparison, agents)
        mode = str(comparison["mode"])
        for workflow in workflows:
            for job in jobs:
                for repeat_index in range(1, repeat_count + 1):
                    group_index += 1
                    compared = [
                        next_entry(
                            comparison_group_id="",
                            agent=agents[agent_name],
                            model=model_by_agent[agent_name],
                            workflow=workflow,
                            job=job,
                            mode=mode,
                            repeat_index=repeat_index,
                        )
                        for agent_name in comparison["agents"]
                    ]
                    append_group(
                        groups=groups,
                        entries=entries,
                        group_index=group_index,
                        group_axes={
                            "mode": mode,
                            "workflow": workflow.name,
                            "job_slug": slugs["jobs"][job.name],
                            "repeat_index": repeat_index,
                        },
                        compared_entries=compared,
                        comparison_type=comparison_type,
                    )
    elif comparison_type == COMPARISON_MODEL:
        agent = agents[str(comparison["agent"])]
        mode = str(comparison["mode"])
        models = [ModelSpec(str(model), "comparison") for model in comparison["models"]]
        for workflow in workflows:
            for job in jobs:
                for repeat_index in range(1, repeat_count + 1):
                    group_index += 1
                    compared = [
                        next_entry(
                            comparison_group_id="",
                            agent=agent,
                            model=model,
                            workflow=workflow,
                            job=job,
                            mode=mode,
                            repeat_index=repeat_index,
                        )
                        for model in models
                    ]
                    append_group(
                        groups=groups,
                        entries=entries,
                        group_index=group_index,
                        group_axes={
                            "agent": agent.name,
                            "mode": mode,
                            "workflow": workflow.name,
                            "job_slug": slugs["jobs"][job.name],
                            "repeat_index": repeat_index,
                        },
                        compared_entries=compared,
                        comparison_type=comparison_type,
                    )

    validate_path_budget(scenario_name, entries, path_budget)
    return {
        "schema_version": SCHEMA_VERSION,
        "scenario_name": scenario_name,
        "generated_at": utc_timestamp(),
        "comparison_type": comparison_type,
        "run_count": len(entries),
        "comparison_group_count": len(groups),
        "execution": {"parallelism": 1},
        "quality_gate": DEFAULT_QUALITY_GATE,
        "winner_policy": DEFAULT_WINNER_POLICY,
        "entries": entries,
        "comparison_groups": groups,
    }


def validate_path_budget(
    scenario_name: str, entries: list[dict[str, Any]], path_budget: int, result_root: str | Path | None = None
) -> None:
    prefix = Path(result_root) if result_root is not None else Path("results") / slugify(scenario_name)
    for entry in entries:
        longest = max((str(Path(path)) for path in entry["artifact_paths"].values()), key=len)
        candidate = prefix / longest
        if len(str(candidate)) > path_budget:
            raise ScenarioValidationError(f"Expanded artifact path exceeds path_budget={path_budget}: {candidate}")


def compile_scenario(
    raw: Mapping[str, Any],
    *,
    base_dir: str | Path,
    source_path: str | Path | None = None,
    allow_external_prompt: bool = False,
) -> ScenarioCompilation:
    base_path = Path(base_dir)
    name = require_non_empty_string(raw.get("name"), "name")
    prompt = resolve_prompt(raw, base_path, allow_external_prompt=allow_external_prompt)
    agents, resolved_agents = resolve_agents(raw)
    workflows, resolved_workflows = resolve_workflows(raw)
    jobs, resolved_jobs = resolve_jobs(raw, base_path)
    repeat_count = resolve_repeat_count(raw)
    path_budget = resolve_path_budget(raw)
    comparison = validate_comparison(raw, agents)
    fail_fast = resolve_fail_fast(raw)

    scenario = {
        "schema_version": SCHEMA_VERSION,
        "name": name,
        "scenario_slug": slugify(name),
        "source_path": str(Path(source_path).resolve()) if source_path else None,
        "prompt": prompt,
        "agents": resolved_agents,
        "workflows": resolved_workflows,
        "jobs": resolved_jobs,
        "repeat_count": repeat_count,
        "comparison": comparison,
        "fail_fast": fail_fast,
        "path_budget": path_budget,
        "resource_policy_defaults": DEFAULT_RESOURCE_POLICIES,
    }
    run_plan = expand_run_plan(
        scenario_name=name,
        comparison=comparison,
        agents=agents,
        workflows=workflows,
        jobs=jobs,
        repeat_count=repeat_count,
        prompt=prompt,
        path_budget=path_budget,
    )
    run_plan["source_path"] = scenario["source_path"]
    run_plan["fail_fast"] = fail_fast
    return ScenarioCompilation(scenario=scenario, run_plan=run_plan)


def compile_scenario_file(path: str | Path) -> ScenarioCompilation:
    scenario_path = Path(path)
    raw = load_yaml_file(scenario_path)
    return compile_scenario(raw, base_dir=scenario_path.parent, source_path=scenario_path)


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def number_or_none(value: Any) -> float | None:
    return float(value) if is_number(value) else None


def number_or_zero(value: Any) -> float:
    return float(value) if is_number(value) else 0.0


def stats_for_values(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"count": 0, "median": None, "mean": None, "min": None, "max": None, "stddev": None}
    return {
        "count": len(values),
        "median": statistics.median(values),
        "mean": statistics.mean(values),
        "min": min(values),
        "max": max(values),
        "stddev": statistics.stdev(values) if len(values) >= 2 else None,
    }


def record_dir_path(result_root: Path, entry: Mapping[str, Any]) -> Path:
    return result_root / str(entry["record_dir"])


def repeat_dir_for_record(path: Path) -> Path:
    return path.parent


def benchmark_record_path(record_dir: Path, mode: str) -> Path:
    direct = record_dir / "benchmark_record.json"
    if direct.is_file():
        return direct
    return record_dir / "records" / f"{mode}_record.json"


def agent_record_path(record_dir: Path, mode: str) -> Path:
    direct = record_dir / "agent_record.json"
    if direct.is_file():
        return direct
    return record_dir / "records" / f"{mode}_agent_record.json"


def read_entry_artifacts(result_root: Path, entry: Mapping[str, Any]) -> dict[str, Any]:
    record_dir = record_dir_path(result_root, entry)
    mode = str(entry["mode"])
    summary = load_json(record_dir / "record_summary.json", None)
    if not isinstance(summary, dict):
        summary = load_json(record_dir / "run_summary.json", {}) or {}
    record = load_json(benchmark_record_path(record_dir, mode), {}) or {}
    container_exit = load_json(record_dir / "container_exit_code.json", {}) or {}
    return {
        "record_dir": record_dir,
        "summary": summary if isinstance(summary, dict) else {},
        "record": record if isinstance(record, dict) else {},
        "container_exit": container_exit if isinstance(container_exit, dict) else {},
    }


def quality_gate_failures(summary: Mapping[str, Any], record: Mapping[str, Any], status: int | None) -> list[str]:
    failures = []
    if status not in (0, None):
        failures.append(f"host_status={status}")
    agent_passed = summary.get("agent_process_passed", record.get("agent_process_passed"))
    if agent_passed is not True:
        failures.append("agent_process_passed")
    final_exit = summary.get("final_container_exit_code", record.get("final_container_exit_code"))
    if final_exit is None:
        failures.append("final_container_exit_code=not_recorded")
    elif final_exit != 0:
        failures.append(f"final_container_exit_code={final_exit}")
    policy = summary.get("source_input_immutable_policy")
    if not isinstance(policy, dict):
        policy = (
            record.get("source_input_immutable_policy")
            if isinstance(record.get("source_input_immutable_policy"), dict)
            else {}
        )
    if policy.get("status") == "fail":
        failures.append("source_input_modified")
    metric_status = (
        record.get("required_validation_metric_status")
        or summary.get("required_validation_metric_status")
        or required_validation_metric_status_from_artifacts(summary, record)
    )
    if metric_status and metric_status not in {"present", "not_required"}:
        failures.append(f"required_validation_metric_status={metric_status}")
    if (
        record.get("critical_quality_checks_failed")
        or summary.get("critical_quality_checks_failed")
        or critical_quality_checks_failed(summary, record)
    ):
        failures.append("critical_quality_checks_failed")
    if not summary and not record:
        failures.append("missing_record_summary")
    return failures


def required_validation_metric_status_from_artifacts(summary: Mapping[str, Any], record: Mapping[str, Any]) -> str:
    for artifact in (record, summary):
        quality = artifact.get("quality_signals") if isinstance(artifact, Mapping) else None
        if isinstance(quality, Mapping):
            signal = quality.get("job_guidance_primary_validation_metric") or quality.get(
                "readme_primary_validation_metric"
            )
            status = required_validation_metric_status(signal if isinstance(signal, Mapping) else None)
            if status != "not_required":
                return status
    return "not_required"


def run_summary_for_entry(result_root: Path, entry: Mapping[str, Any], statuses: Mapping[str, int]) -> dict[str, Any]:
    artifacts = read_entry_artifacts(result_root, entry)
    summary = artifacts["summary"]
    record = artifacts["record"]
    container_exit = artifacts["container_exit"]
    status = statuses.get(str(entry["run_id"]))
    if status is None:
        status = statuses.get(str(entry["mode"]))
    final_exit = summary.get("final_container_exit_code", record.get("final_container_exit_code"))
    if final_exit is None:
        final_exit = container_exit.get("exit_code")
    failures = quality_gate_failures(summary, record, status)
    required_metric_status = (
        record.get("required_validation_metric_status")
        or summary.get("required_validation_metric_status")
        or required_validation_metric_status_from_artifacts(summary, record)
    )
    critical_checks_failed = bool(
        record.get("critical_quality_checks_failed")
        or summary.get("critical_quality_checks_failed")
        or critical_quality_checks_failed(summary, record)
    )
    process_metrics = record.get("process_metrics") if isinstance(record.get("process_metrics"), dict) else {}
    agent_elapsed = summary.get("agent_elapsed_seconds")
    if agent_elapsed is None:
        agent_elapsed = process_metrics.get("agent_elapsed_seconds")
    token_count = summary.get("token_count")
    if token_count is None:
        token_count = process_metrics.get("token_count")
    payload = {key: entry.get(key) for key in SUMMARY_RUN_FIELDS}
    payload.update(
        {
            "status": "passed" if not failures else "failed",
            "host_status": status,
            "quality_gate_passed": not failures,
            "quality_gate_failures": failures,
            "required_validation_metric_status": required_metric_status,
            "critical_quality_checks_failed": critical_checks_failed,
            "agent_elapsed_seconds": agent_elapsed,
            "elapsed_seconds": summary.get("elapsed_seconds", process_metrics.get("elapsed_seconds")),
            "token_count": token_count,
            "cost": summary.get("cost", process_metrics.get("cost")),
            "agent_process_passed": summary.get("agent_process_passed", record.get("agent_process_passed")),
            "agent_exit_code": summary.get("agent_exit_code", process_metrics.get("agent_exit_code")),
            "final_container_exit_code": final_exit,
            "failure_root_cause": record.get("failure_root_cause") or record.get("failure_category"),
            "artifact_paths": entry.get("artifact_paths") or {},
        }
    )
    return payload


def comparison_label(entry: Mapping[str, Any]) -> str:
    comparison_type = str(entry.get("comparison_type") or "")
    if comparison_type == COMPARISON_MODE_ABLATION:
        return str(entry.get("mode"))
    if comparison_type == COMPARISON_AGENT:
        return str(entry.get("agent"))
    if comparison_type == COMPARISON_MODEL:
        return str(entry.get("agent_model"))
    return str(entry.get("mode") or entry.get("run_id"))


def comparison_group_summary(group: Mapping[str, Any], runs_by_id: Mapping[str, dict[str, Any]]) -> dict[str, Any]:
    compared = [runs_by_id[run_id] for run_id in group.get("compared_run_ids", []) if run_id in runs_by_id]
    winner = None
    candidates = [
        run for run in compared if run.get("quality_gate_passed") and is_number(run.get("agent_elapsed_seconds"))
    ]
    if candidates:
        winner_run = min(
            candidates, key=lambda item: (float(item["agent_elapsed_seconds"]), number_or_zero(item.get("token_count")))
        )
        winner = {
            "run_id": winner_run["run_id"],
            "label": comparison_label(winner_run),
            "agent_elapsed_seconds": winner_run.get("agent_elapsed_seconds"),
            "token_count": winner_run.get("token_count"),
        }
    return {
        "comparison_group_id": group.get("comparison_group_id"),
        "comparison_type": group.get("comparison_type"),
        "group_axes": group.get("group_axes") or {},
        "compared_runs": compared,
        "winner_policy": DEFAULT_WINNER_POLICY,
        "quality_gate": DEFAULT_QUALITY_GATE,
        "winner": winner,
        "status": "passed" if compared and all(run.get("quality_gate_passed") for run in compared) else "degraded",
    }


def aggregate_results(runs: list[dict[str, Any]]) -> dict[str, Any]:
    by_label: dict[str, list[dict[str, Any]]] = {}
    for run in runs:
        by_label.setdefault(comparison_label(run), []).append(run)
    aggregate = {}
    for label, items in sorted(by_label.items()):
        elapsed_values = [
            float(item["agent_elapsed_seconds"]) for item in items if is_number(item.get("agent_elapsed_seconds"))
        ]
        token_values = [float(item["token_count"]) for item in items if is_number(item.get("token_count"))]
        aggregate[label] = {
            "run_count": len(items),
            "quality_pass_count": sum(1 for item in items if item.get("quality_gate_passed")),
            "quality_fail_count": sum(1 for item in items if not item.get("quality_gate_passed")),
            "agent_elapsed_seconds": stats_for_values(elapsed_values),
            "token_count": stats_for_values(token_values),
        }
    candidates = [
        (label, data)
        for label, data in aggregate.items()
        if data["quality_pass_count"] > 0 and data["agent_elapsed_seconds"]["median"] is not None
    ]
    winner = None
    if candidates:
        label, data = min(
            candidates,
            key=lambda item: (
                float(item[1]["agent_elapsed_seconds"]["median"]),
                float(item[1]["token_count"]["median"] or 0),
            ),
        )
        winner = {
            "label": label,
            "median_agent_elapsed_seconds": data["agent_elapsed_seconds"]["median"],
            "median_token_count": data["token_count"]["median"],
        }
    return {"by_label": aggregate, "winner": winner, "winner_policy": DEFAULT_WINNER_POLICY}


def write_repeat_summaries(result_root: Path, runs: list[dict[str, Any]]) -> None:
    by_repeat: dict[Path, list[dict[str, Any]]] = {}
    for run in runs:
        by_repeat.setdefault(repeat_dir_for_record(result_root / str(run["record_dir"])), []).append(run)
    for repeat_dir, items in by_repeat.items():
        repeat_dir.mkdir(parents=True, exist_ok=True)
        write_json(
            repeat_dir / "repeat_summary.json",
            {
                "schema_version": SCHEMA_VERSION,
                "repeat_index": items[0].get("repeat_index"),
                "mode_summaries": items,
                "status": "passed" if all(item.get("quality_gate_passed") for item in items) else "degraded",
            },
        )


def write_scenario_summaries(result_root: str | Path, statuses: Mapping[str, int] | None = None) -> dict[str, Any]:
    root = Path(result_root)
    statuses = statuses or {}
    run_plan = load_json(root / "run_plan.json", {}) or {}
    scenario = load_json(root / "scenario.json", {}) or {}
    entries = run_plan.get("entries") if isinstance(run_plan.get("entries"), list) else []
    runs = [run_summary_for_entry(root, entry, statuses) for entry in entries if isinstance(entry, dict)]
    runs_by_id = {str(run["run_id"]): run for run in runs}
    comparison_groups = [
        comparison_group_summary(group, runs_by_id)
        for group in run_plan.get("comparison_groups", [])
        if isinstance(group, dict)
    ]
    write_repeat_summaries(root, runs)
    aggregate = aggregate_results(runs)
    completed = sum(
        1 for run in runs if run.get("host_status") is not None or run.get("final_container_exit_code") is not None
    )
    failed = sum(1 for run in runs if not run.get("quality_gate_passed"))
    status = "ok" if runs and failed == 0 else "degraded" if completed else "not_run"
    summary = {
        "schema_version": SCHEMA_VERSION,
        "scenario_name": run_plan.get("scenario_name") or scenario.get("name"),
        "comparison_type": run_plan.get("comparison_type"),
        "expanded_case_count": len(entries),
        "completed_run_count": completed,
        "failed_run_count": failed,
        "repeat_count": scenario.get("repeat_count"),
        "status": status,
        "quality_gate": run_plan.get("quality_gate") or DEFAULT_QUALITY_GATE,
        "winner_policy": run_plan.get("winner_policy") or DEFAULT_WINNER_POLICY,
        "runs": runs,
        "comparison_groups": comparison_groups,
        "aggregate_results": aggregate,
    }
    write_json(root / "scenario_summary.json", summary)
    write_scenario_report(root, summary)
    return summary


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Compile an agent benchmark scenario into scenario.json/run_plan.json."
    )
    parser.add_argument("scenario", help="Scenario YAML file")
    parser.add_argument(
        "--output-dir", required=True, help="Directory where scenario.json and run_plan.json are written"
    )
    args = parser.parse_args(argv)
    compilation = compile_scenario_file(args.scenario)
    compilation.write(args.output_dir)


if __name__ == "__main__":
    main()
