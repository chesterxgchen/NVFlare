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
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml

from .agents.registry import load_agent_adapter
from .common import write_json
from .modes import mode_spec

SCHEMA_VERSION = "1"
COMPARISON_MODE_ABLATION = "mode_ablation"
COMPARISON_AGENT = "agent_comparison"
COMPARISON_MODEL = "model_comparison"
COMPARISON_ONE = "one"
COMPARISON_TYPES = {COMPARISON_MODE_ABLATION, COMPARISON_AGENT, COMPARISON_MODEL, COMPARISON_ONE}
JOB_SCALES = {"small", "medium", "large"}
DEFAULT_PATH_BUDGET = 240
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


def resolve_prompt(raw: Mapping[str, Any], base_dir: Path) -> dict[str, Any]:
    value = raw.get("prompt_path") or raw.get("prompt_file") or raw.get("prompt")
    if isinstance(value, dict):
        if value.get("template") and not value.get("path"):
            raise ScenarioValidationError("prompt templates are not implemented in this scenario-engine slice")
        value = value.get("path")
    prompt_text = require_non_empty_string(value, "prompt path")
    prompt_path = resolve_path(prompt_text, base_dir)
    if not prompt_path.is_file():
        raise ScenarioValidationError(f"Prompt file must exist: {prompt_path}")
    prompt_bytes = prompt_path.read_bytes()
    return {
        "path": str(prompt_path.resolve()),
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


def resource_policy_for(scale: str, scenario_raw: Mapping[str, Any], job_raw: Mapping[str, Any]) -> dict[str, int]:
    policy = dict(DEFAULT_RESOURCE_POLICIES[scale])
    scenario_policy = scenario_raw.get("resource_policy") or {}
    if isinstance(scenario_policy, dict):
        global_overrides = scenario_policy.get(scale) or {}
        if isinstance(global_overrides, dict):
            policy.update({str(key): int(value) for key, value in global_overrides.items()})
    job_policy = job_raw.get("resource_policy") or {}
    if isinstance(job_policy, dict):
        policy.update({str(key): int(value) for key, value in job_policy.items()})
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
        policy = resource_policy_for(scale, raw, data)
        jobs.append(JobSpec(path=path, name=name, scale=scale, resource_policy=policy))
        resolved.append({"name": name, "path": str(path), "scale": scale, "resource_policy": policy})
    return jobs, resolved


def resolve_repeat_count(raw: Mapping[str, Any]) -> int:
    value = raw.get("repeat_count", 1)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ScenarioValidationError("repeat_count must be a positive integer")
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
    attempt_index: int = 1,
) -> str:
    return (
        f"records/agent={agent_slug}/model={model_slug}/workflow={workflow_slug}/job={job_slug}/"
        f"repeat={repeat_index:02d}/mode={mode}/attempt={attempt_index:02d}"
    )


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
    model_slug = slugs["models"][f"{agent.name}\0{model.name}"]
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
        "attempt_index": 1,
        "attempt_id": "01",
        "attempt_count": 1,
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
    for agent in agents.values():
        for model in agent.models or (agent.default_model,):
            model_values_by_agent.setdefault(agent.name, []).append(model)
    if comparison.get("type") == COMPARISON_MODEL:
        agent_name = str(comparison["agent"])
        for model in comparison["models"]:
            model_values_by_agent.setdefault(agent_name, []).append(str(model))
    if comparison.get("type") == COMPARISON_AGENT and isinstance(comparison.get("models_by_agent"), dict):
        for agent_name, value in comparison["models_by_agent"].items():
            for model in model_list(value, f"comparison.models_by_agent.{agent_name}"):
                model_values_by_agent.setdefault(str(agent_name), []).append(model)
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


def validate_path_budget(scenario_name: str, entries: list[dict[str, Any]], path_budget: int) -> None:
    prefix = Path("results") / slugify(scenario_name)
    for entry in entries:
        longest = max(str(Path(path)) for path in entry["artifact_paths"].values())
        candidate = prefix / longest
        if len(str(candidate)) > path_budget:
            raise ScenarioValidationError(f"Expanded artifact path exceeds path_budget={path_budget}: {candidate}")


def compile_scenario(
    raw: Mapping[str, Any], *, base_dir: str | Path, source_path: str | Path | None = None
) -> ScenarioCompilation:
    base_path = Path(base_dir)
    name = require_non_empty_string(raw.get("name"), "name")
    prompt = resolve_prompt(raw, base_path)
    agents, resolved_agents = resolve_agents(raw)
    workflows, resolved_workflows = resolve_workflows(raw)
    jobs, resolved_jobs = resolve_jobs(raw, base_path)
    repeat_count = resolve_repeat_count(raw)
    path_budget = resolve_path_budget(raw)
    comparison = validate_comparison(raw, agents)
    fail_fast = bool(raw.get("fail_fast", False))

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
