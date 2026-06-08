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

"""Generate chart-friendly metrics outputs for NVFLARE agent benchmark runs."""

from __future__ import annotations

import argparse
import binascii
import html
import json
import struct
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from harness.artifacts import collect_report_artifacts
from harness.case_metadata import benchmark_case_metadata, first_dict, load_generated_artifact_text
from harness.common import as_number, flatten_numbers, load_json, load_text
from harness.modes import PROCESS_EVAL_RUNS
from harness.quality_signals import canonical_metric_name as quality_canonical_metric_name

BEHAVIOR_CATEGORIES = ("mandatory_behavior", "prohibited_behavior", "optional_behavior")
COUNT_STATUSES = ("pass", "fail", "missing", "not_applicable", "non_scoring_note")
SUMMARY_TEXT_PREVIEW_BYTES = 4096
EXPLICIT_INSTRUCTION_METRIC_NAMES = {
    "missing": (
        "missing_instruction_count",
        "missing_instructions_count",
        "missed_instruction_count",
        "missed_instructions_count",
        "instruction_missing_count",
        "instruction_missing_total",
    ),
    "failed": (
        "failed_instruction_count",
        "failed_instructions_count",
        "instruction_fail_count",
        "instruction_failed_count",
    ),
    "issue": (
        "instruction_issue_count",
        "instruction_issues_count",
        "instruction_violation_count",
        "instruction_violations_count",
    ),
}
BASE_REPORT_METRIC_ALIASES = {
    "codex_usage.total_tokens": "token_count",
    "phase_seconds.agent_runtime": "elapsed_seconds",
    "phase_seconds.skill_performance_report": "phase_seconds.skill_reports",
    "score.value": "score_value",
    "score.max": "score_max",
}
REPORT_METRIC_ALIASES = dict(BASE_REPORT_METRIC_ALIASES)
for _name in EXPLICIT_INSTRUCTION_METRIC_NAMES["missing"]:
    REPORT_METRIC_ALIASES[_name] = "instruction.missing_instruction_count"
for _name in EXPLICIT_INSTRUCTION_METRIC_NAMES["failed"]:
    REPORT_METRIC_ALIASES[_name] = "instruction.failed_instruction_count"
for _name in EXPLICIT_INSTRUCTION_METRIC_NAMES["issue"]:
    REPORT_METRIC_ALIASES[_name] = "instruction.issue_count"


def explicit_instruction_metric(
    summary: dict[str, Any],
    record: dict[str, Any] | None,
    kind: str,
) -> tuple[float | None, str | None]:
    names = EXPLICIT_INSTRUCTION_METRIC_NAMES[kind]
    search_roots = [
        ("summary", summary),
        ("summary.process_metrics", first_dict(summary.get("process_metrics"))),
        ("record", record or {}),
        ("record.process_metrics", first_dict((record or {}).get("process_metrics"))),
    ]
    for root_name, root in search_roots:
        for name in names:
            value = as_number(root.get(name))
            if value is not None:
                return value, f"{root_name}.{name}"
    return None, None


def compliance_source(summary: dict[str, Any], record: dict[str, Any] | None) -> dict[str, Any]:
    return first_dict(summary.get("instruction_compliance"), (record or {}).get("instruction_compliance"))


def behavior_source(summary: dict[str, Any], record: dict[str, Any] | None, category: str) -> dict[str, Any]:
    return first_dict(summary.get(category), (record or {}).get(category))


def count_behavior_statuses(behavior_map: dict[str, Any]) -> dict[str, int]:
    counts = {status: 0 for status in COUNT_STATUSES}
    for entry in behavior_map.values():
        if not isinstance(entry, dict):
            continue
        status = entry.get("status")
        if status in counts:
            counts[status] += 1
    return counts


def behavior_group_stats(
    summary: dict[str, Any],
    record: dict[str, Any] | None,
    category: str,
) -> dict[str, float | int | None]:
    compliance = compliance_source(summary, record)
    group = first_dict(compliance.get(category))
    behavior_map = behavior_source(summary, record, category)
    counts = first_dict(group.get("status_counts"))
    if not counts and behavior_map:
        counts = count_behavior_statuses(behavior_map)

    total = group.get("total")
    if not isinstance(total, (int, float)):
        total = len(behavior_map)
    pass_count = int(counts.get("pass") or 0)
    fail_count = int(counts.get("fail") or 0)
    missing_count = int(counts.get("missing") or 0)
    not_applicable_count = int(counts.get("not_applicable") or 0)
    non_scoring_note_count = int(counts.get("non_scoring_note") or 0)
    applicable = max(0, int(total) - not_applicable_count - non_scoring_note_count)
    pass_rate = group.get("pass_rate")
    if pass_rate is None:
        pass_rate = group.get("avoidance_rate")
    if pass_rate is None:
        pass_rate = group.get("coverage_rate")
    applicable_pass_rate = round(pass_count / applicable, 3) if applicable else None

    return {
        "total": int(total),
        "applicable": applicable,
        "pass_count": pass_count,
        "fail_count": fail_count,
        "missing_count": missing_count,
        "not_applicable_count": not_applicable_count,
        "non_scoring_note_count": non_scoring_note_count,
        "issue_count": fail_count + missing_count,
        "pass_rate": pass_rate,
        "applicable_pass_rate": applicable_pass_rate,
    }


def derived_instruction_metrics(summary: dict[str, Any], record: dict[str, Any] | None) -> dict[str, float]:
    metrics: dict[str, float] = {}
    required_totals = {
        "total": 0,
        "applicable": 0,
        "pass_count": 0,
        "fail_count": 0,
        "missing_count": 0,
        "not_applicable_count": 0,
        "non_scoring_note_count": 0,
        "issue_count": 0,
    }
    for category in BEHAVIOR_CATEGORIES:
        stats = behavior_group_stats(summary, record, category)
        prefix = f"instruction.{category}"
        for key, value in stats.items():
            if isinstance(value, (int, float)):
                metrics[f"{prefix}.{key}"] = float(value)
        if category in ("mandatory_behavior", "prohibited_behavior"):
            for key in required_totals:
                required_totals[key] += int(stats.get(key) or 0)

    required_applicable = required_totals["applicable"]
    required_pass_count = required_totals["pass_count"]
    for key, value in required_totals.items():
        metrics[f"instruction.required_behavior.{key}"] = float(value)
    if required_totals["total"]:
        metrics["instruction.required_behavior.pass_rate"] = round(required_pass_count / required_totals["total"], 3)
    if required_applicable:
        metrics["instruction.required_behavior.applicable_pass_rate"] = round(
            required_pass_count / required_applicable, 3
        )
    explicit_missing, _ = explicit_instruction_metric(summary, record, "missing")
    explicit_failed, _ = explicit_instruction_metric(summary, record, "failed")
    explicit_issue, _ = explicit_instruction_metric(summary, record, "issue")
    metrics["instruction.missing_instruction_count_available"] = 1.0 if explicit_missing is not None else 0.0
    metrics["instruction.failed_instruction_count_available"] = 1.0 if explicit_failed is not None else 0.0
    metrics["instruction.issue_count_available"] = 1.0 if explicit_issue is not None else 0.0
    if explicit_missing is not None:
        metrics["instruction.missing_instruction_count"] = explicit_missing
    if explicit_failed is not None:
        metrics["instruction.failed_instruction_count"] = explicit_failed
    if explicit_issue is not None:
        metrics["instruction.issue_count"] = explicit_issue
    return metrics


def find_record(run_dir: Path, mode: str | None) -> Path | None:
    records_dir = run_dir / "process_eval_runs"
    if not records_dir.is_dir():
        return None
    candidates = []
    if mode:
        candidates.append(records_dir / f"{mode}_record.json")
    candidates.extend(sorted(records_dir.glob("*_record.json")))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def first_existing_path(*paths: Path) -> Path | None:
    for path in paths:
        if path.is_file():
            return path
    return None


def collect_runs(root: Path) -> list[dict[str, Any]]:
    runs = []
    for run_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        summary_path = run_dir / "run_summary.json"
        if not summary_path.is_file():
            continue
        summary = load_json(summary_path) or {}
        mode = summary.get("mode") or run_dir.name
        record_path = find_record(run_dir, mode)
        record = load_json(record_path) if record_path else None
        activity_path = first_existing_path(run_dir / "agent_activity.json", run_dir / "codex_activity.json")
        activity_report = load_json(activity_path) if activity_path else None
        runtime_image_path = run_dir / "runtime_image.json"
        runtime_image = load_json(runtime_image_path) if runtime_image_path.is_file() else None
        workspace_delta_path = run_dir / "workspace_delta_manifest.json"
        workspace_delta = load_json(workspace_delta_path) if workspace_delta_path.is_file() else None
        prompt_path = run_dir / "prompt.txt"
        prompt_metadata_path = run_dir / "prompt_metadata.json"
        last_message_path = first_existing_path(run_dir / "agent_last_message.txt", run_dir / "codex_last_message.txt")
        prompt_metadata = load_json(prompt_metadata_path) if prompt_metadata_path.is_file() else None
        prompt_text = load_text(prompt_path) if prompt_path.is_file() else ""
        last_message_text = load_text(last_message_path) if last_message_path else ""

        metrics = {}
        metrics.update(flatten_numbers(summary))
        if isinstance(runtime_image, dict):
            for key, value in flatten_numbers(runtime_image).items():
                metrics.setdefault(f"runtime_image.{key}", value)
        if isinstance(activity_report, dict):
            for key, value in flatten_numbers(activity_report).items():
                metrics.setdefault(f"activity.{key}", value)
        if isinstance(record, dict):
            for key, value in flatten_numbers(record).items():
                metrics.setdefault(f"record.{key}", value)
        metrics.update(derived_instruction_metrics(summary, record if isinstance(record, dict) else None))

        runs.append(
            {
                "name": run_dir.name,
                "mode": mode,
                "run_mode": summary.get("run_mode") or (record or {}).get("run_mode"),
                "path": str(run_dir),
                "summary_path": str(summary_path),
                "record_path": str(record_path) if record_path else None,
                "activity_path": str(activity_path) if activity_path else None,
                "runtime_image_path": str(runtime_image_path) if runtime_image_path.is_file() else None,
                "prompt_path": str(prompt_path) if prompt_path.is_file() else None,
                "prompt_metadata_path": str(prompt_metadata_path) if prompt_metadata_path.is_file() else None,
                "last_message_path": str(last_message_path) if last_message_path else None,
                "summary": summary,
                "process_record": record,
                "activity_report": activity_report,
                "runtime_image": runtime_image,
                "workspace_delta": workspace_delta,
                "generated_artifact_text": load_generated_artifact_text(run_dir, workspace_delta or {}),
                "prompt_metadata": prompt_metadata,
                "prompt_text": prompt_text,
                "last_message_text": last_message_text,
                "metrics": metrics,
            }
        )
    return runs


def metrics_by_name(runs: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    by_name: dict[str, dict[str, float]] = {}
    for run in runs:
        for metric, value in run["metrics"].items():
            by_name.setdefault(metric, {})[run["name"]] = value
    return dict(sorted(by_name.items()))


def canonical_report_metric_name(name: str) -> str:
    canonical = str(name or "")
    changed = True
    while changed:
        changed = False
        for prefix in ("record.", "process_metrics."):
            if canonical.startswith(prefix):
                canonical = canonical[len(prefix) :]
                changed = True

    return quality_canonical_metric_name(REPORT_METRIC_ALIASES.get(canonical, canonical))


def metric_fingerprint(values: dict[str, float], run_names: list[str]) -> tuple[tuple[str, bool, float | None], ...]:
    return tuple((run_name, run_name in values, values.get(run_name)) for run_name in run_names)


def metric_preference_key(raw_name: str, canonical_name: str) -> tuple[bool, bool, bool, int, int, str]:
    exact_or_suffix = raw_name == canonical_name or raw_name.endswith("." + canonical_name)
    return (
        not exact_or_suffix,
        raw_name.startswith("record."),
        raw_name.startswith("process_metrics.") or raw_name.startswith("record.process_metrics."),
        raw_name.count("."),
        len(raw_name),
        raw_name,
    )


def dedupe_metrics(
    by_name: dict[str, dict[str, float]],
    run_names: list[str],
) -> tuple[dict[str, dict[str, float]], dict[str, list[str]], list[dict[str, Any]]]:
    grouped: dict[str, list[tuple[str, dict[str, float]]]] = {}
    for raw_name, values in by_name.items():
        grouped.setdefault(canonical_report_metric_name(raw_name), []).append((raw_name, values))

    deduped: dict[str, dict[str, float]] = {}
    aliases: dict[str, list[str]] = {}
    audit: list[dict[str, Any]] = []

    for canonical_name, entries in sorted(grouped.items()):
        by_fingerprint: dict[tuple[tuple[str, bool, float | None], ...], list[tuple[str, dict[str, float]]]] = {}
        for raw_name, values in entries:
            by_fingerprint.setdefault(metric_fingerprint(values, run_names), []).append((raw_name, values))

        for index, equivalent_entries in enumerate(by_fingerprint.values()):
            selected_name, selected_values = sorted(
                equivalent_entries,
                key=lambda entry: metric_preference_key(entry[0], canonical_name),
            )[0]
            display_name = canonical_name
            if len(by_fingerprint) > 1:
                display_name = selected_name
            if display_name in deduped:
                original_display_name = display_name
                display_name = f"{display_name}#{index + 1}"
                audit.append(
                    {
                        "plotted_metric": display_name,
                        "canonical_metric": canonical_name,
                        "selected_raw_metric": selected_name,
                        "reason": "display_name_collision_suffix_added",
                        "collided_display_name": original_display_name,
                    }
                )

            deduped[display_name] = selected_values
            alias_names = sorted(raw_name for raw_name, _ in equivalent_entries if raw_name != display_name)
            if alias_names:
                aliases[display_name] = alias_names
                audit.append(
                    {
                        "plotted_metric": display_name,
                        "canonical_metric": canonical_name,
                        "selected_raw_metric": selected_name,
                        "consolidated_raw_metrics": alias_names,
                        "reason": "same canonical metric name and identical per-run values",
                    }
                )

    return dict(sorted(deduped.items())), dict(sorted(aliases.items())), audit


def text_preview_payload(text: Any, limit: int = SUMMARY_TEXT_PREVIEW_BYTES) -> dict[str, Any]:
    value = "" if text is None else str(text)
    encoded = value.encode("utf-8", errors="replace")
    preview_bytes = encoded[:limit]
    return {
        "byte_count": len(encoded),
        "truncated": len(encoded) > limit,
        "preview": preview_bytes.decode("utf-8", errors="replace"),
    }


def compact_instruction_compliance(summary: dict[str, Any]) -> dict[str, Any]:
    compliance = first_dict(summary.get("instruction_compliance"))
    required = first_dict(compliance.get("required_behavior"))
    keep_keys = (
        "total",
        "applicable",
        "pass_count",
        "fail_count",
        "missing_count",
        "issue_count",
        "pass_rate",
        "applicable_pass_rate",
    )
    compact_required = {key: required.get(key) for key in keep_keys if key in required}
    return {"required_behavior": compact_required} if compact_required else {}


def compact_run_summary_payload(
    summary: dict[str, Any],
    record: dict[str, Any] | None = None,
    runtime_image: dict[str, Any] | None = None,
) -> dict[str, Any]:
    keep_keys = (
        "mode",
        "run_mode",
        "agent",
        "agent_model",
        "skill",
        "skill_name",
        "case_id",
        "eval_passed",
        "codex_process_passed",
        "codex_exit_code",
        "agent_report_exit_code",
        "final_container_exit_code",
        "report_inclusive_exit_code",
        "elapsed_seconds",
        "token_count",
        "score",
        "process_eval_enabled",
        "nvflare_skill_eval_state",
        "reported_validation_metric",
        "validation_metric_policy",
        "harness_error",
    )
    compact = {key: summary.get(key) for key in keep_keys if key in summary}
    record = record or {}
    runtime_image = runtime_image or {}
    compact["agent"] = compact.get("agent") or record.get("agent") or runtime_image.get("agent") or "unknown"
    compact["agent_model"] = (
        compact.get("agent_model")
        or record.get("agent_model")
        or runtime_image.get("agent_model")
        or runtime_image.get("codex_model")
        or "unknown"
    )
    compliance = compact_instruction_compliance(summary)
    if compliance:
        compact["instruction_compliance"] = compliance
    return compact


def compact_run_payload(run: dict[str, Any]) -> dict[str, Any]:
    summary = first_dict(run.get("summary"))
    record = first_dict(run.get("process_record"))
    activity = first_dict(run.get("activity_report"))
    runtime_image = first_dict(run.get("runtime_image"))
    workspace_delta = first_dict(run.get("workspace_delta"))
    return {
        "name": run.get("name"),
        "mode": run.get("mode"),
        "run_mode": run.get("run_mode"),
        "path": run.get("path"),
        "summary_path": run.get("summary_path"),
        "record_path": run.get("record_path"),
        "activity_path": run.get("activity_path"),
        "runtime_image_path": run.get("runtime_image_path"),
        "metric_count": len(run.get("metrics") or {}),
        "summary": compact_run_summary_payload(summary, record, runtime_image),
        "activity_summary": {
            key: activity.get(key)
            for key in ("event_count", "command_count", "unique_command_count", "usage_objects_seen")
            if key in activity
        },
        "workspace_delta_summary": {
            key: workspace_delta.get(key)
            for key in ("changed_file_count", "runtime_artifact_count", "captured_file_count", "total_bytes")
            if key in workspace_delta
        },
        "text_previews": {
            "prompt_text": text_preview_payload(run.get("prompt_text")),
            "last_message_text": text_preview_payload(run.get("last_message_text")),
            "generated_artifact_text": text_preview_payload(run.get("generated_artifact_text")),
        },
    }


def bool_from_any(value: Any) -> bool | None:
    # Report inputs can come from JSON booleans, env-string metadata, or older
    # numeric flags; keep this parser permissive for artifact compatibility.
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on", "enabled"}:
            return True
        if normalized in {"false", "0", "no", "off", "disabled", ""}:
            return False
    return None


def state_label(value: bool | None) -> str:
    if value is True:
        return "on"
    if value is False:
        return "off"
    return "unknown"


def infer_process_eval_enabled(run: dict[str, Any]) -> bool | None:
    summary = run.get("summary") or {}
    record = run.get("process_record") if isinstance(run.get("process_record"), dict) else {}
    runtime_image = run.get("runtime_image") if isinstance(run.get("runtime_image"), dict) else {}
    evaluator_modes = first_dict(summary.get("evaluator_modes"), record.get("evaluator_modes"))
    candidates = [
        summary.get("process_eval_enabled"),
        record.get("process_eval_enabled"),
        runtime_image.get("process_eval"),
        evaluator_modes.get("process_eval"),
        first_dict(summary.get("process_metrics")).get("process_eval_enabled"),
        first_dict(record.get("process_metrics")).get("process_eval_enabled"),
    ]
    for candidate in candidates:
        parsed = bool_from_any(candidate)
        if parsed is not None:
            return parsed
    name = str(run.get("name") or "")
    if name.endswith("_eval_on"):
        return True
    if name.endswith("_eval_off"):
        return False
    return None


def infer_skills_enabled(run: dict[str, Any]) -> bool | None:
    summary = run.get("summary") or {}
    record = run.get("process_record") if isinstance(run.get("process_record"), dict) else {}
    runtime_image = run.get("runtime_image") if isinstance(run.get("runtime_image"), dict) else {}
    for candidate in (
        summary.get("skills_enabled"),
        record.get("skills_enabled"),
        runtime_image.get("use_preinstalled_skills"),
    ):
        parsed = bool_from_any(candidate)
        if parsed is not None:
            return parsed
    name = str(run.get("name") or "")
    mode = str(run.get("mode") or summary.get("mode") or "")
    if name.startswith("with_skills") or mode.startswith("with_skills"):
        return True
    if name.startswith("without_skills") or mode.startswith("without_skills"):
        return False
    return None


def infer_nvflare_skill_eval_state(run: dict[str, Any]) -> str:
    summary = run.get("summary") or {}
    record = run.get("process_record") if isinstance(run.get("process_record"), dict) else {}
    runtime_image = run.get("runtime_image") if isinstance(run.get("runtime_image"), dict) else {}
    evaluator_modes = first_dict(summary.get("evaluator_modes"), record.get("evaluator_modes"))
    state = (
        summary.get("nvflare_skill_eval_state")
        or record.get("nvflare_skill_eval_state")
        or runtime_image.get("nvflare_skill_eval_state")
        or evaluator_modes.get("nvflare_skill_eval")
    )
    if isinstance(state, str) and state.strip():
        return state.strip().lower()
    for value in (
        summary.get("nvflare_skill_eval"),
        record.get("nvflare_skill_eval"),
        runtime_image.get("nvflare_skill_eval"),
    ):
        if isinstance(value, str):
            return "on" if value.strip().lower() == "on" else "off"
    name = str(run.get("name") or "")
    if name.endswith("_eval_on"):
        return "on"
    if name.endswith("_eval_off"):
        return "off"
    return "unknown"


def evaluation_mode_rows(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for run in runs:
        summary = run.get("summary") or {}
        record = run.get("process_record") if isinstance(run.get("process_record"), dict) else {}
        process_eval = infer_process_eval_enabled(run)
        skills_enabled = infer_skills_enabled(run)
        rows.append(
            {
                "run": run["name"],
                "mode": summary.get("mode") or run.get("mode"),
                "run_mode": summary.get("run_mode") or run.get("run_mode"),
                "skills": (
                    "with_skills"
                    if skills_enabled is True
                    else "without_skills" if skills_enabled is False else "unknown"
                ),
                "process_eval": state_label(process_eval),
                "nvflare_skill_eval": infer_nvflare_skill_eval_state(run),
                "skill": summary.get("skill")
                or summary.get("skill_name")
                or record.get("skill")
                or record.get("skill_name"),
                "case_id": summary.get("case_id") or record.get("case_id"),
                "record": "present" if run.get("record_path") else "missing",
            }
        )
    return rows


def process_eval_ablation_case_rows(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    expected_cases = [
        (
            spec.mode,
            spec.skills_enabled,
            spec.process_eval_enabled,
            spec.nvflare_skill_eval_state,
        )
        for spec in PROCESS_EVAL_RUNS
    ]
    exact_by_name = {run["name"]: run for run in runs}
    rows = []
    for case_name, expected_skills, expected_process_eval, expected_skill_eval in expected_cases:
        exact_match = exact_by_name.get(case_name)
        matched = None
        ambiguous_matches: list[dict[str, Any]] = []
        if (
            exact_match is not None
            and infer_skills_enabled(exact_match) is expected_skills
            and infer_process_eval_enabled(exact_match) is expected_process_eval
            and infer_nvflare_skill_eval_state(exact_match) == expected_skill_eval
        ):
            matched = exact_match
        else:
            matches = [
                run
                for run in runs
                if infer_skills_enabled(run) is expected_skills
                and infer_process_eval_enabled(run) is expected_process_eval
                and infer_nvflare_skill_eval_state(run) == expected_skill_eval
            ]
            if len(matches) == 1:
                matched = matches[0]
            elif len(matches) > 1:
                ambiguous_matches = matches
        status = "present" if matched else "ambiguous" if ambiguous_matches else "missing"
        rows.append(
            {
                "expected_case": case_name,
                "expected_skills": "with_skills" if expected_skills else "without_skills",
                "expected_process_eval": state_label(expected_process_eval),
                "expected_nvflare_skill_eval": expected_skill_eval,
                "status": status,
                "observed_run": matched["name"] if matched else None,
                "observed_candidates": (
                    ", ".join(run["name"] for run in ambiguous_matches) if ambiguous_matches else None
                ),
                "observed_process_eval": state_label(infer_process_eval_enabled(matched)) if matched else None,
                "observed_nvflare_skill_eval": infer_nvflare_skill_eval_state(matched) if matched else None,
            }
        )
    return rows


def instruction_summary_rows(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for run in runs:
        summary = run.get("summary") or {}
        record = run.get("process_record") if isinstance(run.get("process_record"), dict) else None
        for category in BEHAVIOR_CATEGORIES:
            stats = behavior_group_stats(summary, record, category)
            rows.append({"run": run["name"], "category": category, **stats})

        required_metrics = derived_instruction_metrics(summary, record)
        rows.append(
            {
                "run": run["name"],
                "category": "required_behavior",
                "total": int(required_metrics.get("instruction.required_behavior.total", 0)),
                "applicable": int(required_metrics.get("instruction.required_behavior.applicable", 0)),
                "pass_count": int(required_metrics.get("instruction.required_behavior.pass_count", 0)),
                "fail_count": int(required_metrics.get("instruction.required_behavior.fail_count", 0)),
                "missing_count": int(required_metrics.get("instruction.required_behavior.missing_count", 0)),
                "not_applicable_count": int(
                    required_metrics.get("instruction.required_behavior.not_applicable_count", 0)
                ),
                "non_scoring_note_count": int(
                    required_metrics.get("instruction.required_behavior.non_scoring_note_count", 0)
                ),
                "issue_count": int(required_metrics.get("instruction.required_behavior.issue_count", 0)),
                "pass_rate": required_metrics.get("instruction.required_behavior.pass_rate"),
                "applicable_pass_rate": required_metrics.get("instruction.required_behavior.applicable_pass_rate"),
            }
        )
    return rows


def instruction_issue_metric_rows(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for run in runs:
        summary = run.get("summary") or {}
        record = run.get("process_record") if isinstance(run.get("process_record"), dict) else None
        row: dict[str, Any] = {"run": run["name"]}
        required_totals = {"pass_count": 0, "applicable": 0, "fail_count": 0, "missing_count": 0, "issue_count": 0}

        for category in BEHAVIOR_CATEGORIES:
            stats = behavior_group_stats(summary, record, category)
            prefix = category.removesuffix("_behavior")
            row[f"{prefix}_pass_count"] = stats.get("pass_count")
            row[f"{prefix}_applicable"] = stats.get("applicable")
            row[f"{prefix}_fail_count"] = stats.get("fail_count")
            row[f"{prefix}_missing_count"] = stats.get("missing_count")
            row[f"{prefix}_issue_count"] = stats.get("issue_count")
            row[f"{prefix}_applicable_pass_rate"] = stats.get("applicable_pass_rate")
            if category in ("mandatory_behavior", "prohibited_behavior"):
                for key in required_totals:
                    required_totals[key] += int(stats.get(key) or 0)

        row["required_pass_count"] = required_totals["pass_count"]
        row["required_applicable"] = required_totals["applicable"]
        row["required_fail_count"] = required_totals["fail_count"]
        row["required_missing_count"] = required_totals["missing_count"]
        row["required_issue_count"] = required_totals["issue_count"]
        row["required_applicable_pass_rate"] = (
            round(required_totals["pass_count"] / required_totals["applicable"], 3)
            if required_totals["applicable"]
            else None
        )
        explicit_missing, explicit_missing_source = explicit_instruction_metric(summary, record, "missing")
        explicit_failed, explicit_failed_source = explicit_instruction_metric(summary, record, "failed")
        explicit_issue, explicit_issue_source = explicit_instruction_metric(summary, record, "issue")
        row["missing_instruction_count"] = explicit_missing
        row["failed_instruction_count"] = explicit_failed
        row["instruction_issue_count"] = explicit_issue
        row["missing_instruction_count_source"] = explicit_missing_source or "unable_to_measure"
        row["failed_instruction_count_source"] = explicit_failed_source or "unable_to_measure"
        row["instruction_issue_count_source"] = explicit_issue_source or "unable_to_measure"
        measured = sum(1 for value in (explicit_missing, explicit_failed, explicit_issue) if value is not None)
        row["instruction_metric_status"] = (
            "measured" if measured == 3 else "partially_measured" if measured else "unable_to_measure"
        )
        rows.append(row)
    return rows


def instruction_detail_rows(runs: list[dict[str, Any]], statuses: set[str]) -> list[dict[str, Any]]:
    rows = []
    for run in runs:
        summary = run.get("summary") or {}
        record = run.get("process_record") if isinstance(run.get("process_record"), dict) else None
        for category in BEHAVIOR_CATEGORIES:
            behavior_map = behavior_source(summary, record, category)
            for behavior_id, entry in sorted(behavior_map.items()):
                if not isinstance(entry, dict):
                    entry = {}
                status = str(entry.get("status") or "missing")
                if status not in statuses:
                    continue
                rows.append(
                    {
                        "run": run["name"],
                        "category": category,
                        "behavior_id": behavior_id,
                        "status": status,
                        "evidence": entry.get("evidence") or "",
                    }
                )
    return rows


def analysis_summary(runs: list[dict[str, Any]], limit: int = 10) -> dict[str, Any]:
    event_totals: dict[str, float] = {}
    top_events_by_run = []
    phase_time_by_run = []
    token_spend_by_run = []

    for run in runs:
        run_summary = run.get("summary") or {}
        run_name = run["name"]

        activity = first_dict(
            run.get("activity_report"),
            run_summary.get("activity"),
            first_dict(run_summary.get("process_metrics")).get("activity"),
        )
        event_types = first_dict(activity.get("event_types"))
        for event_type, count in event_types.items():
            if isinstance(count, (int, float)):
                event_totals[str(event_type)] = event_totals.get(str(event_type), 0.0) + float(count)
        for event_type, count in sorted(event_types.items(), key=lambda item: float(item[1] or 0), reverse=True)[
            :limit
        ]:
            if isinstance(count, (int, float)):
                top_events_by_run.append({"run": run_name, "event_type": event_type, "count": count})

        phases = first_dict(run_summary.get("phase_seconds"))
        total = phases.get("total_container")
        if not isinstance(total, (int, float)):
            total = run_summary.get("elapsed_seconds")
        phase_rows_for_run: dict[str, dict[str, Any]] = {}
        for phase, seconds in sorted(phases.items(), key=lambda item: float(item[1] or 0), reverse=True):
            if not isinstance(seconds, (int, float)):
                continue
            if phase == "total_container":
                continue
            display_phase = "skill_reports" if phase == "skill_performance_report" else phase
            existing = phase_rows_for_run.get(display_phase)
            if existing and float(existing["seconds"] or 0) >= float(seconds):
                continue
            phase_rows_for_run[display_phase] = {
                "run": run_name,
                "phase": display_phase,
                "seconds": seconds,
                "percent_of_container": (
                    round(seconds / total, 3) if isinstance(total, (int, float)) and total else None
                ),
            }
        phase_time_by_run.extend(phase_rows_for_run.values())

        usage = first_dict(run_summary.get("agent_usage"), run_summary.get("codex_usage"))
        token_spend_by_run.append(
            {
                "run": run_name,
                "total_tokens": run_summary.get("token_count") or usage.get("total_tokens"),
                "max_input_tokens": usage.get("max_input_tokens"),
                "max_output_tokens": usage.get("max_output_tokens"),
                "usage_objects_seen": usage.get("usage_objects_seen"),
            }
        )

    top_events_overall = [
        {"event_type": event_type, "count": count}
        for event_type, count in sorted(event_totals.items(), key=lambda item: item[1], reverse=True)[:limit]
    ]
    top_time_spend = sorted(phase_time_by_run, key=lambda row: float(row["seconds"] or 0), reverse=True)[:limit]
    top_token_spend = sorted(
        token_spend_by_run,
        key=lambda row: float(row["total_tokens"] or 0),
        reverse=True,
    )

    return {
        "top_events_overall": top_events_overall,
        "top_events_by_run": top_events_by_run,
        "phase_time_by_run": phase_time_by_run,
        "top_time_spend": top_time_spend,
        "token_spend_by_run": token_spend_by_run,
        "top_token_spend": top_token_spend,
    }


def load_skill_performance(root: Path) -> Any:
    path = root / "skill_performance.json"
    if not path.is_file():
        return {"available": False}
    payload = load_json(path)
    try:
        size_bytes = path.stat().st_size
    except OSError:
        size_bytes = None
    summary: dict[str, Any] = {
        "available": True,
        "path": str(path),
        "size_bytes": size_bytes,
        "payload_type": type(payload).__name__,
        "bounded": True,
    }
    if isinstance(payload, dict):
        scalar_fields: dict[str, Any] = {}
        list_fields: dict[str, int] = {}
        dict_fields: dict[str, int] = {}
        for key, value in list(payload.items())[:50]:
            if isinstance(value, (str, int, float, bool)) or value is None:
                scalar_fields[str(key)] = truncate_text(str(value), 240) if isinstance(value, str) else value
            elif isinstance(value, list):
                list_fields[str(key)] = len(value)
            elif isinstance(value, dict):
                dict_fields[str(key)] = len(value)
        summary["top_level_keys"] = list(payload)[:50]
        if scalar_fields:
            summary["scalar_fields"] = scalar_fields
        if list_fields:
            summary["list_field_counts"] = list_fields
        if dict_fields:
            summary["dict_field_counts"] = dict_fields
    elif isinstance(payload, list):
        summary["item_count"] = len(payload)
    else:
        summary["scalar_value"] = truncate_text(str(payload), 240)
    return summary


def write_metrics_summary(root: Path, title: str, runs: list[dict[str, Any]]) -> dict[str, Any]:
    by_name = metrics_by_name(runs)
    run_names = [run["name"] for run in runs]
    plot_metrics, metric_aliases, metric_dedupe_audit = dedupe_metrics(by_name, run_names)
    eval_rows = evaluation_mode_rows(runs)
    ablation_rows = process_eval_ablation_case_rows(runs)
    metadata_rows = [benchmark_case_metadata(run) for run in runs]
    summary = {
        "title": title,
        "result_root": str(root),
        "runs": [compact_run_payload(run) for run in runs],
        "run_payload_policy": {
            "bounded": True,
            "text_preview_bytes": SUMMARY_TEXT_PREVIEW_BYTES,
            "excluded_full_fields": [
                "prompt_text",
                "last_message_text",
                "generated_artifact_text",
                "process_record",
                "activity_report",
                "runtime_image",
                "workspace_delta",
                "prompt_metadata",
                "metrics",
            ],
            "note": "Full run artifacts remain available as files and through bounded comprehensive artifact capture.",
        },
        "case_metadata_rows": metadata_rows,
        "metric_names": list(by_name),
        "metrics_by_name": by_name,
        "raw_metric_count": len(by_name),
        "plot_metric_names": list(plot_metrics),
        "plot_metrics_by_name": plot_metrics,
        "plot_metric_count": len(plot_metrics),
        "metric_aliases": metric_aliases,
        "metric_dedupe_audit": metric_dedupe_audit,
        "evaluation_mode_rows": eval_rows,
        "process_eval_ablation_case_rows": ablation_rows,
        "process_eval_ablation_complete": all(row["status"] == "present" for row in ablation_rows),
        "instruction_summary_rows": instruction_summary_rows(runs),
        "instruction_issue_metric_rows": instruction_issue_metric_rows(runs),
        "instruction_issue_rows": instruction_detail_rows(runs, {"fail", "missing"}),
        "instruction_non_pass_note_rows": instruction_detail_rows(runs, {"not_applicable", "non_scoring_note"}),
        "analysis_summary": analysis_summary(runs),
        "skill_performance": load_skill_performance(root),
    }
    (root / "metrics_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return summary


def fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return f"{value:.3f}".rstrip("0").rstrip(".")
    return str(value)


def bar_html(value: float, max_abs: float) -> str:
    width = 0 if max_abs == 0 else min(100, abs(value) / max_abs * 100)
    css_class = "bar positive" if value >= 0 else "bar negative"
    return (
        f'<div class="bar-track"><div class="{css_class}" style="width:{width:.2f}%"></div></div>'
        f'<span class="value">{html.escape(fmt(value))}</span>'
    )


def metric_chart(metric: str, values: dict[str, float]) -> str:
    max_abs = max((abs(value) for value in values.values()), default=0)
    rows = []
    for run_name, value in sorted(values.items()):
        rows.append("<tr>" f"<th>{html.escape(run_name)}</th>" f"<td>{bar_html(value, max_abs)}</td>" "</tr>")
    return (
        '<details class="metric" open>'
        f"<summary>{html.escape(metric)}</summary>"
        "<table>" + "".join(rows) + "</table></details>"
    )


def plot_metrics(summary: dict[str, Any]) -> dict[str, dict[str, float]]:
    metrics = summary.get("plot_metrics_by_name")
    if isinstance(metrics, dict):
        return metrics
    return summary["metrics_by_name"]


def plot_values_for_images(summary: dict[str, Any]) -> tuple[dict[str, dict[str, float]], str]:
    return plot_metrics(summary), "Per-run numeric values; bars are scaled independently within each metric."


def alias_table(summary: dict[str, Any]) -> str:
    aliases = summary.get("metric_aliases") or {}
    if not aliases:
        return '<p class="meta">No duplicate metric aliases were consolidated.</p>'
    body = []
    for metric, alias_names in aliases.items():
        body.append(
            "<tr>"
            f"<td>{html.escape(str(metric))}</td>"
            f"<td>{html.escape(', '.join(str(name) for name in alias_names))}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr><th>Plotted Metric</th><th>Consolidated Raw Metrics</th></tr></thead><tbody>"
        + "".join(body)
        + "</tbody></table>"
    )


def instruction_summary_table(rows: list[dict[str, Any]]) -> str:
    body = []
    for row in rows:
        body.append(
            "<tr>"
            f"<td>{html.escape(str(row['run']))}</td>"
            f"<td>{html.escape(str(row['category']))}</td>"
            f"<td>{html.escape(fmt(row.get('total')))}</td>"
            f"<td>{html.escape(fmt(row.get('applicable')))}</td>"
            f"<td>{html.escape(fmt(row.get('pass_count')))}</td>"
            f"<td>{html.escape(fmt(row.get('fail_count')))}</td>"
            f"<td>{html.escape(fmt(row.get('missing_count')))}</td>"
            f"<td>{html.escape(fmt(row.get('issue_count')))}</td>"
            f"<td>{html.escape(fmt(row.get('not_applicable_count')))}</td>"
            f"<td>{html.escape(fmt(row.get('pass_rate')))}</td>"
            f"<td>{html.escape(fmt(row.get('applicable_pass_rate')))}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr><th>Run</th><th>Behavior Group</th><th>Total</th><th>Applicable</th>"
        "<th>Pass</th><th>Fail</th><th>Missing</th><th>Issues</th><th>N/A</th>"
        "<th>Raw Pass Rate</th><th>Applicable Pass Rate</th></tr></thead><tbody>" + "".join(body) + "</tbody></table>"
    )


def instruction_issue_metrics_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return '<p class="meta">No instruction issue metrics were recorded.</p>'
    body = []
    for row in rows:
        metric_sources = "; ".join(
            [
                f"missing={row.get('missing_instruction_count_source')}",
                f"failed={row.get('failed_instruction_count_source')}",
                f"issue={row.get('instruction_issue_count_source')}",
            ]
        )
        body.append(
            "<tr>"
            f"<td>{html.escape(str(row['run']))}</td>"
            f"<td>{html.escape(fmt(row.get('missing_instruction_count')))}</td>"
            f"<td>{html.escape(fmt(row.get('failed_instruction_count')))}</td>"
            f"<td>{html.escape(fmt(row.get('instruction_issue_count')))}</td>"
            f"<td>{html.escape(str(row.get('instruction_metric_status') or ''))}</td>"
            f"<td>{html.escape(metric_sources)}</td>"
            f"<td>{html.escape(fmt(row.get('required_applicable')))}</td>"
            f"<td>{html.escape(fmt(row.get('required_pass_count')))}</td>"
            f"<td>{html.escape(fmt(row.get('required_fail_count')))}</td>"
            f"<td>{html.escape(fmt(row.get('required_missing_count')))}</td>"
            f"<td>{html.escape(fmt(row.get('required_issue_count')))}</td>"
            f"<td>{html.escape(fmt(row.get('required_applicable_pass_rate')))}</td>"
            f"<td>{html.escape(fmt(row.get('mandatory_issue_count')))}</td>"
            f"<td>{html.escape(fmt(row.get('prohibited_issue_count')))}</td>"
            f"<td>{html.escape(fmt(row.get('optional_issue_count')))}</td>"
            "</tr>"
        )
    return (
        '<p class="meta">Missing/failed/issue instruction counts are only measured when the evaluator '
        "or skill emits explicit metrics. n/a means unable to measure. Required fail/missing/issue columns "
        "are best-effort post-analysis from behavior statuses.</p>"
        "<table><thead><tr><th>Run</th><th>Missing Instruction Count</th>"
        "<th>Failed Instruction Count</th><th>Instruction Issue Count</th><th>Measurement Status</th>"
        "<th>Metric Sources</th>"
        "<th>Required Applicable</th><th>Required Pass</th>"
        "<th>Best-Effort Required Fail</th><th>Best-Effort Required Missing</th><th>Best-Effort Required Issues</th>"
        "<th>Required Applicable Pass Rate</th><th>Mandatory Issues</th>"
        "<th>Prohibited Issues</th><th>Optional Issues</th></tr></thead><tbody>" + "".join(body) + "</tbody></table>"
    )


def instruction_detail_table(rows: list[dict[str, Any]], empty_message: str) -> str:
    if not rows:
        return f'<p class="meta">{html.escape(empty_message)}</p>'
    body = []
    for row in rows:
        body.append(
            "<tr>"
            f"<td>{html.escape(str(row['run']))}</td>"
            f"<td>{html.escape(str(row['category']))}</td>"
            f"<td>{html.escape(str(row['behavior_id']))}</td>"
            f"<td>{html.escape(str(row['status']))}</td>"
            f"<td>{html.escape(str(row['evidence']))}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr><th>Run</th><th>Behavior Group</th><th>Instruction</th>"
        "<th>Status</th><th>Evidence</th></tr></thead><tbody>" + "".join(body) + "</tbody></table>"
    )


def analysis_table(rows: list[dict[str, Any]], columns: list[tuple[str, str]], empty_message: str) -> str:
    if not rows:
        return f'<p class="meta">{html.escape(empty_message)}</p>'
    header = "".join(f"<th>{html.escape(label)}</th>" for key, label in columns)
    body = []
    for row in rows:
        body.append("<tr>" + "".join(f"<td>{html.escape(fmt(row.get(key)))}</td>" for key, label in columns) + "</tr>")
    return f"<table><thead><tr>{header}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def analysis_sections_html(summary: dict[str, Any]) -> str:
    analysis = summary.get("analysis_summary") or {}
    return f"""
<section>
<h2>Summary Analysis</h2>
<h3>Token Spend By Run</h3>
{analysis_table(
    analysis.get("top_token_spend") or [],
    [
        ("run", "Run"),
        ("total_tokens", "Total Tokens"),
        ("max_input_tokens", "Max Input Tokens"),
        ("max_output_tokens", "Max Output Tokens"),
        ("usage_objects_seen", "Usage Objects"),
    ],
    "No token usage was recorded.",
)}
<h3>Most Time Spent</h3>
{analysis_table(
    analysis.get("top_time_spend") or [],
    [
        ("run", "Run"),
        ("phase", "Phase"),
        ("seconds", "Seconds"),
        ("percent_of_container", "Container Share"),
    ],
    "No phase timing was recorded.",
)}
<h3>Most Frequent Events</h3>
{analysis_table(
    analysis.get("top_events_overall") or [],
    [("event_type", "Event Type"), ("count", "Count")],
    "No Codex event counts were recorded.",
)}
</section>
"""


def evaluation_modes_table(rows: list[dict[str, Any]]) -> str:
    return analysis_table(
        rows,
        [
            ("run", "Run"),
            ("mode", "Mode"),
            ("skills", "Skills"),
            ("process_eval", "Harness Process Flag"),
            ("nvflare_skill_eval", "NVFLARE Skill Eval"),
            ("run_mode", "Run Mode"),
            ("skill", "Skill"),
            ("case_id", "Case"),
            ("record", "Record"),
        ],
        "No evaluation mode rows were found.",
    )


def case_metadata_table(rows: list[dict[str, Any]]) -> str:
    return analysis_table(
        rows,
        [
            ("run", "Run"),
            ("agent", "Agent"),
            ("clients", "Clients"),
            ("algorithm", "Algorithm"),
            ("rounds", "Rounds"),
            ("job_name", "Job Name"),
            ("agent_model", "Agent Model"),
        ],
        "No benchmark case metadata was found.",
    )


def process_eval_ablation_table(summary: dict[str, Any]) -> str:
    rows = summary.get("process_eval_ablation_case_rows") or []
    status = "complete" if summary.get("process_eval_ablation_complete") else "incomplete"
    return (
        f'<p class="meta">Skill-eval ablation matrix: {html.escape(status)}. '
        "A complete ablation has one no-skills baseline plus skills-enabled NVFLARE skill-eval off/on runs. "
        "The process flag is retained as harness metadata; NVFLARE Skill Eval is the behavior switch.</p>"
        + analysis_table(
            rows,
            [
                ("expected_case", "Expected Case"),
                ("expected_skills", "Expected Skills"),
                ("expected_process_eval", "Expected Harness Process Flag"),
                ("expected_nvflare_skill_eval", "Expected NVFLARE Skill Eval"),
                ("status", "Status"),
                ("observed_run", "Observed Run"),
                ("observed_candidates", "Observed Candidates"),
                ("observed_process_eval", "Observed Harness Process Flag"),
                ("observed_nvflare_skill_eval", "Observed NVFLARE Skill Eval"),
            ],
            "No skill-eval ablation matrix was generated.",
        )
    )


def write_html_report(root: Path, summary: dict[str, Any]) -> None:
    visible_metrics = plot_metrics(summary)
    charts = "\n".join(metric_chart(metric, values) for metric, values in visible_metrics.items())
    run_links = "\n".join(
        f'<li><a href="{html.escape(run["name"])}/run_summary.json">{html.escape(run["name"])}</a></li>'
        for run in summary["runs"]
    )
    content = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{html.escape(summary["title"])}</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 24px; color: #1f2937; }}
h1, h2 {{ margin: 0 0 12px; }}
section {{ margin: 24px 0; }}
table {{ border-collapse: collapse; width: 100%; margin: 8px 0 16px; }}
th, td {{ border-bottom: 1px solid #e5e7eb; padding: 6px 8px; text-align: left; vertical-align: middle; }}
th {{ width: 240px; font-weight: 600; }}
details.metric {{ border: 1px solid #e5e7eb; border-radius: 6px; margin: 8px 0; padding: 8px; }}
summary {{ cursor: pointer; font-weight: 600; overflow-wrap: anywhere; }}
.bar-track {{ display: inline-block; width: min(60vw, 560px); height: 14px; background: #f3f4f6; border-radius: 4px; overflow: hidden; vertical-align: middle; }}
.bar {{ height: 100%; }}
.positive {{ background: #2563eb; }}
.negative {{ background: #dc2626; }}
.value {{ display: inline-block; min-width: 80px; margin-left: 10px; font-variant-numeric: tabular-nums; }}
.meta {{ color: #4b5563; }}
</style>
</head>
<body>
<h1>{html.escape(summary["title"])}</h1>
<p class="meta">Result root: {html.escape(summary["result_root"])}</p>
<p class="meta">Plotted metrics: {summary.get("plot_metric_count", len(visible_metrics))} after consolidating {summary.get("raw_metric_count", len(visible_metrics))} raw flattened metrics.</p>
<section>
<h2>Runs</h2>
<ul>{run_links}</ul>
</section>
<section>
<h2>Evaluation Modes</h2>
{evaluation_modes_table(summary.get("evaluation_mode_rows") or [])}
<h3>Process-Eval Ablation Case Matrix</h3>
{process_eval_ablation_table(summary)}
</section>
<section>
<h2>Case Metadata</h2>
{case_metadata_table(summary.get("case_metadata_rows") or [])}
</section>
{analysis_sections_html(summary)}
<section>
<h2>Instruction Compliance Summary</h2>
{instruction_summary_table(summary.get("instruction_summary_rows") or [])}
</section>
<section>
<h2>Instruction Issue Metrics</h2>
{instruction_issue_metrics_table(summary.get("instruction_issue_metric_rows") or [])}
</section>
<section>
<h2>Instruction Misses And Failures</h2>
{instruction_detail_table(summary.get("instruction_issue_rows") or [], "No fail or missing instruction items were recorded.")}
</section>
<section>
<h2>Other Non-Pass Instruction Notes</h2>
{instruction_detail_table(summary.get("instruction_non_pass_note_rows") or [], "No not-applicable or non-scoring instruction notes were recorded.")}
</section>
<section>
<h2>Deduped Numeric Metrics</h2>
{charts}
</section>
<section>
<h2>Consolidated Aliases</h2>
{alias_table(summary)}
</section>
</body>
</html>
"""
    (root / "metrics_report.html").write_text(content, encoding="utf-8")


def markdown_escape(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", "<br>")


def run_table(summary: dict[str, Any]) -> str:
    rows = [
        "| Run | Mode | Agent | Model | Harness Process Flag | NVFLARE Skill Eval | Skill | Case | Evaluator Passed | Process Passed | Score | Elapsed Seconds | Token Count | Required Pass Rate |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | ---: | ---: | ---: |",
    ]
    eval_by_run = {row["run"]: row for row in summary.get("evaluation_mode_rows") or []}
    for run in summary["runs"]:
        run_summary = run.get("summary") or {}
        eval_row = eval_by_run.get(run["name"], {})
        score = run_summary.get("score") or {}
        compliance = run_summary.get("instruction_compliance") or {}
        required = compliance.get("required_behavior") or {}
        rows.append(
            "| "
            + " | ".join(
                [
                    markdown_escape(run["name"]),
                    markdown_escape(run_summary.get("run_mode") or run.get("run_mode") or run.get("mode")),
                    markdown_escape(run_summary.get("agent")),
                    markdown_escape(run_summary.get("agent_model")),
                    markdown_escape(eval_row.get("process_eval")),
                    markdown_escape(eval_row.get("nvflare_skill_eval")),
                    markdown_escape(run_summary.get("skill")),
                    markdown_escape(run_summary.get("case_id")),
                    markdown_escape(run_summary.get("eval_passed")),
                    markdown_escape(run_summary.get("codex_process_passed")),
                    markdown_escape(fmt(score.get("value"))),
                    markdown_escape(fmt(run_summary.get("elapsed_seconds"))),
                    markdown_escape(fmt(run_summary.get("token_count"))),
                    markdown_escape(fmt(required.get("pass_rate"))),
                ]
            )
            + " |"
        )
    return "\n".join(rows)


def evaluation_modes_markdown(summary: dict[str, Any]) -> str:
    mode_table = markdown_table(
        summary.get("evaluation_mode_rows") or [],
        [
            ("run", "Run"),
            ("mode", "Mode"),
            ("skills", "Skills"),
            ("process_eval", "Harness Process Flag"),
            ("nvflare_skill_eval", "NVFLARE Skill Eval"),
            ("run_mode", "Run Mode"),
            ("skill", "Skill"),
            ("case_id", "Case"),
            ("record", "Record"),
        ],
        "No evaluation mode rows were found.",
    )
    status = "complete" if summary.get("process_eval_ablation_complete") else "incomplete"
    ablation_table = markdown_table(
        summary.get("process_eval_ablation_case_rows") or [],
        [
            ("expected_case", "Expected Case"),
            ("expected_skills", "Expected Skills"),
            ("expected_process_eval", "Expected Harness Process Flag"),
            ("expected_nvflare_skill_eval", "Expected NVFLARE Skill Eval"),
            ("status", "Status"),
            ("observed_run", "Observed Run"),
            ("observed_candidates", "Observed Candidates"),
            ("observed_process_eval", "Observed Harness Process Flag"),
            ("observed_nvflare_skill_eval", "Observed NVFLARE Skill Eval"),
        ],
        "No skill-eval ablation matrix was generated.",
    )
    return f"""## Evaluation Modes

{mode_table}

Skill-eval ablation matrix: {status}. A complete ablation has one no-skills baseline plus skills-enabled NVFLARE skill-eval off/on runs. The process flag is retained as harness metadata.

{ablation_table}
"""


def case_metadata_markdown(summary: dict[str, Any]) -> str:
    return markdown_table(
        summary.get("case_metadata_rows") or [],
        [
            ("run", "Run"),
            ("agent", "Agent"),
            ("clients", "Clients"),
            ("algorithm", "Algorithm"),
            ("rounds", "Rounds"),
            ("job_name", "Job Name"),
            ("agent_model", "Agent Model"),
        ],
        "No benchmark case metadata was found.",
    )


def metrics_table(summary: dict[str, Any]) -> str:
    run_names = [run["name"] for run in summary["runs"]]
    rows = ["| Metric | " + " | ".join(markdown_escape(name) for name in run_names) + " |"]
    rows.append("| --- | " + " | ".join("---:" for _ in run_names) + " |")
    for metric, values in plot_metrics(summary).items():
        rows.append(
            "| "
            + markdown_escape(metric)
            + " | "
            + " | ".join(markdown_escape(fmt(values.get(run_name))) for run_name in run_names)
            + " |"
        )
    return "\n".join(rows)


def instruction_summary_markdown(rows: list[dict[str, Any]]) -> str:
    table = [
        "| Run | Behavior Group | Total | Applicable | Pass | Fail | Missing | Issues | N/A | Raw Pass Rate | Applicable Pass Rate |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        table.append(
            "| "
            + " | ".join(
                [
                    markdown_escape(row.get("run")),
                    markdown_escape(row.get("category")),
                    markdown_escape(fmt(row.get("total"))),
                    markdown_escape(fmt(row.get("applicable"))),
                    markdown_escape(fmt(row.get("pass_count"))),
                    markdown_escape(fmt(row.get("fail_count"))),
                    markdown_escape(fmt(row.get("missing_count"))),
                    markdown_escape(fmt(row.get("issue_count"))),
                    markdown_escape(fmt(row.get("not_applicable_count"))),
                    markdown_escape(fmt(row.get("pass_rate"))),
                    markdown_escape(fmt(row.get("applicable_pass_rate"))),
                ]
            )
            + " |"
        )
    return "\n".join(table)


def instruction_details_markdown(rows: list[dict[str, Any]], empty_message: str) -> str:
    if not rows:
        return empty_message
    table = [
        "| Run | Behavior Group | Instruction | Status | Evidence |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        table.append(
            "| "
            + " | ".join(
                [
                    markdown_escape(row.get("run")),
                    markdown_escape(row.get("category")),
                    markdown_escape(row.get("behavior_id")),
                    markdown_escape(row.get("status")),
                    markdown_escape(row.get("evidence")),
                ]
            )
            + " |"
        )
    return "\n".join(table)


def instruction_issue_metrics_markdown(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "No instruction issue metrics were recorded."
    table = [
        "Missing/failed/issue instruction counts are only measured when the evaluator or skill emits explicit metrics. `n/a` means unable to measure. Required fail/missing/issue columns are best-effort post-analysis from behavior statuses.",
        "",
        "| Run | Missing Instruction Count | Failed Instruction Count | Instruction Issue Count | Measurement Status | Metric Sources | Required Applicable | Required Pass | Best-Effort Required Fail | Best-Effort Required Missing | Best-Effort Required Issues | Required Applicable Pass Rate | Mandatory Issues | Prohibited Issues | Optional Issues |",
        "| --- | ---: | ---: | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        metric_sources = "; ".join(
            [
                f"missing={row.get('missing_instruction_count_source')}",
                f"failed={row.get('failed_instruction_count_source')}",
                f"issue={row.get('instruction_issue_count_source')}",
            ]
        )
        table.append(
            "| "
            + " | ".join(
                [
                    markdown_escape(row.get("run")),
                    markdown_escape(fmt(row.get("missing_instruction_count"))),
                    markdown_escape(fmt(row.get("failed_instruction_count"))),
                    markdown_escape(fmt(row.get("instruction_issue_count"))),
                    markdown_escape(row.get("instruction_metric_status")),
                    markdown_escape(metric_sources),
                    markdown_escape(fmt(row.get("required_applicable"))),
                    markdown_escape(fmt(row.get("required_pass_count"))),
                    markdown_escape(fmt(row.get("required_fail_count"))),
                    markdown_escape(fmt(row.get("required_missing_count"))),
                    markdown_escape(fmt(row.get("required_issue_count"))),
                    markdown_escape(fmt(row.get("required_applicable_pass_rate"))),
                    markdown_escape(fmt(row.get("mandatory_issue_count"))),
                    markdown_escape(fmt(row.get("prohibited_issue_count"))),
                    markdown_escape(fmt(row.get("optional_issue_count"))),
                ]
            )
            + " |"
        )
    return "\n".join(table)


def metric_aliases_markdown(summary: dict[str, Any]) -> str:
    aliases = summary.get("metric_aliases") or {}
    if not aliases:
        return "No duplicate metric aliases were consolidated."
    table = [
        "| Plotted Metric | Consolidated Raw Metrics |",
        "| --- | --- |",
    ]
    for metric, alias_names in aliases.items():
        table.append(
            "| "
            + markdown_escape(metric)
            + " | "
            + markdown_escape(", ".join(str(name) for name in alias_names))
            + " |"
        )
    return "\n".join(table)


def markdown_table(rows: list[dict[str, Any]], columns: list[tuple[str, str]], empty_message: str) -> str:
    if not rows:
        return empty_message
    table = [
        "| " + " | ".join(markdown_escape(label) for key, label in columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in rows:
        table.append("| " + " | ".join(markdown_escape(fmt(row.get(key))) for key, label in columns) + " |")
    return "\n".join(table)


def analysis_sections_markdown(summary: dict[str, Any]) -> str:
    analysis = summary.get("analysis_summary") or {}
    token_table = markdown_table(
        analysis.get("top_token_spend") or [],
        [
            ("run", "Run"),
            ("total_tokens", "Total Tokens"),
            ("max_input_tokens", "Max Input Tokens"),
            ("max_output_tokens", "Max Output Tokens"),
            ("usage_objects_seen", "Usage Objects"),
        ],
        "No token usage was recorded.",
    )
    time_table = markdown_table(
        analysis.get("top_time_spend") or [],
        [
            ("run", "Run"),
            ("phase", "Phase"),
            ("seconds", "Seconds"),
            ("percent_of_container", "Container Share"),
        ],
        "No phase timing was recorded.",
    )
    event_table = markdown_table(
        analysis.get("top_events_overall") or [],
        [("event_type", "Event Type"), ("count", "Count")],
        "No Codex event counts were recorded.",
    )
    return f"""## Summary Analysis

### Token Spend By Run

{token_table}

### Most Time Spent

{time_table}

### Most Frequent Events

{event_table}
"""


def write_comprehensive_report(root: Path, summary: dict[str, Any], include_plot_files: bool = False) -> None:
    artifacts = collect_report_artifacts(root)
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    generated_outputs = {
        "metrics_summary_json": str(root / "metrics_summary.json"),
        "metrics_report_html": str(root / "metrics_report.html"),
        "comprehensive_report_json": str(root / "comprehensive_report.json"),
        "comprehensive_report_md": str(root / "comprehensive_report.md"),
    }
    generated_output_lines = [
        "- `metrics_summary.json`: normalized raw metrics plus deduped per-run metrics from every run.",
        "- `metrics_report.html`: browser-friendly deduped metric bars and instruction-following details.",
        "- `comprehensive_report.json`: combined JSON/text/log artifact content.",
        "- `comprehensive_report.md`: this readable report.",
    ]
    if include_plot_files:
        generated_outputs.update(
            {
                "metrics_plots_svg": str(root / "metrics_plots.svg"),
                "metrics_plots_png": str(root / "metrics_plots.png"),
                "metrics_report_pdf": str(root / "metrics_report.pdf"),
            }
        )
        generated_output_lines[2:2] = [
            "- `metrics_plots.svg`: plot image generated from deduped numeric metrics.",
            "- `metrics_plots.png`: PNG plot image generated from deduped numeric metrics.",
            "- `metrics_report.pdf`: PDF plot report generated from deduped numeric metrics.",
        ]
    report = {
        "title": summary["title"],
        "generated_at": generated_at,
        "result_root": str(root),
        "generated_outputs": generated_outputs,
        "metrics_summary": summary,
        "artifacts": artifacts,
    }
    (root / "comprehensive_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )

    artifact_rows = [
        "| Artifact | Kind | Size Bytes | Lines |",
        "| --- | --- | ---: | ---: |",
    ]
    for artifact in artifacts:
        artifact_rows.append(
            "| "
            + " | ".join(
                [
                    markdown_escape(artifact["relative_path"]),
                    markdown_escape(artifact["kind"]),
                    markdown_escape(artifact["size_bytes"]),
                    markdown_escape(artifact["line_count"]),
                ]
            )
            + " |"
        )

    markdown = f"""# {summary["title"]}

Generated: {generated_at}

Result root: `{root}`

## Generated Outputs

{chr(10).join(generated_output_lines)}

## Run Summary

{run_table(summary)}

{evaluation_modes_markdown(summary)}

## Case Metadata

{case_metadata_markdown(summary)}

{analysis_sections_markdown(summary)}

## Instruction Compliance

{instruction_summary_markdown(summary.get("instruction_summary_rows") or [])}

## Instruction Issue Metrics

{instruction_issue_metrics_markdown(summary.get("instruction_issue_metric_rows") or [])}

## Instruction Misses And Failures

{instruction_details_markdown(summary.get("instruction_issue_rows") or [], "No fail or missing instruction items were recorded.")}

## Other Non-Pass Instruction Notes

{instruction_details_markdown(summary.get("instruction_non_pass_note_rows") or [], "No not-applicable or non-scoring instruction notes were recorded.")}

## Deduped Numeric Metrics

{metrics_table(summary)}

## Consolidated Metric Aliases

{metric_aliases_markdown(summary)}

## Combined Artifacts

{chr(10).join(artifact_rows)}
"""
    (root / "comprehensive_report.md").write_text(markdown, encoding="utf-8")


def truncate_text(value: str, limit: int = 96) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


def svg_text(value: Any) -> str:
    return html.escape(str(value), quote=True)


def plot_metadata_lines(summary: dict[str, Any]) -> list[str]:
    lines = []
    for row in summary.get("case_metadata_rows") or []:
        lines.append(
            " | ".join(
                [
                    f"run={fmt(row.get('run'))}",
                    f"agent={fmt(row.get('agent'))}",
                    f"clients={fmt(row.get('clients'))}",
                    f"algorithm={fmt(row.get('algorithm'))}",
                    f"rounds={fmt(row.get('rounds'))}",
                    f"job={fmt(row.get('job_name'))}",
                    f"model={fmt(row.get('agent_model'))}",
                ]
            )
        )
    return lines


def write_svg_plots(root: Path, summary: dict[str, Any]) -> None:
    visible_metrics, plot_note = plot_values_for_images(summary)
    metadata_lines = plot_metadata_lines(summary)
    width = 1400
    line_height = 22
    metric_gap = 10
    top = 104 + len(metadata_lines) * 18
    metric_count = len(visible_metrics)
    value_rows = sum(max(1, len(values)) + 1 for values in visible_metrics.values())
    height = max(320, top + value_rows * line_height + metric_count * metric_gap + 40)
    palette = ["#2563eb", "#16a34a", "#f59e0b", "#dc2626", "#7c3aed", "#0891b2"]

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        "<style>"
        "text{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;fill:#111827}"
        ".muted{fill:#4b5563}.metric{font-weight:600}.value{font-variant-numeric:tabular-nums}"
        ".track{fill:#f3f4f6}.grid{stroke:#e5e7eb;stroke-width:1}"
        "</style>",
        f'<text x="24" y="34" font-size="22" font-weight="700">{svg_text(summary["title"])}</text>',
        f'<text x="24" y="60" font-size="12" class="muted">Result root: {svg_text(summary["result_root"])}</text>',
        f'<text x="24" y="78" font-size="12" class="muted">{svg_text(plot_note)}</text>',
    ]
    for index, line in enumerate(metadata_lines):
        parts.append(
            f'<text x="24" y="{100 + index * 18}" font-size="12" class="muted">'
            f"{svg_text(truncate_text(line, 175))}</text>"
        )

    y = top
    bar_x = 560
    bar_max_width = 520
    value_x = bar_x + bar_max_width + 18
    for metric, values in visible_metrics.items():
        max_abs = max((abs(value) for value in values.values()), default=0)
        parts.append(f'<line x1="24" y1="{y - 13}" x2="{width - 24}" y2="{y - 13}" class="grid"/>')
        parts.append(
            f'<text x="24" y="{y}" font-size="12" class="metric">'
            f"<title>{svg_text(metric)}</title>{svg_text(truncate_text(metric, 88))}</text>"
        )
        y += line_height
        for color_index, (run_name, value) in enumerate(sorted(values.items())):
            bar_width = 0 if max_abs == 0 else min(bar_max_width, abs(value) / max_abs * bar_max_width)
            color = palette[color_index % len(palette)]
            parts.append(f'<text x="48" y="{y}" font-size="11" class="muted">{svg_text(run_name)}</text>')
            parts.append(f'<rect x="{bar_x}" y="{y - 12}" width="{bar_max_width}" height="12" rx="2" class="track"/>')
            parts.append(f'<rect x="{bar_x}" y="{y - 12}" width="{bar_width:.2f}" height="12" rx="2" fill="{color}"/>')
            parts.append(f'<text x="{value_x}" y="{y}" font-size="11" class="value">{svg_text(fmt(value))}</text>')
            y += line_height
        y += metric_gap

    parts.append("</svg>")
    (root / "metrics_plots.svg").write_text("\n".join(parts), encoding="utf-8")


FONT_5X7 = {
    " ": ["00000", "00000", "00000", "00000", "00000", "00000", "00000"],
    "!": ["00100", "00100", "00100", "00100", "00100", "00000", "00100"],
    "#": ["01010", "11111", "01010", "01010", "11111", "01010", "01010"],
    "%": ["11001", "11010", "00100", "01000", "10110", "00110", "00000"],
    "(": ["00010", "00100", "01000", "01000", "01000", "00100", "00010"],
    ")": ["01000", "00100", "00010", "00010", "00010", "00100", "01000"],
    "+": ["00000", "00100", "00100", "11111", "00100", "00100", "00000"],
    ",": ["00000", "00000", "00000", "00000", "00110", "00100", "01000"],
    "-": ["00000", "00000", "00000", "11111", "00000", "00000", "00000"],
    ".": ["00000", "00000", "00000", "00000", "00000", "01100", "01100"],
    "/": ["00001", "00010", "00100", "01000", "10000", "00000", "00000"],
    "0": ["01110", "10001", "10011", "10101", "11001", "10001", "01110"],
    "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "2": ["01110", "10001", "00001", "00010", "00100", "01000", "11111"],
    "3": ["11110", "00001", "00001", "01110", "00001", "00001", "11110"],
    "4": ["00010", "00110", "01010", "10010", "11111", "00010", "00010"],
    "5": ["11111", "10000", "10000", "11110", "00001", "00001", "11110"],
    "6": ["00110", "01000", "10000", "11110", "10001", "10001", "01110"],
    "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
    "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
    "9": ["01110", "10001", "10001", "01111", "00001", "00010", "01100"],
    ":": ["00000", "01100", "01100", "00000", "01100", "01100", "00000"],
    "=": ["00000", "11111", "00000", "11111", "00000", "00000", "00000"],
    "?": ["01110", "10001", "00001", "00010", "00100", "00000", "00100"],
    "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
    "B": ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
    "C": ["01110", "10001", "10000", "10000", "10000", "10001", "01110"],
    "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
    "F": ["11111", "10000", "10000", "11110", "10000", "10000", "10000"],
    "G": ["01110", "10001", "10000", "10111", "10001", "10001", "01110"],
    "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"],
    "I": ["01110", "00100", "00100", "00100", "00100", "00100", "01110"],
    "J": ["00111", "00010", "00010", "00010", "10010", "10010", "01100"],
    "K": ["10001", "10010", "10100", "11000", "10100", "10010", "10001"],
    "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
    "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"],
    "N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
    "Q": ["01110", "10001", "10001", "10001", "10101", "10010", "01101"],
    "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
    "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
    "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
    "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
    "V": ["10001", "10001", "10001", "10001", "10001", "01010", "00100"],
    "W": ["10001", "10001", "10001", "10101", "10101", "10101", "01010"],
    "X": ["10001", "10001", "01010", "00100", "01010", "10001", "10001"],
    "Y": ["10001", "10001", "01010", "00100", "00100", "00100", "00100"],
    "Z": ["11111", "00001", "00010", "00100", "01000", "10000", "11111"],
    "_": ["00000", "00000", "00000", "00000", "00000", "00000", "11111"],
}


class PngCanvas:
    def __init__(self, width: int, height: int, background: tuple[int, int, int] = (255, 255, 255)) -> None:
        self.width = width
        self.height = height
        self.pixels = bytearray(background * (width * height))

    def rect(self, x: int, y: int, width: int, height: int, color: tuple[int, int, int]) -> None:
        x0 = max(0, x)
        y0 = max(0, y)
        x1 = min(self.width, x + max(0, width))
        y1 = min(self.height, y + max(0, height))
        if x0 >= x1 or y0 >= y1:
            return
        row = bytes(color) * (x1 - x0)
        stride = self.width * 3
        for yy in range(y0, y1):
            start = yy * stride + x0 * 3
            self.pixels[start : start + len(row)] = row

    def text(self, x: int, y: int, text: Any, color: tuple[int, int, int] = (17, 24, 39), scale: int = 2) -> None:
        cursor = x
        for char in str(text).upper():
            glyph = FONT_5X7.get(char, FONT_5X7["?"])
            for row_index, row in enumerate(glyph):
                for col_index, value in enumerate(row):
                    if value == "1":
                        self.rect(cursor + col_index * scale, y + row_index * scale, scale, scale, color)
            cursor += 6 * scale

    def write_png(self, path: Path) -> None:
        def chunk(kind: bytes, payload: bytes) -> bytes:
            return (
                struct.pack(">I", len(payload))
                + kind
                + payload
                + struct.pack(">I", binascii.crc32(kind + payload) & 0xFFFFFFFF)
            )

        stride = self.width * 3
        raw = bytearray()
        for y in range(self.height):
            raw.append(0)
            start = y * stride
            raw.extend(self.pixels[start : start + stride])

        png = bytearray(b"\x89PNG\r\n\x1a\n")
        png.extend(chunk(b"IHDR", struct.pack(">IIBBBBB", self.width, self.height, 8, 2, 0, 0, 0)))
        png.extend(chunk(b"IDAT", zlib.compress(bytes(raw), level=6)))
        png.extend(chunk(b"IEND", b""))
        path.write_bytes(bytes(png))


def write_png_plots(root: Path, summary: dict[str, Any]) -> None:
    visible_metrics, plot_note = plot_values_for_images(summary)
    metadata_lines = plot_metadata_lines(summary)
    width = 1600
    line_height = 30
    metric_gap = 14
    top = 134 + len(metadata_lines) * 24
    metric_count = len(visible_metrics)
    value_rows = sum(max(1, len(values)) + 1 for values in visible_metrics.values())
    height = max(360, top + value_rows * line_height + metric_count * metric_gap + 48)
    palette = [(37, 99, 235), (22, 163, 74), (245, 158, 11), (220, 38, 38), (124, 58, 237), (8, 145, 178)]

    canvas = PngCanvas(width, height)
    canvas.text(24, 24, truncate_text(summary["title"], 58), scale=3)
    canvas.text(24, 68, "RESULT ROOT: " + truncate_text(summary["result_root"], 120), color=(75, 85, 99), scale=2)
    canvas.text(24, 92, truncate_text(plot_note, 125), color=(75, 85, 99), scale=2)
    for index, line in enumerate(metadata_lines):
        canvas.text(24, 122 + index * 24, truncate_text(line, 125), color=(75, 85, 99), scale=2)

    y = top
    bar_x = 820
    bar_max_width = 520
    value_x = bar_x + bar_max_width + 28
    for metric, values in visible_metrics.items():
        canvas.rect(24, y - 18, width - 48, 1, (229, 231, 235))
        canvas.text(24, y, truncate_text(metric, 88), scale=2)
        y += line_height
        max_abs = max((abs(value) for value in values.values()), default=0)
        for color_index, (run_name, value) in enumerate(sorted(values.items())):
            canvas.text(48, y, truncate_text(run_name, 50), color=(75, 85, 99), scale=2)
            canvas.rect(bar_x, y + 1, bar_max_width, 14, (243, 244, 246))
            bar_width = 0 if max_abs == 0 else min(bar_max_width, int(abs(value) / max_abs * bar_max_width))
            canvas.rect(bar_x, y + 1, bar_width, 14, palette[color_index % len(palette)])
            canvas.text(value_x, y, fmt(value), scale=2)
            y += line_height
        y += metric_gap

    canvas.write_png(root / "metrics_plots.png")


def pdf_literal(value: Any) -> str:
    text = str(value).encode("ascii", errors="backslashreplace").decode("ascii")
    text = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return f"({text})"


def add_pdf_text(ops: list[str], x: float, y: float, text: Any, size: int = 8) -> None:
    ops.append(f"BT /F1 {size} Tf {x:.2f} {y:.2f} Td {pdf_literal(text)} Tj ET")


def add_pdf_bar(
    ops: list[str], x: float, y: float, width: float, height: float, color: tuple[float, float, float]
) -> None:
    r, g, b = color
    ops.append(f"{r:.3f} {g:.3f} {b:.3f} rg {x:.2f} {y:.2f} {width:.2f} {height:.2f} re f 0 0 0 rg")


def write_pdf_plots(root: Path, summary: dict[str, Any]) -> None:
    visible_metrics, plot_note = plot_values_for_images(summary)
    plot_note = plot_note + " PDF text escapes non-ASCII characters."
    metadata_lines = plot_metadata_lines(summary)
    page_width = 612
    page_height = 792
    margin = 36
    line_height = 14
    bar_x = 310
    bar_max_width = 190
    value_x = 512
    colors = [(0.145, 0.388, 0.922), (0.086, 0.639, 0.290), (0.859, 0.149, 0.149), (0.486, 0.227, 0.929)]

    class PdfPageWriter:
        def __init__(self) -> None:
            self.pages: list[list[str]] = []
            self.y = page_height - margin

        def new_page(self) -> list[str]:
            ops: list[str] = []
            self.pages.append(ops)
            self.y = page_height - margin
            add_pdf_text(ops, margin, self.y, summary["title"], 13)
            self.y -= 18
            add_pdf_text(ops, margin, self.y, f"Result root: {summary['result_root']}", 7)
            self.y -= 12
            add_pdf_text(ops, margin, self.y, truncate_text(plot_note, 112), 7)
            self.y -= 10
            for line in metadata_lines:
                add_pdf_text(ops, margin, self.y, truncate_text(line, 112), 7)
                self.y -= 10
            self.y -= 12
            return ops

        def ensure_space(self, ops: list[str], needed: int = 1) -> list[str]:
            if self.y - needed * line_height < margin:
                return self.new_page()
            return ops

    writer = PdfPageWriter()
    ops = writer.new_page()
    if not visible_metrics:
        add_pdf_text(ops, margin, writer.y, "No numeric metrics found.", 10)
    for metric, values in visible_metrics.items():
        ops = writer.ensure_space(ops, 1 + max(1, len(values)))
        add_pdf_text(ops, margin, writer.y, truncate_text(metric, 70), 8)
        writer.y -= line_height
        max_abs = max((abs(value) for value in values.values()), default=0)
        for color_index, (run_name, value) in enumerate(sorted(values.items())):
            ops = writer.ensure_space(ops, 1)
            add_pdf_text(ops, margin + 12, writer.y, truncate_text(run_name, 34), 7)
            add_pdf_bar(ops, bar_x, writer.y - 4, bar_max_width, 6, (0.949, 0.953, 0.961))
            bar_width = 0 if max_abs == 0 else min(bar_max_width, abs(value) / max_abs * bar_max_width)
            add_pdf_bar(ops, bar_x, writer.y - 4, bar_width, 6, colors[color_index % len(colors)])
            add_pdf_text(ops, value_x, writer.y, fmt(value), 7)
            writer.y -= line_height
        writer.y -= 5

    objects: dict[int, bytes | str] = {}
    catalog_id = 1
    pages_id = 2
    font_id = 3
    next_id = 4
    page_ids = []
    for page_ops in writer.pages:
        page_id = next_id
        content_id = next_id + 1
        next_id += 2
        page_ids.append(page_id)
        stream = "\n".join(page_ops).encode("ascii")
        objects[content_id] = (
            b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream"
        )
        objects[page_id] = (
            f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 {page_width} {page_height}] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_id} 0 R >>"
        )
    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects[font_id] = "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    objects[pages_id] = f"<< /Type /Pages /Kids [ {kids} ] /Count {len(page_ids)} >>"
    objects[catalog_id] = f"<< /Type /Catalog /Pages {pages_id} 0 R >>"

    max_id = max(objects)
    data = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0] * (max_id + 1)
    for obj_id in range(1, max_id + 1):
        offsets[obj_id] = len(data)
        body = objects[obj_id]
        if isinstance(body, str):
            body_bytes = body.encode("latin-1", errors="replace")
        else:
            body_bytes = body
        data.extend(f"{obj_id} 0 obj\n".encode("ascii"))
        data.extend(body_bytes)
        data.extend(b"\nendobj\n")
    xref_offset = len(data)
    data.extend(f"xref\n0 {max_id + 1}\n".encode("ascii"))
    data.extend(b"0000000000 65535 f \n")
    for obj_id in range(1, max_id + 1):
        data.extend(f"{offsets[obj_id]:010d} 00000 n \n".encode("ascii"))
    data.extend(
        f"trailer\n<< /Size {max_id + 1} /Root {catalog_id} 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    (root / "metrics_report.pdf").write_bytes(bytes(data))


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate JSON and HTML metrics reports for benchmark result roots.")
    parser.add_argument("result_root", type=Path)
    parser.add_argument("--title", default="NVFLARE Codex Benchmark Metrics")
    parser.add_argument(
        "--plot-files",
        action="store_true",
        help="also generate metrics_plots.svg, metrics_plots.png, and metrics_report.pdf",
    )
    args = parser.parse_args()

    root = args.result_root.resolve()
    runs = collect_runs(root)
    summary = write_metrics_summary(root, args.title, runs)
    write_html_report(root, summary)
    if args.plot_files:
        write_svg_plots(root, summary)
        write_png_plots(root, summary)
        write_pdf_plots(root, summary)
    write_comprehensive_report(root, summary, include_plot_files=args.plot_files)
    print(root / "metrics_summary.json")
    print(root / "metrics_report.html")
    if args.plot_files:
        print(root / "metrics_plots.svg")
        print(root / "metrics_plots.png")
        print(root / "metrics_report.pdf")
    print(root / "comprehensive_report.json")
    print(root / "comprehensive_report.md")


if __name__ == "__main__":
    main()
