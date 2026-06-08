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

"""Process-record synthesis, normalization, and report-gating helpers."""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .common import bool_from_text, flatten_numbers, load_json, write_json
from .quality_signals import metric_signal
from .record_identity import record_case, record_skill
from .reports.reporting import (
    discover_report_filter,
    has_evaluator_backed_record,
    write_report_filter,
    write_report_status,
)
from .timing import finalize_timing

ALLOWED_BEHAVIOR_STATUSES = {"pass", "fail", "missing", "not_applicable", "non_scoring_note"}
PROCESS_EVAL_SEMANTICS = (
    "harness metadata flag; NVFLARE_SKILL_EVAL is the runtime switch that enables NVFLARE skill evaluation"
)


def apply_record_runtime_fields(
    record: dict[str, Any],
    *,
    usage: dict[str, Any],
    mode: str,
    elapsed_seconds: int,
    codex_exit: int,
    skills_enabled: bool,
    process_eval: bool,
    eval_run_mode: str,
    nvflare_skill_eval: str,
    agent: str,
    agent_model: str,
    agent_record_present: bool | None = None,
    agent_record_valid: bool | None = None,
) -> dict[str, Any]:
    record["schema_version"] = "1"
    record["run_mode"] = record.get("run_mode") or eval_run_mode
    record["agent"] = record.get("agent") or agent
    record["mode"] = mode
    record["source"] = "docker_codex_benchmark"
    record["agent_model"] = record.get("agent_model") or agent_model
    record["skills_enabled"] = skills_enabled
    record["process_eval_enabled"] = process_eval
    record["process_evaluator_state"] = "on" if process_eval else "off"
    record["process_eval_semantics"] = PROCESS_EVAL_SEMANTICS
    record["nvflare_skill_eval"] = nvflare_skill_eval
    record["nvflare_skill_eval_state"] = "on" if nvflare_skill_eval == "on" else "off"
    record["codex_process_passed"] = codex_exit == 0
    record["codex_process_exit_code"] = codex_exit
    record["evaluator_modes"] = {
        "process_eval": record["process_evaluator_state"],
        "nvflare_skill_eval": record["nvflare_skill_eval_state"],
    }
    record["timestamp"] = record.get("timestamp") or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    if agent_record_present is not None:
        record["agent_record_present"] = agent_record_present
    if agent_record_valid is not None:
        record["agent_record_valid"] = agent_record_valid

    metrics = record.get("process_metrics")
    if not isinstance(metrics, dict):
        metrics = {}
        record["process_metrics"] = metrics
    metrics.update(
        {
            "elapsed_seconds": elapsed_seconds,
            "token_count": usage.get("total_tokens"),
            "codex_exit_code": codex_exit,
            "codex_process_passed": 1 if codex_exit == 0 else 0,
            "token_parser": usage.get("token_parser"),
            "process_eval_enabled": 1 if process_eval else 0,
            "process_eval_metadata_only": 1,
            "nvflare_skill_eval_enabled": 1 if nvflare_skill_eval == "on" else 0,
        }
    )
    if usage.get("token_parser_warnings"):
        metrics["token_parser_warning_count"] = len(usage["token_parser_warnings"])
    if agent_record_present is not None:
        metrics["agent_record_present"] = 1 if agent_record_present else 0
    if agent_record_valid is not None:
        metrics["agent_record_valid"] = 1 if agent_record_valid else 0
    return metrics


def same_path(left: str | Path, right: str | Path) -> bool:
    try:
        return Path(left).resolve() == Path(right).resolve()
    except Exception:
        return False


def record_is_candidate(record: Any) -> bool:
    return isinstance(record, dict) and (
        record_skill(record) or record_case(record) or isinstance(record.get("eval_passed"), bool)
    )


def load_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def run_start_cutoff_ns(value: int) -> int:
    # Backward-compatible CLI handling: old callers passed seconds, new callers pass time_ns().
    return max(0, value) * 1_000_000_000 if value < 1_000_000_000_000 else max(0, value)


def copy_default_evaluator_records(records_dir: Path, nvflare_skill_eval: str, run_start_time_ns: int) -> list[str]:
    default_root = Path.home() / ".nvflare" / "agent_skill_eval_runs"
    copied = []
    if nvflare_skill_eval != "on" or not default_root.exists() or same_path(default_root, records_dir):
        return copied
    cutoff_ns = run_start_cutoff_ns(run_start_time_ns)
    for src in sorted(default_root.rglob("*.json")):
        if not src.is_file() or src.is_symlink():
            continue
        try:
            if src.stat().st_mtime_ns < cutoff_ns:
                continue
        except OSError:
            continue
        rel = src.relative_to(default_root)
        dst = records_dir / rel
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if not dst.exists() or src.read_bytes() != dst.read_bytes():
                shutil.copy2(src, dst)
            copied.append(str(dst))
        except Exception:
            continue
    return copied


def iter_json_records(root: Path, agent_record_path: Path | None = None) -> Iterable[tuple[Path, dict[str, Any]]]:
    for path in sorted(root.rglob("*.json")):
        if not path.is_file() or path.is_symlink():
            continue
        if agent_record_path is not None and same_path(path, agent_record_path):
            continue
        if path.name.endswith("_agent_record.json") or path.name.endswith("_record.json"):
            continue
        data = load_json(path)
        if isinstance(data, dict):
            yield path, data
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    yield path, item


def path_is_current_run(path: Path, run_start_time_ns: int) -> bool:
    cutoff_ns = run_start_cutoff_ns(run_start_time_ns)
    try:
        return path.stat().st_mtime_ns >= cutoff_ns
    except OSError:
        return False


def discover_readme(input_root: Path) -> tuple[Path | None, str]:
    if not input_root.is_dir():
        return None, ""
    candidates = []
    for path in input_root.iterdir():
        if path.is_file() and path.name.lower().startswith("readme"):
            candidates.append(path)
    docs_dir = input_root / "docs"
    if docs_dir.is_dir():
        for path in docs_dir.iterdir():
            if path.is_file() and path.name.lower().startswith("readme"):
                candidates.append(path)
    if not candidates:
        return None, ""
    candidates.sort(key=lambda path: (0 if path.name.lower() == "readme.md" else 1, len(path.name), path.name.lower()))
    path = candidates[0]
    return path, load_text(path)


def available_skill_names() -> set[str]:
    names = set()
    skills_root = Path(os.environ.get("CODEX_HOME", "/workspace/.codex")) / "skills"
    if skills_root.is_dir():
        for path in skills_root.iterdir():
            if path.is_dir() and not path.name.startswith("."):
                names.add(path.name)
    return names


def eval_case_ids_for_skill(skill_name: str) -> list[str]:
    evals_path = (
        Path(os.environ.get("CODEX_HOME", "/workspace/.codex")) / "skills" / skill_name / "evals" / "evals.json"
    )
    data = load_json(evals_path)
    if not isinstance(data, dict):
        return []
    case_ids = []
    for item in data.get("evals") or []:
        if isinstance(item, dict) and item.get("id"):
            case_ids.append(str(item["id"]))
    return case_ids


IDENTITY_PLACEHOLDERS = {
    "CASE",
    "CASE_ID",
    "EVAL_ID",
    "SKILL",
    "SKILL_NAME",
    "<case>",
    "<case_id>",
    "<skill>",
    "<skill_name>",
}


def valid_identity_token(value: str) -> bool:
    normalized = value.strip()
    return (
        bool(normalized) and normalized not in IDENTITY_PLACEHOLDERS and normalized.upper() not in IDENTITY_PLACEHOLDERS
    )


def infer_from_events(events_text: str) -> dict[str, Any]:
    scores: dict[str, int] = {}
    source: dict[str, str] = {}

    def add(name: str, points: int, reason: str) -> None:
        if not valid_identity_token(name):
            return
        scores[name] = scores.get(name, 0) + points
        source.setdefault(name, reason)

    for match in re.finditer(r"/\.codex/skills/([^/\s\"']+)", events_text):
        add(match.group(1), 50, "codex_skill_path")

    for match in re.finditer(r"(?:^|\s)--skill(?:=|\s+)([A-Za-z0-9_.-]+)", events_text):
        add(match.group(1), 100, "agent_skills_evaluate_arg")

    for name in available_skill_names():
        occurrences = events_text.count(name)
        if occurrences:
            add(name, occurrences, "installed_skill_name_seen_in_events")

    skill = ""
    if scores:
        skill = sorted(scores.items(), key=lambda item: (item[1], item[0]), reverse=True)[0][0]

    case_id = ""
    case_source = ""
    case_match = re.search(r"(?:^|\s)--case(?:=|\s+)([A-Za-z0-9_.-]+)", events_text)
    if case_match and valid_identity_token(case_match.group(1)):
        case_id = case_match.group(1)
        case_source = "agent_skills_evaluate_arg"
    elif skill:
        case_scores = {}
        for candidate in eval_case_ids_for_skill(skill):
            count = events_text.count(candidate)
            if count:
                case_scores[candidate] = count
        if case_scores:
            case_id = sorted(case_scores.items(), key=lambda item: (item[1], item[0]), reverse=True)[0][0]
            case_source = "installed_skill_eval_case_seen_in_events"
    return {
        "skill": skill,
        "case_id": case_id,
        "skill_source": source.get(skill, "") if skill else "",
        "case_source": case_source,
        "skill_scores": dict(sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:5]),
        "used_as_fallback": False,
    }


def record_score(path: Path, record: dict[str, Any]) -> tuple[int, int, str]:
    score = 0
    if isinstance(record.get("eval_passed"), bool):
        score += 10
    if record.get("score") is not None:
        score += 3
    if record_skill(record):
        score += 2
    if record_case(record):
        score += 2
    try:
        mtime = path.stat().st_mtime_ns
    except OSError:
        mtime = 0
    return score, mtime, str(path)


def choose_source_record(
    candidates: list[tuple[Path, dict[str, Any]]],
    *,
    expected_skill: str = "",
    expected_case: str = "",
) -> tuple[Path | None, dict[str, Any] | None, dict[str, Any]]:
    audit: dict[str, Any] = {
        "candidate_count": len(candidates),
        "expected_skill": expected_skill or None,
        "expected_case": expected_case or None,
        "selection_reason": "",
        "selected_path": None,
        "selected_skill": None,
        "selected_case": None,
    }
    explicit_candidates = [
        (path, record) for path, record in candidates if record_skill(record) and record_case(record)
    ]
    audit["explicit_identity_candidate_count"] = len(explicit_candidates)
    if not explicit_candidates:
        audit["selection_reason"] = "no_explicit_identity_candidates"
        return None, None, audit

    filtered = explicit_candidates
    if expected_skill:
        filtered = [(path, record) for path, record in filtered if str(record_skill(record)) == str(expected_skill)]
    if expected_case:
        filtered = [(path, record) for path, record in filtered if str(record_case(record)) == str(expected_case)]
    audit["identity_matched_candidate_count"] = len(filtered)
    if (expected_skill or expected_case) and not filtered:
        audit["selection_reason"] = "no_candidate_matched_expected_identity"
        return None, None, audit

    identities = sorted({(str(record_skill(record)), str(record_case(record))) for _path, record in filtered})
    audit["candidate_identities"] = [{"skill": skill, "case": case} for skill, case in identities]
    if not expected_skill and not expected_case and len(identities) != 1:
        audit["selection_reason"] = "ambiguous_identity_without_expected_filter"
        return None, None, audit

    scored = []
    for path, record in filtered:
        score, mtime, path_text = record_score(path, record)
        scored.append((score, mtime, path_text, path, record))
    if not scored:
        audit["selection_reason"] = "no_scored_candidates"
        return None, None, audit
    scored.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    selected_path = scored[0][3]
    selected_record = scored[0][4]
    audit["selection_reason"] = "selected_explicit_identity_record"
    audit["selected_path"] = str(selected_path)
    audit["selected_skill"] = str(record_skill(selected_record))
    audit["selected_case"] = str(record_case(selected_record))
    audit["selected_score"] = scored[0][0]
    return selected_path, selected_record, audit


def synthesize_agent_record(
    agent_record_path: Path,
    records_dir: Path,
    events_path: Path,
    usage_path: Path,
    activity_path: Path,
    last_message_path: Path,
    input_dir: Path,
    mode: str,
    elapsed_seconds: int,
    codex_exit: int,
    skills_enabled: bool,
    process_eval: bool,
    eval_run_mode: str,
    nvflare_skill_eval: str,
    agent: str,
    agent_model: str,
    run_start_time_ns: int,
    workspace_delta_manifest_path: Path,
    input_delta_manifest_path: Path | None = None,
) -> None:
    records_dir.mkdir(parents=True, exist_ok=True)
    copied_evaluator_records = copy_default_evaluator_records(records_dir, nvflare_skill_eval, run_start_time_ns)
    existing_agent_record = load_json(agent_record_path)
    usage = load_json(usage_path, {}) or {}
    activity = load_json(activity_path, {}) or {}
    workspace_delta = load_json(workspace_delta_manifest_path, {}) or {}
    input_delta: dict[str, Any] | None = None
    input_delta_not_captured_reason = "input_delta_manifest was not provided"
    if input_delta_manifest_path is not None:
        loaded_input_delta = load_json(input_delta_manifest_path)
        if isinstance(loaded_input_delta, dict) and loaded_input_delta.get("delta_scope") == "input_snapshot":
            input_delta = loaded_input_delta
        elif isinstance(loaded_input_delta, dict) and loaded_input_delta:
            input_delta_not_captured_reason = (
                f"input_delta_manifest had unexpected delta_scope={loaded_input_delta.get('delta_scope')!r}"
            )
        else:
            input_delta_not_captured_reason = "input_delta_manifest was missing, empty, or unreadable"
    events_text = load_text(events_path)
    last_message = load_text(last_message_path)
    readme_path, readme_text = discover_readme(input_dir)
    event_identity = infer_from_events(events_text)
    readme_metric_signal = metric_signal(readme_path, readme_text, last_message)
    existing_skill = str(record_skill(existing_agent_record) or "") if isinstance(existing_agent_record, dict) else ""
    existing_case = str(record_case(existing_agent_record) or "") if isinstance(existing_agent_record, dict) else ""
    if not valid_identity_token(existing_skill):
        existing_skill = ""
    if not valid_identity_token(existing_case):
        existing_case = ""

    candidates = [
        (path, record)
        for path, record in iter_json_records(records_dir, agent_record_path)
        if nvflare_skill_eval == "on"
        and path_is_current_run(path, run_start_time_ns)
        and record_is_candidate(record)
        and record_skill(record)
        and record_case(record)
    ]
    source_path, source_record, source_audit = choose_source_record(
        candidates,
        expected_skill=existing_skill,
        expected_case=existing_case,
    )

    base: dict[str, Any] = {}
    record_source = "harness_synthesized"
    if isinstance(source_record, dict):
        base = copy.deepcopy(source_record)
        record_source = "nvflare_skill_evaluator_record"
    elif isinstance(existing_agent_record, dict):
        base = copy.deepcopy(existing_agent_record)
        record_source = "existing_mode_agent_record"

    skill = record_skill(base)
    case_id = record_case(base)
    event_skill = event_identity.get("skill") if isinstance(event_identity, dict) else ""
    event_case = event_identity.get("case_id") if isinstance(event_identity, dict) else ""
    if not skill and event_skill:
        skill = event_skill
        event_identity["used_as_fallback"] = True
    if not case_id and event_case:
        case_id = event_case
        event_identity["used_as_fallback"] = True
    if event_identity.get("used_as_fallback"):
        print(
            "warning: process record identity inferred from Codex event text "
            f"(skill={skill or 'unknown'}, case_id={case_id or 'unknown'})",
            file=sys.stderr,
        )

    record = base if isinstance(base, dict) else {}
    metrics = apply_record_runtime_fields(
        record,
        usage=usage,
        mode=mode,
        elapsed_seconds=elapsed_seconds,
        codex_exit=codex_exit,
        skills_enabled=skills_enabled,
        process_eval=process_eval,
        eval_run_mode=eval_run_mode,
        nvflare_skill_eval=nvflare_skill_eval,
        agent=agent,
        agent_model=agent_model,
    )
    record["agent_record_generated_by_harness"] = True
    record["agent_record_source"] = record_source
    if source_path is not None:
        record["agent_record_source_path"] = str(source_path)
    if copied_evaluator_records:
        record["copied_evaluator_record_paths"] = copied_evaluator_records
        record["copied_evaluator_records_cutoff_time_ns"] = run_start_cutoff_ns(run_start_time_ns)
    record["agent_record_source_audit"] = source_audit
    record["event_identity_inference"] = event_identity

    if skill:
        record["skill"] = skill
        record["skill_name"] = skill
    if case_id:
        record["case_id"] = case_id

    discovery = record.get("skill_discovery")
    if not isinstance(discovery, dict):
        discovery = {}
    if skill and not discovery.get("selected_skill"):
        discovery["selected_skill"] = skill
    if case_id and not discovery.get("selected_case_id"):
        discovery["selected_case_id"] = case_id
    if discovery:
        discovery.setdefault(
            "source",
            "harness_explicit_record" if not event_identity.get("used_as_fallback") else "harness_event_log_fallback",
        )
        record["skill_discovery"] = discovery

    evaluation = record.get("evaluation")
    if not isinstance(evaluation, dict):
        evaluation = {}
    if source_record is None:
        evaluation.update(
            {
                "mode": "harness_outcome_proxy",
                "scoring_source": "harness:codex_exit_code",
                "reason": "No NVFLARE skill evaluator record was found for this mode; eval_passed is unavailable and codex_process_passed reflects Codex process exit only.",
            }
        )
    else:
        evaluation.setdefault("mode", "on")
        evaluation.setdefault("scoring_source", "nvflare agent skills evaluate")
    record["evaluation"] = evaluation

    if not isinstance(record.get("eval_passed"), bool):
        record["eval_passed"] = None
        record["eval_passed_source"] = "unavailable"
    else:
        record.setdefault("eval_passed_source", record_source)

    score = record.get("score")
    if score is not None and not isinstance(score, dict):
        score = None
    if score is None:
        score = {
            "value": None,
            "max": 5,
            "rationale": "No evaluator score was available; the harness generated this mode record for reporting continuity.",
        }
    record["score"] = score

    for category in ("mandatory_behavior", "prohibited_behavior", "optional_behavior"):
        if record.get(category) is None:
            record[category] = {}

    metrics["event_count"] = activity.get("event_count")
    metrics["command_count"] = activity.get("command_count")
    metrics["unique_command_count"] = activity.get("unique_command_count")
    if isinstance(workspace_delta, dict):
        record["workspace_delta"] = workspace_delta
        for key in (
            "changed_file_count",
            "deleted_file_count",
            "workspace_added_file_count",
            "workspace_modified_file_count",
            "workspace_deleted_baseline_file_count",
            "workspace_change_count",
            "runtime_artifact_count",
            "copied_file_count",
            "copied_bytes",
        ):
            if isinstance(workspace_delta.get(key), (int, float)) and not isinstance(workspace_delta.get(key), bool):
                metrics[f"workspace_delta_{key}"] = workspace_delta[key]

    if isinstance(input_delta, dict):
        record["source_input_delta"] = input_delta
        input_delta_aliases = {
            "workspace_added_file_count": "added_file_count",
            "workspace_modified_file_count": "modified_file_count",
            "workspace_deleted_baseline_file_count": "deleted_baseline_file_count",
            "workspace_change_count": "change_count",
        }
        for key in (
            "changed_file_count",
            "deleted_file_count",
            "workspace_added_file_count",
            "workspace_modified_file_count",
            "workspace_deleted_baseline_file_count",
            "workspace_change_count",
            "copied_file_count",
            "copied_bytes",
        ):
            if isinstance(input_delta.get(key), (int, float)) and not isinstance(input_delta.get(key), bool):
                metrics[f"source_input_delta_{key}"] = input_delta[key]
                if key in input_delta_aliases:
                    metrics[f"source_input_delta_{input_delta_aliases[key]}"] = input_delta[key]
        source_input_violation = bool(input_delta.get("changed_file_count") or input_delta.get("deleted_file_count"))
        metrics["source_input_immutable_violation"] = 1 if source_input_violation else 0
        record["source_input_immutable_policy"] = {
            "status": "fail" if source_input_violation else "pass",
            "reason": (
                "The immutable input snapshot changed during the agent run."
                if source_input_violation
                else "The immutable input snapshot was unchanged; conversion output is captured separately from the writable workspace."
            ),
            "scope": str(input_delta.get("workspace_root") or ""),
            "changed_files": input_delta.get("changed_files") or [],
            "deleted_files": input_delta.get("deleted_files") or [],
        }
        if source_input_violation:
            record["source_input_immutable_violation"] = {
                "status": "fail",
                "reason": "Agent or runtime changed files inside the immutable input snapshot.",
                "changed_files": input_delta.get("changed_files") or [],
                "deleted_files": input_delta.get("deleted_files") or [],
            }
    else:
        record["source_input_immutable_policy"] = {
            "status": "not_captured",
            "reason": input_delta_not_captured_reason,
            "scope": "",
            "changed_files": [],
            "deleted_files": [],
        }
        metrics["source_input_immutable_violation"] = 0

    quality_signals = record.get("quality_signals")
    if not isinstance(quality_signals, dict):
        quality_signals = {}
    quality_signals["readme_primary_validation_metric"] = readme_metric_signal
    record["quality_signals"] = quality_signals
    if readme_metric_signal.get("expected_primary_metric"):
        record["validation_metric_policy"] = {
            "source": readme_metric_signal.get("source"),
            "expected_primary_metric": readme_metric_signal.get("expected_primary_metric"),
            "scoring_note": "Measured as a quality signal only; evaluator-owned eval_passed is not modified by this harness heuristic.",
        }
        validation_metric = readme_metric_signal.get("reported_validation_metric")
        record["reported_validation_metric"] = validation_metric
        metrics["validation_metric_policy_available"] = 1
        metrics["validation_metric_value_available"] = 1 if readme_metric_signal.get("metric_value_available") else 0
        metrics["validation_metric_aligned_with_readme"] = 1 if readme_metric_signal.get("aligned_with_readme") else 0
        metrics["validation_metric_mismatch"] = 1 if readme_metric_signal.get("mismatch") else 0
    else:
        validation_metric = readme_metric_signal.get("reported_validation_metric")
        if isinstance(validation_metric, dict) and validation_metric.get("name"):
            record["reported_validation_metric"] = validation_metric
        metrics["validation_metric_policy_available"] = 0

    record["process_metrics"] = metrics
    record["agent_usage"] = usage
    record["codex_usage"] = usage

    notes = record.get("notes")
    note = "Mode-specific process record was synthesized by the benchmark harness, not requested through prompt text."
    if isinstance(notes, list):
        if note not in notes:
            notes.append(note)
    elif isinstance(notes, str) and notes:
        record["notes"] = [notes, note] if notes != note else [notes]
    else:
        record["notes"] = [note]

    write_json(agent_record_path, record)


def as_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_behavior_map(record: dict[str, Any], category: str) -> dict[str, dict[str, str]]:
    raw = record.get(category)
    if not isinstance(raw, dict):
        raw = {}
    normalized = {}
    for behavior_id, entry in raw.items():
        if not isinstance(entry, dict):
            entry = {}
        status = entry.get("status")
        if status not in ALLOWED_BEHAVIOR_STATUSES:
            status = "missing"
        normalized[str(behavior_id)] = {
            "status": status,
            "evidence": str(entry.get("evidence") or "No evidence supplied by agent."),
        }
    record[category] = normalized
    return normalized


def status_counts(behavior_map: dict[str, dict[str, str]]) -> dict[str, int]:
    counts = {status: 0 for status in sorted(ALLOWED_BEHAVIOR_STATUSES)}
    for entry in behavior_map.values():
        status = entry.get("status")
        if status in counts:
            counts[status] += 1
    return counts


def pass_rate(behavior_map: dict[str, dict[str, str]]) -> float | None:
    total = len(behavior_map)
    if total == 0:
        return None
    return round(sum(1 for entry in behavior_map.values() if entry.get("status") == "pass") / total, 3)


def merge_record(
    agent_record_path: Path,
    final_record_path: Path,
    usage_path: Path,
    mode: str,
    elapsed_seconds: int,
    codex_exit: int,
    skills_enabled: bool,
    process_eval: bool,
    eval_run_mode: str,
    nvflare_skill_eval: str,
    agent: str,
    agent_model: str,
) -> None:
    record: dict[str, Any] = {}
    agent_record_present = agent_record_path.exists()
    agent_record_valid = False
    if agent_record_present:
        try:
            data = json.loads(agent_record_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                record = data
                agent_record_valid = True
        except Exception as exc:
            record = {"notes": f"agent record was not valid JSON: {exc}"}

    if not isinstance(record, dict):
        record = {"notes": "agent record was not a JSON object"}

    usage = load_json(usage_path, {}) or {}
    metrics = apply_record_runtime_fields(
        record,
        usage=usage,
        mode=mode,
        elapsed_seconds=elapsed_seconds,
        codex_exit=codex_exit,
        skills_enabled=skills_enabled,
        process_eval=process_eval,
        eval_run_mode=eval_run_mode,
        nvflare_skill_eval=nvflare_skill_eval,
        agent=agent,
        agent_model=agent_model,
        agent_record_present=agent_record_present,
        agent_record_valid=agent_record_valid,
    )
    if "user_correction_count" not in metrics and "correction_count" in metrics:
        metrics["user_correction_count"] = metrics.get("correction_count")
    score = record.get("score")
    if not isinstance(score, dict):
        score = {}
        record["score"] = score
    if not isinstance(record.get("eval_passed"), bool):
        record["eval_passed"] = None
    metrics["eval_passed_available"] = 1 if isinstance(record.get("eval_passed"), bool) else 0
    if "first_pass_accepted" not in metrics:
        corrections = as_float(metrics.get("user_correction_count"))
        if corrections is not None and isinstance(record.get("eval_passed"), bool):
            metrics["first_pass_accepted"] = 1 if record["eval_passed"] and corrections == 0 else 0

    mandatory_behavior = normalize_behavior_map(record, "mandatory_behavior")
    prohibited_behavior = normalize_behavior_map(record, "prohibited_behavior")
    optional_behavior = normalize_behavior_map(record, "optional_behavior")
    mandatory_count = len(mandatory_behavior)
    prohibited_count = len(prohibited_behavior)
    required_count = mandatory_count + prohibited_count
    required_pass_count = sum(1 for entry in mandatory_behavior.values() if entry.get("status") == "pass") + sum(
        1 for entry in prohibited_behavior.values() if entry.get("status") == "pass"
    )
    instruction_compliance = {
        "mandatory_behavior": {
            "total": mandatory_count,
            "pass_rate": pass_rate(mandatory_behavior),
            "status_counts": status_counts(mandatory_behavior),
        },
        "prohibited_behavior": {
            "total": prohibited_count,
            "avoidance_rate": pass_rate(prohibited_behavior),
            "status_counts": status_counts(prohibited_behavior),
        },
        "optional_behavior": {
            "total": len(optional_behavior),
            "coverage_rate": pass_rate(optional_behavior),
            "status_counts": status_counts(optional_behavior),
        },
        "required_behavior": {
            "total": required_count,
            "pass_rate": round(required_pass_count / required_count, 3) if required_count else None,
            "pass_count": required_pass_count,
        },
    }
    reported_instruction_compliance = record.get("instruction_compliance")
    if (
        mandatory_behavior
        or prohibited_behavior
        or optional_behavior
        or not isinstance(reported_instruction_compliance, dict)
    ):
        record["instruction_compliance"] = instruction_compliance
    else:
        instruction_compliance = reported_instruction_compliance
    required_behavior = instruction_compliance.get("required_behavior") or {}
    mandatory_behavior_summary = instruction_compliance.get("mandatory_behavior") or {}
    prohibited_behavior_summary = instruction_compliance.get("prohibited_behavior") or {}
    metrics["instruction_required_pass_rate"] = required_behavior.get("pass_rate")
    metrics["instruction_mandatory_pass_rate"] = mandatory_behavior_summary.get("pass_rate")
    metrics["instruction_prohibited_avoidance_rate"] = prohibited_behavior_summary.get("avoidance_rate")
    required_pass_rate = required_behavior.get("pass_rate")
    if required_pass_rate is not None:
        metrics["instruction_required_passed"] = 1 if required_pass_rate >= 1.0 else 0
    record["agent_usage"] = usage
    record["codex_usage"] = usage
    write_json(final_record_path, record)


def write_run_summary(final_record_path: Path, summary_path: Path, *, print_summary: bool = True) -> None:
    record = load_json(final_record_path, {}) or {}
    metrics = record.get("process_metrics") or {}
    score = record.get("score") or {}
    summary = {
        "mode": record.get("mode"),
        "run_mode": record.get("run_mode"),
        "skill": record.get("skill"),
        "skill_name": record.get("skill_name"),
        "case_id": record.get("case_id"),
        "elapsed_seconds": metrics.get("elapsed_seconds"),
        "token_count": metrics.get("token_count"),
        "conversion_quality": metrics.get("conversion_quality"),
        "correction_count": metrics.get("correction_count"),
        "command_failures": metrics.get("command_failures"),
        "score_value": score.get("value"),
        "score_max": score.get("max"),
        "eval_passed": record.get("eval_passed"),
        "codex_process_passed": record.get("codex_process_passed"),
        "codex_process_exit_code": record.get("codex_process_exit_code"),
        "codex_exit_code": metrics.get("codex_exit_code"),
        "agent_report_exit_codes": record.get("agent_report_exit_codes") or {},
        "agent_report_exit_code": record.get("agent_report_exit_code"),
        "agent_report_failed": record.get("agent_report_failed"),
        "final_container_exit_code": record.get("final_container_exit_code"),
        "report_inclusive_exit_code": record.get("report_inclusive_exit_code"),
        "harness_failure": record.get("harness_failure") or metrics.get("harness_failure"),
        "harness_error": record.get("harness_error") or {},
        "harness_errors": record.get("harness_errors") or [],
        "skills_enabled": record.get("skills_enabled"),
        "process_eval_enabled": record.get("process_eval_enabled"),
        "process_evaluator_state": record.get("process_evaluator_state"),
        "process_eval_semantics": record.get("process_eval_semantics"),
        "nvflare_skill_eval": record.get("nvflare_skill_eval"),
        "nvflare_skill_eval_state": record.get("nvflare_skill_eval_state"),
        "agent": record.get("agent"),
        "agent_model": record.get("agent_model"),
        "agent_record_present": record.get("agent_record_present"),
        "agent_record_valid": record.get("agent_record_valid"),
        "evaluator_modes": record.get("evaluator_modes") or {},
        "score": score,
        "process_metrics": metrics,
        "instruction_compliance": record.get("instruction_compliance") or {},
        "mandatory_behavior": record.get("mandatory_behavior") or {},
        "prohibited_behavior": record.get("prohibited_behavior") or {},
        "optional_behavior": record.get("optional_behavior") or {},
        "skill_discovery": record.get("skill_discovery") or {},
        "agent_usage": record.get("agent_usage") or record.get("codex_usage") or {},
        "codex_usage": record.get("codex_usage") or {},
        "workspace_delta": record.get("workspace_delta") or {},
        "source_input_delta": record.get("source_input_delta") or {},
        "source_input_immutable_policy": record.get("source_input_immutable_policy") or {},
    }
    summary["all_metrics"] = flatten_numbers(summary)
    write_json(summary_path, summary)
    if print_summary:
        print(json.dumps(summary, indent=2, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    synth = subparsers.add_parser("synthesize")
    synth.add_argument("agent_record", type=Path)
    synth.add_argument("records_dir", type=Path)
    synth.add_argument("events_path", type=Path)
    synth.add_argument("usage_path", type=Path)
    synth.add_argument("activity_path", type=Path)
    synth.add_argument("last_message_path", type=Path)
    synth.add_argument("input_dir", type=Path)
    synth.add_argument("mode")
    synth.add_argument("elapsed_seconds", type=int)
    synth.add_argument("codex_exit", type=int)
    synth.add_argument("skills_enabled")
    synth.add_argument("process_eval")
    synth.add_argument("eval_run_mode")
    synth.add_argument("nvflare_skill_eval")
    synth.add_argument("agent_model")
    synth.add_argument("run_start_time_ns", type=int)
    synth.add_argument("workspace_delta_manifest", type=Path)
    synth.add_argument("input_delta_manifest", nargs="?", type=Path)
    synth.add_argument("--agent", default=os.environ.get("BENCHMARK_AGENT", "codex"))

    merge = subparsers.add_parser("merge")
    merge.add_argument("agent_record", type=Path)
    merge.add_argument("final_record", type=Path)
    merge.add_argument("usage_path", type=Path)
    merge.add_argument("mode")
    merge.add_argument("elapsed_seconds", type=int)
    merge.add_argument("codex_exit", type=int)
    merge.add_argument("skills_enabled")
    merge.add_argument("process_eval")
    merge.add_argument("eval_run_mode")
    merge.add_argument("nvflare_skill_eval")
    merge.add_argument("agent_model")
    merge.add_argument("--agent", default=os.environ.get("BENCHMARK_AGENT", "codex"))

    summary = subparsers.add_parser("summary")
    summary.add_argument("final_record", type=Path)
    summary.add_argument("summary_path", type=Path)

    report_filter = subparsers.add_parser("report-filter")
    report_filter.add_argument("records_path", type=Path)
    report_filter.add_argument("--json-out", type=Path)

    evaluator = subparsers.add_parser("evaluator-backed")
    evaluator.add_argument("records_path", type=Path)

    report_status = subparsers.add_parser("report-status")
    report_status.add_argument("path", type=Path)
    report_status.add_argument("performance_json_status", type=int)
    report_status.add_argument("performance_text_status", type=int)
    report_status.add_argument("benchmark_status", type=int)
    report_status.add_argument("skipped")
    report_status.add_argument("skip_reason")
    report_status.add_argument("evaluator_backed_record")
    report_status.add_argument("--runner")
    report_status.add_argument("--image")

    finalize = subparsers.add_parser("finalize")
    finalize.add_argument("summary_path", type=Path)
    finalize.add_argument("record_path", type=Path)
    finalize.add_argument("timing_path", type=Path)
    finalize.add_argument("activity_path", type=Path)
    finalize.add_argument("epochs", nargs=14, type=int)

    args = parser.parse_args()
    if args.command == "synthesize":
        synthesize_agent_record(
            args.agent_record,
            args.records_dir,
            args.events_path,
            args.usage_path,
            args.activity_path,
            args.last_message_path,
            args.input_dir,
            args.mode,
            args.elapsed_seconds,
            args.codex_exit,
            bool_from_text(args.skills_enabled),
            bool_from_text(args.process_eval),
            args.eval_run_mode,
            args.nvflare_skill_eval,
            args.agent,
            args.agent_model,
            args.run_start_time_ns,
            args.workspace_delta_manifest,
            args.input_delta_manifest,
        )
    elif args.command == "merge":
        merge_record(
            args.agent_record,
            args.final_record,
            args.usage_path,
            args.mode,
            args.elapsed_seconds,
            args.codex_exit,
            bool_from_text(args.skills_enabled),
            bool_from_text(args.process_eval),
            args.eval_run_mode,
            args.nvflare_skill_eval,
            args.agent,
            args.agent_model,
        )
    elif args.command == "summary":
        write_run_summary(args.final_record, args.summary_path)
    elif args.command == "report-filter":
        result = discover_report_filter(args.records_path)
        if args.json_out:
            write_report_filter(args.json_out, result["skill"], result["case"])
        if result["skill"]:
            print(f"skill={result['skill']}")
        if result["case"]:
            print(f"case={result['case']}")
    elif args.command == "evaluator-backed":
        print("true" if has_evaluator_backed_record(args.records_path) else "false")
    elif args.command == "report-status":
        write_report_status(
            args.path,
            args.performance_json_status,
            args.performance_text_status,
            args.benchmark_status,
            bool_from_text(args.skipped),
            args.skip_reason,
            bool_from_text(args.evaluator_backed_record),
            report_runner=args.runner,
            report_image=args.image,
        )
    elif args.command == "finalize":
        finalize_timing(args.summary_path, args.record_path, args.timing_path, args.activity_path, args.epochs)


if __name__ == "__main__":
    main()
