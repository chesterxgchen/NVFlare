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

"""Generate an insight-focused Markdown report for NVFLARE agent benchmark runs."""

from __future__ import annotations

import argparse
import html
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from harness.case_metadata import algorithm_consensus, algorithm_signal, load_generated_artifact_text
from harness.common import as_number, load_json, load_text
from harness.modes import NO_SKILLS_MODE
from harness.modes import PROCESS_EVAL_RUNS as PROCESS_EVAL_MODE_SPECS
from harness.modes import SKILLS_EVAL_OFF_MODE, SKILLS_EVAL_ON_MODE
from harness.quality_signals import canonical_metric_name, reported_validation_metric
from harness.record_identity import record_case, record_skill


def first_existing_path(*paths: Path) -> Path:
    for path in paths:
        if path.is_file():
            return path
    return paths[0]


REPORT_MODE_ORDER = [SKILLS_EVAL_OFF_MODE, SKILLS_EVAL_ON_MODE, NO_SKILLS_MODE]
REPORT_COL_LABELS = {
    SKILLS_EVAL_OFF_MODE: "With skills, skill eval off",
    SKILLS_EVAL_ON_MODE: "With skills, skill eval on",
    NO_SKILLS_MODE: "No skills baseline",
}
REQUIRED_STRUCTURE_FILES = ("client.py", "model.py", "job.py")
OPTIONAL_STRUCTURE_FILES = ("prepare_data.py", "download_data.py")
CONFIG_STRUCTURE_SUFFIXES = (".cfg", ".ini", ".json", ".toml", ".yaml", ".yml")
TREE_SOURCE_SUFFIXES = (".py",)
TREE_RUNTIME_SUFFIXES = (".py",) + CONFIG_STRUCTURE_SUFFIXES
EVALUATOR_PROCESS_METRIC_KEYS = {
    "conversion_quality",
    "validation_commands_run",
    "first_pass_accepted",
    "turns_to_acceptable",
    "user_correction_count",
    "agent_self_correction_count",
    "missed_instruction_count",
    "workflow_violations",
    "layout_violations",
    "evidence_gap_violations",
    "unnecessary_files_created",
}
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


def metric_display(metric: dict[str, Any] | None) -> str:
    metric = metric if isinstance(metric, dict) else {}
    name = metric.get("name")
    if not name:
        return "NA"
    value = metric.get("value")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{name} {value:.4f}"
    return f"{name} NA"


def additional_metric_values_display(metric: dict[str, Any] | None) -> str:
    metric = metric if isinstance(metric, dict) else {}
    values = metric.get("reported_values")
    labels = metric.get("reported_value_labels")
    if not isinstance(values, list):
        values = metric.get("site_values")
    if not isinstance(labels, list):
        labels = metric.get("site_value_labels")
    if not isinstance(values, list):
        return "NA"
    entries = [
        (labels[index] if isinstance(labels, list) and index < len(labels) else None, value)
        for index, value in enumerate(values)
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    ]
    if len(entries) <= 1:
        return "NA"
    rendered = []
    for index, (label, value) in enumerate(entries, start=1):
        label_text = str(label).strip() if label else f"value-{index}"
        rendered.append(f"{label_text}={value:.4f}")
    return ", ".join(rendered)


def metric_has_value(metric: dict[str, Any] | None) -> bool:
    if not isinstance(metric, dict):
        return False
    return isinstance(metric.get("value"), (int, float)) and not isinstance(metric.get("value"), bool)


def metric_reported_value_count(metric: dict[str, Any] | None) -> int:
    if not isinstance(metric, dict):
        return 0
    values = metric.get("reported_values")
    if not isinstance(values, list):
        values = metric.get("site_values")
    if not isinstance(values, list):
        return 0
    return sum(1 for value in values if isinstance(value, (int, float)) and not isinstance(value, bool))


def run_result_metric_status(run: dict[str, Any]) -> str:
    metric = run.get("validation_metric")
    metric = metric if isinstance(metric, dict) else {}
    name = metric.get("name")
    if metric_has_value(metric):
        return metric_display(metric)
    value_count = metric_reported_value_count(metric)
    if value_count:
        return f"partial: {value_count} reported values, no single FL scalar"
    if name:
        return f"missing scalar: {name} mentioned without value"
    return "missing"


def run_has_result_metric_issue(run: dict[str, Any]) -> bool:
    if not run.get("available"):
        return True
    metric = run.get("validation_metric")
    return not metric_has_value(metric)


def dependency_install_attempted(run: dict[str, Any]) -> bool:
    for command in commands_for_run(run):
        lowered = command.lower()
        if "pip install" in lowered or "uv pip install" in lowered or "python -m pip" in lowered:
            return True
    return False


def benchmark_outcome(run: dict[str, Any]) -> str:
    if not run.get("available"):
        return "fail: run artifacts missing"
    summary = run.get("run") if isinstance(run.get("run"), dict) else {}
    codex_exit = summary.get("codex_exit_code")
    final_exit = summary.get("final_container_exit_code")
    wrapper_status = str(run.get("status") or "")
    if codex_exit not in (None, 0):
        return f"fail: agent exit {codex_exit}"
    if final_exit not in (None, 0):
        return f"fail: final container exit {final_exit}"
    if wrapper_status and wrapper_status not in {"0", "missing"}:
        return f"fail: wrapper status {wrapper_status}"
    if run_has_result_metric_issue(run):
        return f"fail: no scalar FL result ({run_result_metric_status(run)})"
    return "pass: scalar FL result available"


def benchmark_outcome_summary(runs: dict[str, dict[str, Any]], modes: list[str]) -> str:
    return "; ".join(f"{REPORT_COL_LABELS[mode]}={benchmark_outcome(runs[mode])}" for mode in modes)


def process_pass_display(run: dict[str, Any]) -> str:
    summary = run.get("run") if isinstance(run.get("run"), dict) else {}
    record = run.get("record") if isinstance(run.get("record"), dict) else {}
    value = summary.get("codex_process_passed")
    if not isinstance(value, bool):
        value = record.get("codex_process_passed")
    if isinstance(value, bool):
        return "pass" if value else "fail"
    codex_exit = summary.get("codex_exit_code")
    if codex_exit == 0:
        return "pass"
    if codex_exit is None:
        return "NA"
    return "fail"


def evaluator_availability_display(run: dict[str, Any]) -> str:
    record = run.get("record") if isinstance(run.get("record"), dict) else {}
    metrics = record.get("process_metrics") if isinstance(record.get("process_metrics"), dict) else {}
    available = metrics.get("eval_passed_available")
    if isinstance(available, (int, float)) and not isinstance(available, bool):
        return "available" if available else "unavailable"
    if isinstance(record.get("eval_passed"), bool):
        return "available"
    return "unavailable"


def fl_result_status_display(run: dict[str, Any]) -> str:
    return run_result_metric_status(run)


def algorithm_display(run: dict[str, Any]) -> str:
    signal = run.get("algorithm_signal")
    signal = signal if isinstance(signal, dict) else algorithm_signal(run)
    algorithm = signal.get("algorithm")
    source = signal.get("source")
    if not algorithm:
        return "n/a"
    return f"{algorithm} ({source})" if source else str(algorithm)


def agent_display(run: dict[str, Any]) -> str:
    record = run.get("record") if isinstance(run.get("record"), dict) else {}
    summary = run.get("run") if isinstance(run.get("run"), dict) else {}
    runtime_image = run.get("runtime_image") if isinstance(run.get("runtime_image"), dict) else {}
    return str(summary.get("agent") or record.get("agent") or runtime_image.get("agent") or "unknown")


def agent_model_display(run: dict[str, Any]) -> str:
    record = run.get("record") if isinstance(run.get("record"), dict) else {}
    summary = run.get("run") if isinstance(run.get("run"), dict) else {}
    runtime_image = run.get("runtime_image") if isinstance(run.get("runtime_image"), dict) else {}
    return str(
        summary.get("agent_model")
        or record.get("agent_model")
        or runtime_image.get("agent_model")
        or runtime_image.get("codex_model")
        or "unknown"
    )


def same_record_path(left: str | None, right: str | None) -> bool:
    if not left or not right:
        return False
    try:
        return Path(left).resolve() == Path(right).resolve()
    except Exception:
        return str(left) == str(right)


def valid_identity(value: Any) -> str:
    text = str(value or "").strip()
    if not text or text in IDENTITY_PLACEHOLDERS or text.upper() in IDENTITY_PLACEHOLDERS:
        return ""
    return text


def evaluator_record_filter_description(run: dict[str, Any]) -> dict[str, Any]:
    record = run.get("record") if isinstance(run.get("record"), dict) else {}
    return {
        "source_path": record.get("agent_record_source_path"),
        "skill": valid_identity(record_skill(record)),
        "case_id": valid_identity(record_case(record)),
        "filtered_record_count": len(evaluator_records(run)),
    }


def collect_evaluator_records(root: Path, mode: str, mode_record: dict[str, Any]) -> list[dict[str, Any]]:
    records_dir = root / mode / "process_eval_runs"
    if not records_dir.is_dir():
        return []
    ignored = {f"{mode}_record.json", f"{mode}_agent_record.json"}
    expected_skill = valid_identity(record_skill(mode_record))
    expected_case = valid_identity(record_case(mode_record))
    expected_source_path = mode_record.get("agent_record_source_path") if isinstance(mode_record, dict) else None
    expected_source_path = str(expected_source_path) if expected_source_path else ""
    records = []
    for path in sorted(records_dir.rglob("*.json")):
        if path.name in ignored:
            continue
        record = load_json(path)
        if not isinstance(record, dict):
            continue
        if expected_source_path:
            if not same_record_path(str(path), expected_source_path):
                continue
        elif expected_skill and expected_case:
            if str(record_skill(record) or "") != expected_skill or str(record_case(record) or "") != expected_case:
                continue
        elif expected_skill:
            if str(record_skill(record) or "") != expected_skill:
                continue
        else:
            continue
        record = dict(record)
        record["_record_path"] = str(path)
        try:
            record["_record_mtime"] = path.stat().st_mtime
        except OSError:
            record["_record_mtime"] = 0
        records.append(record)
    return records


def filter_mode_console(console_text: str, mode: str) -> str:
    if not console_text:
        return ""
    prefix = f"[{mode}] "
    lines = []
    for line in console_text.splitlines():
        if line.startswith(prefix):
            lines.append(line[len(prefix) :])
    return "\n".join(lines)


def load_text_preview(path: Path, limit: int = 65536) -> str:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as stream:
            return stream.read(limit)
    except Exception:
        return ""


def collect_process_eval_runs(root: Path) -> dict[str, dict[str, Any]]:
    runs: dict[str, dict[str, Any]] = {}
    root_console_text = load_text(root / "console_output.log")
    for spec in PROCESS_EVAL_MODE_SPECS:
        mode = spec.mode
        summary_path = root / mode / "run_summary.json"
        activity_path = first_existing_path(root / mode / "agent_activity.json", root / mode / "codex_activity.json")
        timing_path = root / mode / "timing.json"
        record_path = root / mode / "process_eval_runs" / f"{mode}_record.json"
        runtime_image_path = root / mode / "runtime_image.json"
        container_exit_path = root / mode / "container_exit_code.json"
        host_case_error_path = root / mode / "host_case_error.json"
        early_failure_path = root / mode / "early_failure.json"
        late_harness_failure_path = root / mode / "late_harness_failure.json"
        agent_stderr_path = first_existing_path(root / mode / "agent_stderr.txt", root / mode / "codex_stderr.txt")
        agent_events_path = first_existing_path(root / mode / "agent_events.jsonl", root / mode / "codex_events.jsonl")
        console_path = root / f"{mode}.console.log"
        last_message_path = first_existing_path(
            root / mode / "agent_last_message.txt", root / mode / "codex_last_message.txt"
        )
        prompt_path = root / mode / "prompt.txt"
        status_path = root / f"{mode}.status"
        workspace_delta = load_json(root / mode / "workspace_delta_manifest.json") or {}
        source_input_delta = load_json(root / mode / "input_delta_manifest.json") or {}
        available = any(
            path.is_file()
            for path in (
                summary_path,
                activity_path,
                timing_path,
                record_path,
                last_message_path,
                prompt_path,
                status_path,
                container_exit_path,
                host_case_error_path,
                early_failure_path,
                late_harness_failure_path,
                runtime_image_path,
            )
        )
        run = load_json(summary_path) or {}
        activity = load_json(activity_path) or {}
        timing = load_json(timing_path) or {}
        record = load_json(record_path) or {}
        runtime_image = load_json(runtime_image_path) or {}
        container_exit = load_json(container_exit_path) or {}
        host_case_error = load_json(host_case_error_path) or {}
        early_failure = load_json(early_failure_path) or {}
        late_harness_failure = load_json(late_harness_failure_path) or {}
        last_message = load_text(last_message_path)
        agent_stderr = load_text(agent_stderr_path)
        agent_events_text = load_text_preview(agent_events_path)
        console_text = load_text(console_path) or filter_mode_console(root_console_text, mode)
        prompt_text = load_text(prompt_path)
        status = load_text(status_path).strip() if status_path.exists() else "missing"
        run_payload: dict[str, Any] = {
            "label": spec.label,
            "skills": "on" if spec.skills_enabled else "off",
            "process_eval": "on" if spec.process_eval_enabled else "off",
            "skill_eval": spec.nvflare_skill_eval_state,
            "available": available,
            "run": run,
            "activity": activity,
            "timing": timing,
            "record": record,
            "runtime_image": runtime_image,
            "container_exit": container_exit,
            "host_case_error": host_case_error,
            "early_failure": early_failure,
            "late_harness_failure": late_harness_failure,
            "agent_stderr": agent_stderr,
            "agent_events_text": agent_events_text,
            "console_text": console_text,
            "last_message": last_message,
            "prompt_text": prompt_text,
            "status": status,
            "validation_metric": record.get("reported_validation_metric") if isinstance(record, dict) else None,
            "workspace_delta": workspace_delta,
            "source_input_delta": source_input_delta
            or (record.get("source_input_delta") if isinstance(record, dict) else {}),
            "record_path": str(record_path) if record_path.is_file() else None,
            "generated_artifact_text": load_generated_artifact_text(root / mode, workspace_delta),
            "evaluator_records": collect_evaluator_records(root, mode, record if isinstance(record, dict) else {}),
        }
        run_payload["evaluator_record_filter"] = evaluator_record_filter_description(run_payload)
        run_payload["algorithm_signal"] = algorithm_signal(run_payload)
        runs[mode] = run_payload
    return runs


def collect_extra_run_names(root: Path, known_modes: set[str]) -> list[str]:
    names: list[str] = []
    if not root.is_dir():
        return names
    marker_names = {
        "run_summary.json",
        "agent_activity.json",
        "codex_activity.json",
        "timing.json",
        "agent_last_message.txt",
        "codex_last_message.txt",
        "prompt.txt",
    }
    for child in sorted(root.iterdir(), key=lambda path: path.name):
        if not child.is_dir() or child.name in known_modes:
            continue
        if any((child / marker).is_file() for marker in marker_names):
            names.append(child.name)
    return names


def run_value(runs: dict[str, dict[str, Any]], mode: str, key: str) -> Any:
    return runs[mode]["run"].get(key)


def phase_value(runs: dict[str, dict[str, Any]], mode: str, key: str) -> Any:
    timing = runs[mode]["timing"]
    phase_seconds = timing.get("phase_seconds") if isinstance(timing.get("phase_seconds"), dict) else {}
    return phase_seconds.get(key)


def usage_value(runs: dict[str, dict[str, Any]], mode: str, key: str) -> Any:
    usage = runs[mode]["run"].get("agent_usage") or runs[mode]["run"].get("codex_usage")
    usage = usage if isinstance(usage, dict) else {}
    return usage.get(key)


def activity_value(runs: dict[str, dict[str, Any]], mode: str, key: str) -> Any:
    return runs[mode]["activity"].get(key)


def event_type(runs: dict[str, dict[str, Any]], mode: str, key: str) -> int:
    event_types = runs[mode]["activity"].get("event_types")
    event_types = event_types if isinstance(event_types, dict) else {}
    return int(event_types.get(key, 0) or 0)


def hint_count(runs: dict[str, dict[str, Any]], mode: str, key: str) -> int:
    hints = runs[mode]["activity"].get("hint_counts")
    hints = hints if isinstance(hints, dict) else {}
    return int(hints.get(key, 0) or 0)


def fmt_int(value: Any) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "n/a"


def fmt_short(value: Any) -> str:
    if value is None:
        return "n/a"
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if abs(numeric) >= 1_000_000:
        return f"{numeric / 1_000_000:.2f}M"
    if abs(numeric) >= 1000:
        return f"{numeric / 1000:.1f}K"
    return f"{numeric:.0f}"


def fmt_signed_int(value: Any, suffix: str = "") -> str:
    numeric = as_number(value)
    if numeric is None:
        return "NA"
    sign = "+" if numeric >= 0 else "-"
    return f"{sign}{abs(int(round(numeric))):,}{suffix}"


def fmt_signed_short(value: Any, suffix: str = "") -> str:
    numeric = as_number(value)
    if numeric is None:
        return "NA"
    sign = "+" if numeric >= 0 else "-"
    return f"{sign}{fmt_short(abs(numeric))}{suffix}"


def fmt_percent(value: Any) -> str:
    numeric = as_number(value)
    return "n/a" if numeric is None else f"{numeric:.0f}%"


def safe_diff(left: Any, right: Any) -> float | None:
    left_num = as_number(left)
    right_num = as_number(right)
    if left_num is None or right_num is None:
        return None
    return left_num - right_num


def lowest_mode(modes: list[str], getter: Callable[[str], Any]) -> str | None:
    values = [(mode, as_number(getter(mode))) for mode in modes]
    values = [(mode, value) for mode, value in values if value is not None]
    if not values:
        return None
    return min(values, key=lambda item: item[1])[0]


def bar(value: Any, maximum: Any, width: int = 20) -> str:
    if value is None or maximum in (None, 0):
        return ""
    try:
        size = max(1, round(float(value) / float(maximum) * width))
    except (TypeError, ValueError, ZeroDivisionError):
        return ""
    return "#" * size


def artifact_summary(run: dict[str, Any]) -> str:
    manifest = run.get("workspace_delta") if isinstance(run.get("workspace_delta"), dict) else {}
    if not manifest:
        return "not captured"
    changed = manifest.get("changed_file_count")
    runtime = manifest.get("runtime_artifact_count")
    deleted = manifest.get("deleted_file_count")
    parts = []
    if isinstance(changed, (int, float)):
        parts.append(f"{int(changed)} changed/generated workspace files")
    if isinstance(runtime, (int, float)):
        parts.append(f"{int(runtime)} runtime artifacts")
    if isinstance(deleted, (int, float)) and deleted:
        parts.append(f"{int(deleted)} deleted files")
    return ", ".join(parts) if parts else "captured with no changed files"


def workspace_change_display(run: dict[str, Any]) -> str:
    manifest = run.get("workspace_delta") if isinstance(run.get("workspace_delta"), dict) else {}
    if not manifest:
        return "not captured"
    modified = manifest.get("workspace_modified_files")
    deleted = manifest.get("workspace_deleted_baseline_files")
    added = manifest.get("workspace_added_file_count")
    modified = modified if isinstance(modified, list) else []
    deleted = deleted if isinstance(deleted, list) else []
    if not modified and "workspace_modified_files" not in manifest:
        changed = manifest.get("changed_files")
        if isinstance(changed, list):
            modified = [entry for entry in changed if isinstance(entry, dict) and entry.get("status") == "modified"]
    if not deleted and "workspace_deleted_baseline_files" not in manifest:
        legacy_deleted = manifest.get("deleted_files")
        if isinstance(legacy_deleted, list):
            deleted = [entry for entry in legacy_deleted if isinstance(entry, dict)]
    if not isinstance(added, (int, float)):
        added = manifest.get("input_added_file_count")
    if not isinstance(added, (int, float)):
        changed = manifest.get("changed_files")
        if isinstance(changed, list):
            added = sum(1 for entry in changed if isinstance(entry, dict) and entry.get("status") == "added")
    added_entries: list[dict[str, Any]] = []
    changed = manifest.get("changed_files")
    if isinstance(changed, list):
        added_entries = [entry for entry in changed if isinstance(entry, dict) and entry.get("status") == "added"]
    if modified or deleted or added_entries:
        paths = [
            str(entry.get("path"))
            for entry in [*added_entries, *modified, *deleted]
            if isinstance(entry, dict) and entry.get("path")
        ]
        path_text = ", ".join(paths[:3])
        if len(paths) > 3:
            path_text += f", +{len(paths) - 3} more"
        return f"{len(added_entries)} added, {len(modified)} modified, {len(deleted)} deleted workspace files ({path_text})"
    if isinstance(added, (int, float)) and added:
        return f"{int(added)} added, 0 modified, 0 deleted workspace files"
    return "no copied-workspace changes"


def source_input_protection_display(run: dict[str, Any]) -> str:
    manifest = run.get("source_input_delta") if isinstance(run.get("source_input_delta"), dict) else {}
    record = run.get("record") if isinstance(run.get("record"), dict) else {}
    policy = (
        record.get("source_input_immutable_policy")
        if isinstance(record.get("source_input_immutable_policy"), dict)
        else {}
    )
    if policy.get("status") == "not_captured":
        reason = str(policy.get("reason") or "not captured in this artifact")
        return f"not captured in this artifact ({reason})"
    if not manifest:
        return "not captured in this artifact"
    if manifest.get("delta_scope") != "input_snapshot":
        return "not captured in this artifact (input delta manifest scope is missing or invalid)"
    changed = manifest.get("changed_file_count")
    deleted = manifest.get("deleted_file_count")
    changed_count = int(changed) if isinstance(changed, (int, float)) else 0
    deleted_count = int(deleted) if isinstance(deleted, (int, float)) else 0
    if changed_count or deleted_count:
        changed_entries = manifest.get("changed_files")
        deleted_entries = manifest.get("deleted_files")
        changed_entries = changed_entries if isinstance(changed_entries, list) else []
        deleted_entries = deleted_entries if isinstance(deleted_entries, list) else []
        paths = [
            str(entry.get("path"))
            for entry in [*changed_entries, *deleted_entries]
            if isinstance(entry, dict) and entry.get("path")
        ]
        path_text = ", ".join(paths[:3])
        if len(paths) > 3:
            path_text += f", +{len(paths) - 3} more"
        details = f" ({path_text})" if path_text else ""
        return f"FAIL: {changed_count} changed, {deleted_count} deleted immutable input files{details}"
    return "pass: immutable input snapshot unchanged"


def source_input_protection_summary(runs: dict[str, dict[str, Any]], modes: list[str]) -> str:
    failures = []
    missing = []
    for mode in modes:
        display = source_input_protection_display(runs[mode])
        if display.startswith("FAIL"):
            failures.append(f"{REPORT_COL_LABELS[mode]}: {display}")
        elif display.startswith("not captured"):
            missing.append(REPORT_COL_LABELS[mode])
    if failures:
        return "; ".join(failures)
    if missing:
        return (
            "Not captured in this artifact for: "
            + ", ".join(missing)
            + ". Future runs compare immutable `run/input` separately from writable `run/workspace`."
        )
    return "Immutable input snapshots were unchanged. Agent output changes are reported under copied workspace changes."


def matching_message_line(text: str, patterns: tuple[str, ...]) -> str | None:
    for raw_line in text.splitlines():
        line = raw_line.strip().lstrip("-").strip()
        if not line:
            continue
        lowered = line.lower()
        if any(pattern in lowered for pattern in patterns):
            return truncate(line, 220).rstrip(".")
    return None


def dependency_evidence(text: str) -> str | None:
    preflight_match = re.search(r"preflight:\s*missing\s+([^\n.]+)", text, flags=re.IGNORECASE)
    if preflight_match:
        packages = re.sub(r"[`]", "", preflight_match.group(1)).strip().strip(".")
        return f"preflight missing dependencies: {packages}"
    runtime_match = re.search(
        r"missing\s+runtime\s+dependencies.*?((?:`[^`]+`(?:\s*(?:,|and)\s*)?)+)\s+are\s+not\s+installed",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if runtime_match:
        packages = ", ".join(re.findall(r"`([^`]+)`", runtime_match.group(1)))
        return f"missing dependencies: {packages}" if packages else "missing dependencies"
    match = re.search(
        r"missing\s+(?:required\s+)?(?:python\s+)?package(?:\(s\))?\s*:? ([^\n.]+)",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    packages = match.group(1).strip().strip(".")
    return f"missing dependencies: {packages}" if packages else "missing dependencies"


def run_summary(run: dict[str, Any]) -> dict[str, Any]:
    return run.get("run") if isinstance(run.get("run"), dict) else {}


def container_exit_code(run: dict[str, Any]) -> Any:
    summary = run_summary(run)
    value = summary.get("final_container_exit_code")
    if value is not None:
        return value
    container_exit = run.get("container_exit") if isinstance(run.get("container_exit"), dict) else {}
    return container_exit.get("exit_code")


def failure_evidence_text(run: dict[str, Any]) -> str:
    parts = [
        str(run.get("console_text") or ""),
        str(run.get("agent_stderr") or ""),
        str(run.get("agent_events_text") or ""),
        str(run.get("last_message") or ""),
    ]
    for key in ("host_case_error", "early_failure", "late_harness_failure"):
        payload = run.get(key)
        if isinstance(payload, dict):
            parts.extend(str(payload.get(field) or "") for field in ("error_type", "message", "phase", "traceback"))
    summary = run_summary(run)
    error = summary.get("harness_error") if isinstance(summary.get("harness_error"), dict) else {}
    if error:
        parts.extend(str(error.get(field) or "") for field in ("error_type", "message", "phase"))
    return "\n".join(part for part in parts if part)


def first_evidence_line(text: str, patterns: tuple[str, ...]) -> str:
    line = matching_message_line(text, patterns)
    return line or "No single diagnostic line was captured."


def failure_root_cause(run: dict[str, Any]) -> str:
    if not run.get("available"):
        return "Run was not executed or no run artifacts were captured."
    text = failure_evidence_text(run)
    lowered = text.lower()
    image_match = re.search(r"unable to find image ['\"]?([^'\"\s]+)", text, flags=re.IGNORECASE)
    if image_match or "pull access denied" in lowered or "repository does not exist" in lowered:
        image = image_match.group(1) if image_match else "requested benchmark image"
        return f"Docker image unavailable in the active Docker context: {image}."
    if "permission denied" in lowered and "docker" in lowered and "sock" in lowered:
        return "Docker socket access was denied for the benchmark runner."
    unsupported_model_match = re.search(
        r"The\s+'[^']+'\s+model\s+is\s+not\s+supported[^\"\\]*",
        text,
        flags=re.IGNORECASE,
    )
    if "model is not supported" in lowered or unsupported_model_match:
        message = (
            unsupported_model_match.group(0).rstrip(".")
            if unsupported_model_match
            else "selected model is not supported"
        )
        return f"Codex model selection failed: {message}."
    dependency = dependency_evidence(text)
    if dependency:
        if dependency_install_attempted(run):
            return f"Job dependency problem after dependency installation attempt: {dependency}."
        return f"Job dependency preflight failed before a metric-producing run: {dependency}."
    harness_error = harness_error_display(run)
    if harness_error != "none":
        return f"Harness failure: {harness_error}."
    summary = run_summary(run)
    codex_exit = summary.get("codex_exit_code")
    final_exit = container_exit_code(run)
    wrapper_status = str(run.get("status") or "")
    if codex_exit not in (None, 0):
        return f"Agent process exited nonzero ({codex_exit}) before producing a valid FL result."
    if final_exit not in (None, 0):
        return f"Benchmark container exited nonzero ({final_exit}) before producing a valid FL result."
    if wrapper_status and wrapper_status not in {"0", "missing"}:
        return f"Host wrapper recorded nonzero status ({wrapper_status})."
    if run_has_result_metric_issue(run):
        return f"No parseable scalar FL result metric was found ({run_result_metric_status(run)})."
    return "No failure detected from captured benchmark evidence."


def failure_evidence(run: dict[str, Any]) -> str:
    text = failure_evidence_text(run)
    lowered = text.lower()
    if "unable to find image" in lowered or "pull access denied" in lowered or "repository does not exist" in lowered:
        return first_evidence_line(text, ("unable to find image", "pull access denied", "repository does not exist"))
    if "permission denied" in lowered and "docker" in lowered:
        return first_evidence_line(text, ("permission denied",))
    if "model is not supported" in lowered:
        match = re.search(r"The\s+'[^']+'\s+model\s+is\s+not\s+supported[^\"\\]*", text, flags=re.IGNORECASE)
        if match:
            return match.group(0).rstrip(".") + "."
        return first_evidence_line(text, ("model is not supported", "invalid_request_error"))
    dependency = dependency_evidence(text)
    if dependency:
        return first_evidence_line(text, ("missing", "not installed", "preflight"))
    harness_error = harness_error_display(run)
    if harness_error != "none":
        return harness_error
    if text:
        return first_evidence_line(text, ("error", "failed", "exception", "traceback", "exit"))
    return "No diagnostic text was captured."


def failure_next_action(run: dict[str, Any]) -> str:
    cause = failure_root_cause(run).lower()
    if "docker image unavailable" in cause:
        return "Build the benchmark images with `./bin/build.sh`, or set `IMAGE_NAME`/`BASELINE_IMAGE_NAME` to the tags in the active Docker context."
    if "docker socket" in cause:
        return "Start Docker Desktop or fix Docker socket permissions, then rerun the benchmark."
    if "model selection failed" in cause:
        return "Use a Codex model supported by the active account, or update the benchmark model/account configuration before rerunning."
    if "not executed" in cause or "no run artifacts" in cause:
        return "If this mode is required, rerun the benchmark mode that produces it; otherwise ignore it for a smaller comparison."
    if "dependency" in cause:
        return "Install the job's requirements during preflight and rerun export/simulation before declaring a blocker."
    if "harness failure" in cause:
        return (
            "Inspect `early_failure.json`, `late_harness_failure.json`, and `agent_stderr.txt` for the failing phase."
        )
    if "no parseable scalar" in cause:
        return "Make the conversion report one aggregate FL validation metric in the final message or process record."
    return "Inspect the mode console log, agent stderr, and run summary for the first failing command."


def run_failed(run: dict[str, Any]) -> bool:
    summary = run_summary(run)
    codex_exit = summary.get("codex_exit_code")
    final_exit = container_exit_code(run)
    wrapper_status = str(run.get("status") or "")
    return (
        not run.get("available")
        or codex_exit not in (None, 0)
        or final_exit not in (None, 0)
        or bool(wrapper_status and wrapper_status not in {"0", "missing"})
        or run_has_result_metric_issue(run)
    )


def human_readable_status(run: dict[str, Any]) -> str:
    summary = run_summary(run)
    codex_exit = summary.get("codex_exit_code")
    final_exit = container_exit_code(run)
    wrapper_status = str(run.get("status") or "")
    if not run.get("available"):
        return "not run or artifacts missing"
    exit_parts = []
    if codex_exit not in (None, 0):
        exit_parts.append(f"agent exit {codex_exit}")
    if final_exit not in (None, 0):
        exit_parts.append(f"container exit {final_exit}")
    if wrapper_status and wrapper_status not in {"0", "missing"}:
        exit_parts.append(f"wrapper status {wrapper_status}")
    if exit_parts:
        return "failed: " + ", ".join(exit_parts) + f" - {failure_root_cause(run)}"
    if run_has_result_metric_issue(run):
        return f"completed but failed quality gate: {failure_root_cause(run)}"
    return "completed: scalar FL result metric available"


def status_summary(runs: dict[str, dict[str, Any]], modes: list[str]) -> str:
    available_modes = [mode for mode in modes if runs[mode].get("available")]
    if not available_modes:
        return "No completed run artifacts."
    return "; ".join(f"{REPORT_COL_LABELS[mode]}: {human_readable_status(runs[mode])}" for mode in available_modes)


def result_issue_explanation(run: dict[str, Any]) -> str:
    reasons: list[str] = []
    summary = run_summary(run)
    if not run.get("available"):
        reasons.append("run artifacts are missing")

    codex_exit = summary.get("codex_exit_code")
    final_exit = container_exit_code(run)
    wrapper_status = str(run.get("status") or "")
    if codex_exit not in (None, 0):
        reasons.append(f"agent exit code {codex_exit}")
    if final_exit not in (None, 0):
        reasons.append(f"final container exit code {final_exit}")
    if wrapper_status and wrapper_status not in {"0", "missing"}:
        reasons.append(f"wrapper status {wrapper_status}")

    harness_error = harness_error_display(run)
    if harness_error != "none":
        reasons.append(f"harness error: {harness_error}")

    last_message = str(run.get("last_message") or "")
    dependency = dependency_evidence(last_message)
    if dependency:
        reasons.append(dependency)
        if not dependency_install_attempted(run):
            reasons.append("no dependency installation command was attempted")
    line = None
    for patterns in (
        (
            "no flare workspace, result file, or metrics were produced",
            "no metrics were produced",
            "no flare workspace",
            "no result",
        ),
        (
            "stopped at preflight",
            "blocked by the same missing dependencies",
            "simulation command was attempted",
            "export was also attempted",
        ),
        ("not installed",),
    ):
        line = matching_message_line(last_message, patterns)
        if line:
            break
    if line and line not in reasons:
        reasons.append(line)
        lowered_line = line.lower()
        if ("not installed" in lowered_line or "missing depend" in lowered_line) and not dependency_install_attempted(
            run
        ):
            reasons.append("no dependency installation command was attempted")

    workspace_delta = run.get("workspace_delta") if isinstance(run.get("workspace_delta"), dict) else {}
    if workspace_delta and workspace_delta.get("runtime_artifact_count") == 0:
        reasons.append("no runtime FL artifacts captured")

    if not reasons:
        status = run_result_metric_status(run)
        if status.startswith("partial"):
            reasons.append("run reported metric values but no single FL aggregate scalar")
        else:
            reasons.append("final message and records did not contain parseable FL result metrics")
    return "; ".join(dict.fromkeys(reasons))


def result_issue_action(run: dict[str, Any]) -> str:
    explanation = result_issue_explanation(run).lower()
    status = run_result_metric_status(run)
    if "missing dependencies" in explanation or "preflight" in explanation or "not installed" in explanation:
        return "Benchmark failure: FL simulation/export did not run to metric-producing completion."
    if status.startswith("partial"):
        return "Benchmark failure for scalar-quality comparison; require one aggregate FL validation metric."
    return "Benchmark failure until the run produces parseable FL validation metrics."


def result_issue_modes(runs: dict[str, dict[str, Any]], modes: list[str]) -> list[str]:
    return [mode for mode in modes if run_has_result_metric_issue(runs[mode])]


def result_issue_summary(runs: dict[str, dict[str, Any]], modes: list[str]) -> str:
    issue_modes = result_issue_modes(runs, modes)
    if not issue_modes:
        return "All runs reported a scalar FL result metric."
    return "; ".join(f"{REPORT_COL_LABELS[mode]}: {run_result_metric_status(runs[mode])}" for mode in issue_modes)


def missing_result_metrics_section(runs: dict[str, dict[str, Any]], modes: list[str]) -> str:
    issue_modes = result_issue_modes(runs, modes)
    if not issue_modes:
        return ""
    lines = [
        "## Missing Or Partial Result Metrics",
        "",
        "This section is shown because at least one run did not produce a parseable scalar FL result metric. A run with no scalar FL result is a benchmark quality failure for comparison purposes, even if the agent process exited or an evaluator record says the final code shape was accepted.",
        "",
        "| Run | Result metric status | Why results are missing or partial | Report action |",
        "| --- | --- | --- | --- |",
    ]
    for mode in issue_modes:
        run = runs[mode]
        lines.append(
            f"| {REPORT_COL_LABELS[mode]} | {markdown_cell(run_result_metric_status(run))} | "
            f"{markdown_cell(result_issue_explanation(run))} | {markdown_cell(result_issue_action(run))} |"
        )
    return "\n".join(lines)


def failure_analysis_section(runs: dict[str, dict[str, Any]], modes: list[str]) -> str:
    failed_modes = [mode for mode in modes if run_failed(runs[mode])]
    if not failed_modes:
        return ""
    lines = [
        "## Failure Analysis",
        "",
        "This section summarizes the likely root cause from captured benchmark artifacts. It favors direct evidence from console logs, agent stderr, harness failure JSON, run summaries, and final messages.",
        "",
        "| Run | Human-readable status | Likely root cause | Evidence | Next action |",
        "| --- | --- | --- | --- | --- |",
    ]
    for mode in failed_modes:
        run = runs[mode]
        lines.append(
            f"| {REPORT_COL_LABELS[mode]} | {markdown_cell(human_readable_status(run))} | "
            f"{markdown_cell(failure_root_cause(run))} | {markdown_cell(truncate(failure_evidence(run), 240))} | "
            f"{markdown_cell(failure_next_action(run))} |"
        )
    return "\n".join(lines)


def manifest_paths(run: dict[str, Any], key: str) -> list[str]:
    manifest = run.get("workspace_delta") if isinstance(run.get("workspace_delta"), dict) else {}
    paths: list[str] = []
    entries = manifest.get(key)
    if not isinstance(entries, list):
        return paths
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        value = entry.get("path")
        if isinstance(value, str) and value:
            paths.append(value)
    return paths


def unique_paths(paths: list[str]) -> list[str]:
    seen = set()
    unique = []
    for path in paths:
        normalized = path.replace("\\", "/")
        if normalized.startswith("changed_files/"):
            normalized = normalized[len("changed_files/") :]
        if normalized in seen:
            continue
        seen.add(normalized)
        unique.append(normalized)
    return unique


def structure_file_matches(run: dict[str, Any], filename: str) -> list[str]:
    expected = filename.lower()
    return [
        path
        for path in unique_paths(manifest_paths(run, "final_structure_files"))
        if Path(path).name.lower() == expected
    ]


def structure_score(run: dict[str, Any]) -> float | None:
    manifest = run.get("workspace_delta") if isinstance(run.get("workspace_delta"), dict) else {}
    if not manifest:
        return None
    present = sum(1 for filename in REQUIRED_STRUCTURE_FILES if structure_file_matches(run, filename))
    return present / len(REQUIRED_STRUCTURE_FILES) * 100


def structure_required_display(run: dict[str, Any]) -> str:
    if structure_score(run) is None:
        return "not captured"
    present = sum(1 for filename in REQUIRED_STRUCTURE_FILES if structure_file_matches(run, filename))
    return f"{present}/{len(REQUIRED_STRUCTURE_FILES)} ideal"


def structure_optional_display(run: dict[str, Any]) -> str:
    if structure_score(run) is None:
        return "not captured"
    present = [filename for filename in OPTIONAL_STRUCTURE_FILES if structure_file_matches(run, filename)]
    return ", ".join(present) if present else "none"


def basename_count_display(paths: list[str], limit: int = 5) -> str:
    counts = Counter(Path(path).name for path in paths if Path(path).name)
    if not counts:
        return "NA"
    parts = [name if count == 1 else f"{name} ({count} paths)" for name, count in sorted(counts.items())]
    if len(parts) > limit:
        parts = parts[:limit] + [f"+{len(parts) - limit} more"]
    return ", ".join(parts)


def structure_inventory_paths(run: dict[str, Any], key: str, suffixes: tuple[str, ...]) -> list[str]:
    normalized_suffixes = tuple(suffix.lower() for suffix in suffixes)
    paths = unique_paths(manifest_paths(run, key))
    return [path for path in paths if Path(path).name.lower().endswith(normalized_suffixes)]


def structure_inventory_display(run: dict[str, Any], key: str, suffixes: tuple[str, ...]) -> str:
    if structure_score(run) is None:
        return "NA"
    return basename_count_display(structure_inventory_paths(run, key, suffixes))


def tree_from_paths(paths: list[str], *, root_label: str = ".", max_paths: int = 120) -> str:
    normalized_paths = sorted(unique_paths(paths))
    if not normalized_paths:
        return f"{root_label}\n`-- (none)"
    omitted = max(0, len(normalized_paths) - max_paths)
    selected_paths = normalized_paths[:max_paths]
    tree: dict[str, Any] = {}
    for path in selected_paths:
        parts = [part for part in path.replace("\\", "/").split("/") if part and part != "."]
        if not parts:
            continue
        node = tree
        for part in parts[:-1]:
            child = node.setdefault(part, {})
            if isinstance(child, dict):
                node = child
        node.setdefault(parts[-1], None)
    lines = [root_label]

    def walk(node: dict[str, Any], prefix: str = "") -> None:
        items = sorted(node.items(), key=lambda item: (not isinstance(item[1], dict), item[0]))
        for index, (name, child) in enumerate(items):
            is_last = index == len(items) - 1 and omitted == 0
            connector = "`-- " if is_last else "|-- "
            lines.append(f"{prefix}{connector}{name}")
            if isinstance(child, dict):
                walk(child, prefix + ("    " if is_last else "|   "))

    walk(tree)
    if omitted:
        lines.append(f"`-- ... {omitted} more paths omitted")
    return "\n".join(lines)


def structure_tree_paths(run: dict[str, Any], key: str, suffixes: tuple[str, ...]) -> list[str]:
    if structure_score(run) is None:
        return []
    return structure_inventory_paths(run, key, suffixes)


def structure_trees_section(runs: dict[str, dict[str, Any]], modes: list[str]) -> str:
    lines = [
        "### Structure Trees",
        "",
        "Trees are reconstructed from captured artifact manifests, so they show the post-run structure even when the original container is gone.",
    ]
    for mode in modes:
        lines.append("")
        lines.append(f"#### {REPORT_COL_LABELS[mode]}")
        for title, key, suffixes in (
            ("Final workspace Python tree", "final_files", TREE_SOURCE_SUFFIXES),
            ("Runtime exported job source/config tree", "runtime_artifacts", TREE_RUNTIME_SUFFIXES),
        ):
            paths = structure_tree_paths(runs[mode], key, suffixes)
            lines.append("")
            lines.append(f"{title}:")
            lines.append("")
            lines.append("```text")
            lines.append(tree_from_paths(paths))
            lines.append("```")
    return "\n".join(lines)


def structure_ideal_display(run: dict[str, Any]) -> str:
    if structure_score(run) is None:
        return "NA"
    present = [filename for filename in REQUIRED_STRUCTURE_FILES if structure_file_matches(run, filename)]
    return f"{len(present)}/{len(REQUIRED_STRUCTURE_FILES)}: " + (", ".join(present) if present else "NA")


def structure_correctness_table(runs: dict[str, dict[str, Any]], modes: list[str]) -> str:
    lines = [
        "| Structure layer | " + " | ".join(REPORT_COL_LABELS[mode] for mode in modes) + " |",
        "| --- | " + " | ".join("---" for _ in modes) + " |",
    ]
    rows = [
        ("Ideal generated source (`client.py`, `model.py`, `job.py`)", structure_ideal_display),
        ("Final workspace Python inventory", lambda run: structure_inventory_display(run, "final_files", (".py",))),
        (
            "Final workspace config inventory",
            lambda run: structure_inventory_display(run, "final_files", CONFIG_STRUCTURE_SUFFIXES),
        ),
        ("Changed/generated Python inventory", lambda run: structure_inventory_display(run, "changed_files", (".py",))),
        (
            "Changed/generated config inventory",
            lambda run: structure_inventory_display(run, "changed_files", CONFIG_STRUCTURE_SUFFIXES),
        ),
        (
            "Runtime artifact Python inventory",
            lambda run: structure_inventory_display(run, "runtime_artifacts", (".py",)),
        ),
        (
            "Runtime artifact config inventory",
            lambda run: structure_inventory_display(run, "runtime_artifacts", CONFIG_STRUCTURE_SUFFIXES),
        ),
    ]
    for label, formatter in rows:
        lines.append(f"| {label} | " + " | ".join(markdown_cell(formatter(runs[mode])) for mode in modes) + " |")
    return "\n".join(lines)


def run_outcome(run: dict[str, Any]) -> str:
    summary = run.get("run") if isinstance(run.get("run"), dict) else {}
    codex_exit = summary.get("codex_exit_code")
    wrapper_status = run.get("status")
    if codex_exit == 0 and str(wrapper_status) in {"0", "missing"}:
        return "Agent process completed"
    if codex_exit == 0:
        return f"Agent process completed; wrapper status {wrapper_status}"
    if codex_exit is None:
        return f"unknown; wrapper status {wrapper_status}"
    return f"Agent process exit {codex_exit}; wrapper status {wrapper_status}"


def harness_error_display(run: dict[str, Any]) -> str:
    summary = run.get("run") if isinstance(run.get("run"), dict) else {}
    error = summary.get("harness_error") if isinstance(summary.get("harness_error"), dict) else {}
    if not error:
        return "none"
    phase = error.get("phase") or "unknown phase"
    error_type = error.get("error_type") or "error"
    message = truncate(error.get("message") or "", 120)
    return f"{phase}: {error_type}" + (f" - {message}" if message else "")


def evaluator_display(run: dict[str, Any]) -> str:
    evaluator_record = primary_evaluator_record(run)
    if isinstance(evaluator_record, dict) and isinstance(evaluator_record.get("eval_passed"), bool):
        return "pass" if evaluator_record["eval_passed"] else "fail"
    record = run.get("record") if isinstance(run.get("record"), dict) else {}
    value = record.get("eval_passed")
    source = str(record.get("eval_passed_source") or record.get("agent_record_source") or "")
    evaluator_backed = "nvflare_skill_evaluator_record" in source
    if isinstance(value, bool) and evaluator_backed:
        return "pass" if value else "fail"
    process_value = record.get("codex_process_passed")
    if isinstance(process_value, bool):
        return "n/a (process pass)" if process_value else "n/a (process fail)"
    return "n/a"


def record_display(run: dict[str, Any]) -> str:
    if run.get("record_path"):
        source = (run.get("record") or {}).get("agent_record_source")
        return str(source or "present")
    return "missing"


def evaluator_records(run: dict[str, Any]) -> list[dict[str, Any]]:
    records = run.get("evaluator_records")
    filtered = [record for record in records if isinstance(record, dict)] if isinstance(records, list) else []
    record = run.get("record") if isinstance(run.get("record"), dict) else {}
    if not evaluator_backed_record(record):
        return filtered
    mode_record = dict(record)
    record_path = str(run.get("record_path") or "")
    if record_path:
        mode_record["_record_path"] = record_path
        try:
            mode_record["_record_mtime"] = Path(record_path).stat().st_mtime
        except OSError:
            mode_record["_record_mtime"] = 0
    if any(same_record_path(str(item.get("_record_path") or ""), record_path) for item in filtered):
        return filtered
    return filtered + [mode_record]


def evaluator_backed_record(record: dict[str, Any]) -> bool:
    if not isinstance(record, dict):
        return False
    sources = {str(record.get(key) or "") for key in ("agent_record_source", "eval_passed_source", "score_source")}
    if "nvflare_skill_evaluator_record" in sources:
        return True
    if "harness_synthesized" in sources:
        return False
    source_text = " ".join(sources)
    if "nvflare_skill_evaluator_record" in source_text:
        return True
    if isinstance(record.get("eval_passed"), bool):
        score = record.get("score")
        if isinstance(score, dict) and score.get("value") is not None:
            return True
    metrics = record.get("process_metrics")
    if isinstance(metrics, dict) and any(key in metrics for key in EVALUATOR_PROCESS_METRIC_KEYS):
        return True
    return any(
        isinstance(record.get(group), dict) and record[group] for group in ("mandatory_behavior", "prohibited_behavior")
    )


def primary_evaluator_record(run: dict[str, Any]) -> dict[str, Any] | None:
    records = evaluator_records(run)
    if not records:
        return None
    return max(records, key=evaluator_record_sort_key)


def timestamp_sort_value(value: Any) -> float:
    text = str(value or "").strip()
    if not text:
        return 0.0
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return 0.0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def evaluator_record_sort_key(record: dict[str, Any]) -> tuple[float, float, str, str]:
    path = str(record.get("_record_path") or "")
    name = Path(path).name if path else ""
    timestamp = timestamp_sort_value(record.get("timestamp") or record.get("created_at"))
    mtime = as_number(record.get("_record_mtime")) or 0.0
    return (timestamp, mtime, name, path)


def evaluator_score_value(run: dict[str, Any]) -> Any:
    record = primary_evaluator_record(run)
    score = record.get("score") if isinstance(record, dict) else None
    return score.get("value") if isinstance(score, dict) else None


def evaluator_score_max(run: dict[str, Any]) -> Any:
    record = primary_evaluator_record(run)
    score = record.get("score") if isinstance(record, dict) else None
    return score.get("max") if isinstance(score, dict) else None


def evaluator_score_rationale(run: dict[str, Any]) -> str:
    record = primary_evaluator_record(run)
    parts: list[str] = []
    score = record.get("score") if isinstance(record, dict) else None
    if isinstance(score, dict) and score.get("rationale"):
        parts.append(str(score["rationale"]))
    first_pass = record.get("first_pass") if isinstance(record, dict) else None
    if isinstance(first_pass, dict):
        accepted = first_pass.get("accepted")
        violations = first_pass.get("violations")
        if accepted is False:
            if isinstance(violations, list) and violations:
                parts.append("First pass rejected: " + "; ".join(str(item) for item in violations[:3]))
            else:
                parts.append("First pass rejected.")
    if run_has_result_metric_issue(run):
        parts.append(f"No scalar FL result metric: {run_result_metric_status(run)}.")
    if not parts:
        return "No score rationale captured."
    return " ".join(dict.fromkeys(parts))


def evaluator_process_value(run: dict[str, Any], key: str) -> Any:
    record = primary_evaluator_record(run)
    metrics = record.get("process_metrics") if isinstance(record, dict) else None
    return metrics.get(key) if isinstance(metrics, dict) else None


def evaluator_first_pass_accepted(run: dict[str, Any]) -> Any:
    record = primary_evaluator_record(run)
    first_pass = record.get("first_pass") if isinstance(record, dict) else None
    if isinstance(first_pass, dict) and isinstance(first_pass.get("accepted"), bool):
        return first_pass["accepted"]
    return evaluator_process_value(run, "first_pass_accepted")


def evaluator_bool_value(run: dict[str, Any], key: str) -> bool | None:
    record = primary_evaluator_record(run)
    if not isinstance(record, dict):
        return None
    value = record.get(key)
    return value if isinstance(value, bool) else None


def evaluator_bool_numeric(run: dict[str, Any], key: str) -> float | None:
    value = evaluator_bool_value(run, key)
    if value is None:
        return None
    return 1.0 if value else 0.0


def evaluator_behavior_rate(run: dict[str, Any], group: str) -> float | None:
    record = primary_evaluator_record(run)
    behaviors = record.get(group) if isinstance(record, dict) else None
    if not isinstance(behaviors, dict):
        return None
    statuses = []
    for item in behaviors.values():
        if isinstance(item, dict):
            status = item.get("status")
            if isinstance(status, str):
                statuses.append(status)
    applicable = [status for status in statuses if status not in {"not_applicable", "non_scoring_note"}]
    if not applicable:
        return None
    return sum(1 for status in applicable if status == "pass") / len(applicable)


def reported_metric_value(run: dict[str, Any]) -> Any:
    metric = run.get("validation_metric")
    if isinstance(metric, dict):
        return metric.get("value")
    return None


def validation_chart_label(run: dict[str, Any] | None) -> str:
    if not run:
        return "NA"
    metric = run.get("validation_metric")
    metric = metric if isinstance(metric, dict) else {}
    value = metric.get("value")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value:.4f}"
    if metric_reported_value_count(metric):
        return "partial"
    if metric.get("name"):
        return "missing"
    return "missing"


def fmt_na(value: Any) -> str:
    return "NA" if as_number(value) is None else fmt_short(value)


def fmt_rate_value(value: Any) -> str:
    numeric = as_number(value)
    return "NA" if numeric is None else f"{numeric * 100:.0f}%"


def fmt_one_decimal(value: Any) -> str:
    numeric = as_number(value)
    return "NA" if numeric is None else f"{numeric:.1f}"


def fmt_score_value(value: Any, max_value: Any) -> str:
    numeric = as_number(value)
    max_numeric = as_number(max_value)
    if numeric is None:
        return "NA"
    if max_numeric is None:
        return f"{numeric:.0f}"
    return f"{numeric:.0f}/{max_numeric:.0f}"


def fmt_yes_no(value: Any) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    numeric = as_number(value)
    if numeric is None:
        return "NA"
    return "yes" if numeric >= 0.5 else "no"


def format_chart_value(value: Any, kind: str, run: dict[str, Any] | None = None) -> str:
    if kind == "validation":
        return validation_chart_label(run)
    numeric = as_number(value)
    if numeric is None:
        return "NA"
    if kind == "millions":
        return f"{numeric:.2f}M"
    if kind == "percent":
        return f"{numeric:.0f}%"
    if kind == "rate":
        return f"{numeric * 100:.0f}%"
    if kind == "bool":
        return fmt_yes_no(numeric)
    if kind == "score":
        max_value = evaluator_score_max(run or {}) if run else None
        return fmt_score_value(numeric, max_value)
    return f"{int(round(numeric))}"


def validation_metric_chart_name(runs: dict[str, dict[str, Any]]) -> str | None:
    names = []
    for mode in REPORT_MODE_ORDER:
        run = runs.get(mode)
        metric = run.get("validation_metric") if isinstance(run, dict) else None
        if not isinstance(metric, dict):
            continue
        name = canonical_metric_name(metric.get("name"))
        if name and name not in names:
            names.append(name)
    if len(names) == 1:
        return names[0]
    if len(names) > 1:
        return "mixed"
    return None


def validation_metric_chart_title(runs: dict[str, dict[str, Any]]) -> str:
    metric_name = validation_metric_chart_name(runs)
    return f"Metrics ({metric_name})" if metric_name else "Metrics"


def benchmark_chart_metrics(
    runs: dict[str, dict[str, Any]],
) -> list[tuple[str, Callable[[str, dict[str, dict[str, Any]]], Any], str, float | None]]:
    return [
        ("Runtime seconds", lambda mode, runs: run_value(runs, mode, "elapsed_seconds"), "int", None),
        (
            "Total tokens",
            lambda mode, runs: (
                as_number(run_value(runs, mode, "token_count")) / 1_000_000
                if as_number(run_value(runs, mode, "token_count")) is not None
                else None
            ),
            "millions",
            None,
        ),
        ("Commands", lambda mode, runs: activity_value(runs, mode, "command_count"), "int", None),
        ("Structure score", lambda mode, runs: structure_score(runs[mode]), "percent", 100),
        (validation_metric_chart_title(runs), lambda mode, runs: reported_metric_value(runs[mode]), "validation", None),
        ("Evaluator pass", lambda mode, runs: evaluator_bool_numeric(runs[mode], "eval_passed"), "bool", 1),
        ("Evaluator score", lambda mode, runs: evaluator_score_value(runs[mode]), "score", 5),
        ("Conversion quality", lambda mode, runs: evaluator_process_value(runs[mode], "conversion_quality"), "int", 5),
        ("Mandatory pass", lambda mode, runs: evaluator_behavior_rate(runs[mode], "mandatory_behavior"), "rate", 1),
        (
            "Validation cmds",
            lambda mode, runs: evaluator_process_value(runs[mode], "validation_commands_run"),
            "int",
            None,
        ),
    ]


def embedded_bar_chart(runs: dict[str, dict[str, Any]]) -> str:
    modes = [mode for mode in REPORT_MODE_ORDER if mode in runs]
    colors = {
        SKILLS_EVAL_OFF_MODE: "#2563eb",
        SKILLS_EVAL_ON_MODE: "#dc2626",
        NO_SKILLS_MODE: "#16a34a",
    }
    fallback_colors = ["#7c3aed", "#0891b2", "#f59e0b", "#be123c", "#0f766e"]
    short_labels = {
        SKILLS_EVAL_OFF_MODE: "Eval off",
        SKILLS_EVAL_ON_MODE: "Eval on",
        NO_SKILLS_MODE: "No skills",
    }
    metric_groups = benchmark_chart_metrics(runs)
    width, height = 1180, 720
    margin_left, margin_top = 40, 115
    panel_w, panel_h = 210, 220
    gap_x, gap_y = 18, 58
    columns = 5
    bar_count = max(1, len(modes))
    bar_gap = 24 if bar_count <= 3 else 10
    available_bar_w = max(36, panel_w - 44)
    bar_w = max(12.0, min(34.0, (available_bar_w - bar_gap * (bar_count - 1)) / bar_count))
    bar_group_w = bar_count * bar_w + max(0, bar_count - 1) * bar_gap
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<text x="30" y="35" font-family="Arial, sans-serif" font-size="22" font-weight="700" fill="#111827">Benchmark Metrics Comparison</text>',
        '<text x="30" y="62" font-family="Arial, sans-serif" font-size="13" fill="#4b5563">Per-run metrics are shown directly. FL result status is shown even when no scalar bar can be drawn.</text>',
    ]
    for index, (metric_name, getter, kind, max_override) in enumerate(metric_groups):
        col = index % columns
        row = index // columns
        x0 = margin_left + col * (panel_w + gap_x)
        y0 = margin_top + row * (panel_h + gap_y)
        values = {mode: getter(mode, runs) for mode in modes}
        numeric_values = [as_number(value) for value in values.values()]
        numeric_values = [value for value in numeric_values if value is not None]
        max_value = max_override if max_override is not None else max(numeric_values) if numeric_values else 1
        if max_value == 0:
            max_value = 1
        axis_y = y0 + panel_h
        bar_start_x = x0 + max(14.0, (panel_w - bar_group_w) / 2)
        parts.extend(
            [
                f'<text x="{x0}" y="{y0}" font-family="Arial, sans-serif" font-size="16" font-weight="700" fill="#111827">{html.escape(metric_name)}</text>',
                f'<line x1="{x0}" y1="{axis_y}" x2="{x0 + panel_w}" y2="{axis_y}" stroke="#d1d5db" stroke-width="1"/>',
                f'<line x1="{x0}" y1="{y0 + 25}" x2="{x0}" y2="{axis_y}" stroke="#d1d5db" stroke-width="1"/>',
            ]
        )
        for bar_index, mode in enumerate(modes):
            value = as_number(values[mode])
            height_px = 0 if value is None else value / max_value * (panel_h - 62)
            bx = bar_start_x + bar_index * (bar_w + bar_gap)
            by = axis_y - height_px
            value_text = format_chart_value(value, kind, runs[mode])
            color = colors.get(mode, fallback_colors[bar_index % len(fallback_colors)])
            label = short_labels.get(mode, truncate(mode.replace("_", " "), 12))
            if value is None:
                missing_text = format_chart_value(value, kind, runs[mode])
                parts.extend(
                    [
                        f'<rect x="{bx:.1f}" y="{axis_y - 26}" width="{bar_w:.1f}" height="22" fill="#e5e7eb" rx="3"/>',
                        f'<text x="{bx + bar_w / 2}" y="{axis_y - 10}" text-anchor="middle" font-family="Arial, sans-serif" font-size="11" font-weight="700" fill="#4b5563">{html.escape(truncate(missing_text, 13))}</text>',
                        f'<text x="{bx + bar_w / 2}" y="{axis_y + 18}" text-anchor="middle" font-family="Arial, sans-serif" font-size="11" fill="#374151">{html.escape(label)}</text>',
                    ]
                )
            else:
                parts.extend(
                    [
                        f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bar_w:.1f}" height="{height_px:.1f}" fill="{color}" rx="3"/>',
                        f'<text x="{bx + bar_w / 2}" y="{by - 7:.1f}" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#111827">{html.escape(value_text)}</text>',
                        f'<text x="{bx + bar_w / 2}" y="{axis_y + 18}" text-anchor="middle" font-family="Arial, sans-serif" font-size="11" fill="#374151">{html.escape(label)}</text>',
                    ]
                )
    legend_y = height - 35
    for index, mode in enumerate(modes):
        legend_gap = min(230, max(120, (width - 140) / max(1, len(modes))))
        lx = 70 + index * legend_gap
        color = colors.get(mode, fallback_colors[index % len(fallback_colors)])
        parts.extend(
            [
                f'<rect x="{lx:.1f}" y="{legend_y}" width="14" height="14" fill="{color}" rx="2"/>',
                f'<text x="{lx + 22}" y="{legend_y + 12}" font-family="Arial, sans-serif" font-size="13" fill="#111827">{html.escape(runs[mode]["label"])}</text>',
            ]
        )
    parts.append("</svg>")
    return "\n".join(parts)


def table_row(name: str, values: list[Any]) -> str:
    return "| " + name + " | " + " | ".join(fmt_int(value) for value in values) + " |"


def markdown_cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def truncate(value: Any, limit: int = 150) -> str:
    text = str(value).strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def count_map(run: dict[str, Any], key: str) -> dict[str, Any]:
    activity = run.get("activity") if isinstance(run.get("activity"), dict) else {}
    value = activity.get(key)
    return value if isinstance(value, dict) else {}


def commands_for_run(run: dict[str, Any]) -> list[str]:
    activity = run.get("activity") if isinstance(run.get("activity"), dict) else {}
    commands = activity.get("commands")
    return [str(command) for command in commands] if isinstance(commands, list) else []


def hint_group_count(runs: dict[str, dict[str, Any]], mode: str, keys: list[str]) -> int:
    return sum(hint_count(runs, mode, key) for key in keys)


def no_skills_is_cheaper(runs: dict[str, dict[str, Any]]) -> bool:
    runtime_gap = safe_diff(
        run_value(runs, SKILLS_EVAL_OFF_MODE, "elapsed_seconds"),
        run_value(runs, NO_SKILLS_MODE, "elapsed_seconds"),
    )
    token_gap = safe_diff(
        run_value(runs, SKILLS_EVAL_OFF_MODE, "token_count"),
        run_value(runs, NO_SKILLS_MODE, "token_count"),
    )
    return bool((runtime_gap is not None and runtime_gap > 0) or (token_gap is not None and token_gap > 0))


def evaluator_record_count(run: dict[str, Any]) -> int:
    return len(evaluator_records(run))


def evaluator_record_count_display(run: dict[str, Any]) -> str:
    records = evaluator_records(run)
    if not records:
        return "0"
    record = primary_evaluator_record(run)
    path = str(record.get("_record_path") or "") if isinstance(record, dict) else ""
    latest = Path(path).name if path else "unknown"
    return f"{len(records)} (latest {latest})"


def significant_violation_count(run: dict[str, Any]) -> Any:
    record = primary_evaluator_record(run)
    violations = record.get("significant_violations") if isinstance(record, dict) else None
    return len(violations) if isinstance(violations, list) else None


def evaluator_metric_specs() -> (
    list[tuple[str, Callable[[dict[str, Any]], Any], Callable[[Any, dict[str, Any]], str], str]]
):
    return [
        (
            "Evaluator records",
            evaluator_record_count,
            lambda _value, run: evaluator_record_count_display(run),
            "Captured records; metric rows use the latest record.",
        ),
        (
            "Evaluator pass",
            lambda run: evaluator_bool_value(run, "eval_passed"),
            lambda value, _run: fmt_yes_no(value),
            "Final evaluator gate.",
        ),
        (
            "Evaluator score",
            evaluator_score_value,
            lambda value, run: fmt_score_value(value, evaluator_score_max(run)),
            "Rubric score from skill eval.",
        ),
        (
            "Conversion quality",
            lambda run: evaluator_process_value(run, "conversion_quality"),
            lambda value, _run: fmt_na(value),
            "Evaluator quality proxy.",
        ),
        (
            "Validation commands",
            lambda run: evaluator_process_value(run, "validation_commands_run"),
            lambda value, _run: fmt_na(value),
            "How much validation was checked.",
        ),
        (
            "First pass accepted",
            evaluator_first_pass_accepted,
            lambda value, _run: fmt_yes_no(value),
            "Whether evaluator saw an acceptable first result.",
        ),
        (
            "Turns to acceptable",
            lambda run: evaluator_process_value(run, "turns_to_acceptable"),
            lambda value, _run: fmt_na(value),
            "Correction-loop depth.",
        ),
        (
            "User corrections",
            lambda run: evaluator_process_value(run, "user_correction_count"),
            lambda value, _run: fmt_na(value),
            "Human intervention proxy.",
        ),
        (
            "Agent self-corrections",
            lambda run: evaluator_process_value(run, "agent_self_correction_count"),
            lambda value, _run: fmt_na(value),
            "Agent rework proxy.",
        ),
        (
            "Missed instructions",
            lambda run: evaluator_process_value(run, "missed_instruction_count"),
            lambda value, _run: fmt_na(value),
            "Instruction-following defects.",
        ),
        (
            "Workflow violations",
            lambda run: evaluator_process_value(run, "workflow_violations"),
            lambda value, _run: fmt_na(value),
            "Wrong-process defects.",
        ),
        (
            "Layout violations",
            lambda run: evaluator_process_value(run, "layout_violations"),
            lambda value, _run: fmt_na(value),
            "Generated-structure defects.",
        ),
        (
            "Evidence gaps",
            lambda run: evaluator_process_value(run, "evidence_gap_violations"),
            lambda value, _run: fmt_na(value),
            "Missing proof or validation evidence.",
        ),
        (
            "Mandatory pass rate",
            lambda run: evaluator_behavior_rate(run, "mandatory_behavior"),
            lambda value, _run: fmt_rate_value(value),
            "Required behavior coverage.",
        ),
        (
            "Prohibited avoidance",
            lambda run: evaluator_behavior_rate(run, "prohibited_behavior"),
            lambda value, _run: fmt_rate_value(value),
            "Avoided forbidden behavior.",
        ),
        (
            "Significant violations",
            significant_violation_count,
            lambda value, _run: fmt_na(value),
            "High-severity evaluator findings.",
        ),
    ]


def value_available(value: Any) -> bool:
    return value is not None


def evaluator_metric_availability_table(runs: dict[str, dict[str, Any]], modes: list[str]) -> str:
    lines = [
        "| Eval metric | " + " | ".join(REPORT_COL_LABELS[mode] for mode in modes) + " | What it tells us |",
        "| --- | " + " | ".join("---" for _ in modes) + " | --- |",
    ]
    for label, getter, formatter, note in evaluator_metric_specs():
        values = {mode: getter(runs[mode]) for mode in modes}
        lines.append(
            f"| {label} | "
            + " | ".join(markdown_cell(formatter(values[mode], runs[mode])) for mode in modes)
            + f" | {markdown_cell(note)} |"
        )
    return "\n".join(lines)


def evaluator_score_rationale_table(runs: dict[str, dict[str, Any]], modes: list[str]) -> str:
    lines = [
        "| Run | Evaluator score | FL result quality gate | Why the score/outcome is reduced |",
        "| --- | ---: | --- | --- |",
    ]
    for mode in modes:
        lines.append(
            f"| {REPORT_COL_LABELS[mode]} | "
            f"{fmt_score_value(evaluator_score_value(runs[mode]), evaluator_score_max(runs[mode]))} | "
            f"{markdown_cell(benchmark_outcome(runs[mode]))} | "
            f"{markdown_cell(evaluator_score_rationale(runs[mode]))} |"
        )
    return "\n".join(lines)


def outcome_metrics_table(runs: dict[str, dict[str, Any]], modes: list[str]) -> str:
    rows = [
        ("Agent process", lambda run: process_pass_display(run)),
        ("Evaluator availability", lambda run: evaluator_availability_display(run)),
        ("Evaluator pass", lambda run: fmt_yes_no(evaluator_bool_value(run, "eval_passed"))),
        ("Evaluator source", lambda run: (run.get("record") or {}).get("eval_passed_source") or "unavailable"),
        (validation_metric_chart_title(runs), fl_result_status_display),
        ("FL result quality gate", benchmark_outcome),
    ]
    lines = [
        "| Metric | " + " | ".join(REPORT_COL_LABELS[mode] for mode in modes) + " |",
        "| --- | " + " | ".join("---" for _ in modes) + " |",
    ]
    for label, getter in rows:
        lines.append(f"| {label} | " + " | ".join(markdown_cell(getter(runs[mode])) for mode in modes) + " |")
    return "\n".join(lines)


def evaluator_metric_summary(runs: dict[str, dict[str, Any]]) -> str:
    eval_on = runs[SKILLS_EVAL_ON_MODE]
    eval_on_only = [label for label, _value, _note in evaluator_added_signal_rows(runs)]
    unavailable = []
    for label, getter, _formatter, _note in evaluator_metric_specs():
        if label == "Evaluator records":
            continue
        on_value = getter(eval_on)
        if not value_available(on_value):
            unavailable.append(label)
    parts = []
    if eval_on_only:
        parts.append(
            "Eval-on-only metrics: "
            + ", ".join(eval_on_only[:8])
            + ("." if len(eval_on_only) <= 8 else f", +{len(eval_on_only) - 8} more.")
        )
    if unavailable:
        parts.append(
            "Still unavailable in eval-on: "
            + ", ".join(unavailable[:6])
            + ("." if len(unavailable) <= 6 else f", +{len(unavailable) - 6} more.")
        )
    if not parts:
        parts.append("No evaluator-only metric gap was detected.")
    return " ".join(parts)


def evaluator_added_signal_rows(runs: dict[str, dict[str, Any]]) -> list[tuple[str, str, str]]:
    eval_on = runs[SKILLS_EVAL_ON_MODE]
    eval_off = runs[SKILLS_EVAL_OFF_MODE]
    no_skills = runs[NO_SKILLS_MODE]
    rows = []
    for label, getter, formatter, note in evaluator_metric_specs():
        if label == "Evaluator records":
            continue
        on_value = getter(eval_on)
        off_value = getter(eval_off)
        no_skills_value = getter(no_skills)
        if value_available(on_value) and not value_available(off_value) and not value_available(no_skills_value):
            rows.append((label, formatter(on_value, eval_on), note))
    return rows


def evaluator_added_signal_summary(runs: dict[str, dict[str, Any]]) -> str:
    rows = evaluator_added_signal_rows(runs)
    if not rows:
        return "Skill eval produced no evaluator-only metrics in this artifact."
    preferred = {
        "Evaluator pass",
        "Evaluator score",
        "Conversion quality",
        "Validation commands",
        "Missed instructions",
        "Mandatory pass rate",
        "Prohibited avoidance",
    }
    important = [f"{label}={value}" for label, value, _note in rows if label in preferred]
    if not important:
        important = [f"{label}={value}" for label, value, _note in rows[:6]]
    suffix = "" if len(rows) <= len(important) else f"; +{len(rows) - len(important)} more eval-only signals"
    return ", ".join(important) + suffix + "."


def skill_eval_extra_cost_summary(runs: dict[str, dict[str, Any]]) -> str:
    if not runs[SKILLS_EVAL_ON_MODE].get("available"):
        return "skill eval-on run unavailable"
    parts = []
    for baseline_mode, label in (
        (SKILLS_EVAL_OFF_MODE, "vs skill eval off"),
        (NO_SKILLS_MODE, "vs no skills"),
    ):
        if not runs[baseline_mode].get("available"):
            continue
        runtime_delta = safe_diff(
            run_value(runs, SKILLS_EVAL_ON_MODE, "elapsed_seconds"),
            run_value(runs, baseline_mode, "elapsed_seconds"),
        )
        token_delta = safe_diff(
            run_value(runs, SKILLS_EVAL_ON_MODE, "token_count"),
            run_value(runs, baseline_mode, "token_count"),
        )
        parts.append(f"{label}: {fmt_signed_int(runtime_delta, 's')}, {fmt_signed_short(token_delta, ' tokens')}")
    return "; ".join(parts) if parts else "no baseline run available for cost delta"


def evaluator_added_signal_table(runs: dict[str, dict[str, Any]]) -> str:
    rows = evaluator_added_signal_rows(runs)
    if not rows:
        return "No eval-on-only evaluator metrics were captured."
    lines = [
        "| Eval-on-only signal | Value | Why it matters |",
        "| --- | ---: | --- |",
    ]
    for label, value, note in rows:
        lines.append(f"| {markdown_cell(label)} | {markdown_cell(value)} | {markdown_cell(note)} |")
    return "\n".join(lines)


def append_no_skills_advantage_analysis(lines: list[str], runs: dict[str, dict[str, Any]]) -> None:
    if not no_skills_is_cheaper(runs):
        return

    compared = SKILLS_EVAL_OFF_MODE
    baseline = NO_SKILLS_MODE
    runtime_delta = safe_diff(
        run_value(runs, compared, "elapsed_seconds"), run_value(runs, baseline, "elapsed_seconds")
    )
    token_delta = safe_diff(run_value(runs, compared, "token_count"), run_value(runs, baseline, "token_count"))
    no_skills_faster = runtime_delta is not None and runtime_delta > 0
    no_skills_lower_tokens = token_delta is not None and token_delta > 0

    if no_skills_faster and no_skills_lower_tokens:
        title = "Why No Skills Was Lower Runtime and Lower Token Than Skills Eval-Off"
    elif no_skills_faster:
        title = "Why No Skills Was Faster Than Skills Eval-Off"
    elif no_skills_lower_tokens:
        title = "Why No Skills Used Fewer Tokens Than Skills Eval-Off"
    else:
        title = "No-Skills Cost Comparison"
    lines.append(f"## {title}")
    lines.append("")
    lines.append(
        "This section separates cost facts from explanatory signals. A higher command count is not automatically the cause of higher runtime; when the faster run has more commands, command volume is a counter-signal and the likely cause shifts toward longer-running commands, model latency, or skill/meta-workflow detours."
    )
    lines.append("")
    baseline_commands = activity_value(runs, baseline, "command_count")
    compared_commands = activity_value(runs, compared, "command_count")
    cost_rows = [
        ("Elapsed seconds", lambda mode: run_value(runs, mode, "elapsed_seconds"), fmt_int),
        ("Total tokens", lambda mode: run_value(runs, mode, "token_count"), fmt_short),
        ("Commands", lambda mode: activity_value(runs, mode, "command_count"), fmt_int),
        (
            "Seconds per command",
            lambda mode: (
                safe_diff(run_value(runs, mode, "elapsed_seconds"), 0) / activity_value(runs, mode, "command_count")
                if as_number(activity_value(runs, mode, "command_count"))
                else None
            ),
            fmt_one_decimal,
        ),
        ("Unique commands", lambda mode: activity_value(runs, mode, "unique_command_count"), fmt_int),
        ("Events", lambda mode: activity_value(runs, mode, "event_count"), fmt_int),
        (
            "Changed/generated files",
            lambda mode: (runs[mode].get("workspace_delta") or {}).get("changed_file_count"),
            fmt_int,
        ),
        (
            "Runtime artifacts",
            lambda mode: (runs[mode].get("workspace_delta") or {}).get("runtime_artifact_count"),
            fmt_int,
        ),
    ]
    lines.append("| Cost signal | No skills baseline | Skills, skill eval off |")
    lines.append("| --- | ---: | ---: |")
    for label, getter, formatter in cost_rows:
        lines.append(
            f"| {markdown_cell(label)} | {markdown_cell(formatter(getter(baseline)))} | {markdown_cell(formatter(getter(compared)))} |"
        )
    lines.append("")

    signal_rows = [
        (
            "Skill docs and references",
            hint_group_count(runs, compared, ["skill_md", "skill_references", "benchmark_md"]),
            hint_group_count(runs, baseline, ["skill_md", "skill_references", "benchmark_md"]),
            "The skills run spent context on skill material before or during conversion.",
            "No-skills had more skill-doc hits, which would be unexpected; inspect command logs before using this as an explanation.",
        ),
        (
            "Evaluator-adjacent material",
            hint_group_count(runs, compared, ["skill_evals", "agent_inspect", "agent_skill_install_or_list"]),
            hint_group_count(runs, baseline, ["skill_evals", "agent_inspect", "agent_skill_install_or_list"]),
            "Eval-off should not need much evaluator/dev-surface exploration; extra hits suggest a meta-workflow detour.",
            "No-skills had more evaluator-adjacent hits, so evaluator/dev-surface exploration does not explain skills overhead in this artifact.",
        ),
        (
            "Filesystem discovery",
            hint_group_count(runs, compared, ["shell_find", "shell_rg", "shell_cat_or_sed"]),
            hint_group_count(runs, baseline, ["shell_find", "shell_rg", "shell_cat_or_sed"]),
            "More search/read operations mean the agent widened its discovery scope.",
            "No-skills did more search/read work, so discovery volume does not explain why skills eval-off took longer.",
        ),
        (
            "Validation loop signals",
            hint_group_count(runs, compared, ["simulation", "py_compile", "python_job_py"]),
            hint_group_count(runs, baseline, ["simulation", "py_compile", "python_job_py"]),
            "More compile/simulation/job execution references indicate extra verification cycles.",
            "No-skills had more validation-loop signals, so validation volume does not explain why skills eval-off took longer.",
        ),
        (
            "Agent messages",
            event_type(runs, compared, "agent_message"),
            event_type(runs, baseline, "agent_message"),
            "More assistant turns usually correlate with planning, re-planning, or explanatory overhead.",
            "No-skills had more assistant turns, so turn count does not explain why skills eval-off took longer.",
        ),
        (
            "Command executions",
            event_type(runs, compared, "command_execution"),
            event_type(runs, baseline, "command_execution"),
            "Skills executed more commands, which can add operational latency.",
            "No-skills executed more commands, so command volume does not explain why skills eval-off took longer.",
        ),
        (
            "File-change events",
            event_type(runs, compared, "file_change"),
            event_type(runs, baseline, "file_change"),
            "More edits can mean a broader or less direct implementation path.",
            "No-skills had more edit events, so edit count does not explain why skills eval-off took longer.",
        ),
    ]
    visible_signal_rows = [
        row for row in signal_rows if as_number(row[1]) not in (None, 0) or as_number(row[2]) not in (None, 0)
    ]
    if visible_signal_rows:
        visible_signal_rows.sort(
            key=lambda row: (
                0 if (as_number(row[1]) or 0) > (as_number(row[2]) or 0) else 1,
                -abs((as_number(row[1]) or 0) - (as_number(row[2]) or 0)),
                row[0],
            )
        )
        lines.append("| Work signal | No skills baseline | Skills, skill eval off | Direction | What it means |")
        lines.append("| --- | ---: | ---: | --- | --- |")
        for (
            label,
            compared_value,
            baseline_value,
            compared_interpretation,
            baseline_interpretation,
        ) in visible_signal_rows[:8]:
            compared_num = as_number(compared_value) or 0
            baseline_num = as_number(baseline_value) or 0
            delta = compared_num - baseline_num
            if delta > 0:
                direction = f"skills +{fmt_int(delta)}"
                interpretation = compared_interpretation
            elif delta < 0:
                direction = f"no-skills +{fmt_int(abs(delta))}"
                interpretation = baseline_interpretation
            else:
                direction = "same"
                interpretation = "No directional difference; this signal does not explain the runtime gap."
            lines.append(
                f"| {markdown_cell(label)} | {fmt_int(baseline_value)} | {fmt_int(compared_value)} | {markdown_cell(direction)} | {markdown_cell(interpretation)} |"
            )
        lines.append("")

    prefix_rows = []
    compared_prefixes = count_map(runs[compared], "command_prefix_counts")
    baseline_prefixes = count_map(runs[baseline], "command_prefix_counts")
    for prefix in sorted(set(compared_prefixes) | set(baseline_prefixes)):
        compared_value = compared_prefixes.get(prefix, 0)
        baseline_value = baseline_prefixes.get(prefix, 0)
        if as_number(compared_value) or as_number(baseline_value):
            prefix_rows.append((prefix, compared_value, baseline_value))
    prefix_rows.sort(key=lambda item: (-(as_number(item[1]) or 0), item[0]))
    if prefix_rows:
        lines.append("| Command prefix usage | No skills baseline | Skills, skill eval off |")
        lines.append("| --- | ---: | ---: |")
        for prefix, compared_value, baseline_value in prefix_rows[:8]:
            lines.append(f"| `{markdown_cell(prefix)}` | {fmt_int(baseline_value)} | {fmt_int(compared_value)} |")
        lines.append("")

    baseline_command_set = set(commands_for_run(runs[baseline]))
    extra_commands = []
    for command in commands_for_run(runs[compared]):
        if command not in baseline_command_set and command not in extra_commands:
            extra_commands.append(command)
    if extra_commands:
        lines.append("Representative commands that appeared only in the skills/skill-eval-off run:")
        lines.append("")
        for command in extra_commands[:6]:
            lines.append(f"- `{markdown_cell(truncate(command, 180))}`")
        lines.append("")

    skill_meta_compared = hint_group_count(
        runs, compared, ["skill_md", "skill_references", "skill_evals", "agent_inspect", "benchmark_md"]
    )
    skill_meta_baseline = hint_group_count(
        runs, baseline, ["skill_md", "skill_references", "skill_evals", "agent_inspect", "benchmark_md"]
    )
    evaluator_adjacent_compared = hint_group_count(
        runs, compared, ["skill_evals", "agent_inspect", "agent_skill_install_or_list"]
    )
    evaluator_adjacent_baseline = hint_group_count(
        runs, baseline, ["skill_evals", "agent_inspect", "agent_skill_install_or_list"]
    )
    validation_compared = hint_group_count(runs, compared, ["simulation", "py_compile", "python_job_py"])
    validation_baseline = hint_group_count(runs, baseline, ["simulation", "py_compile", "python_job_py"])
    discovery_compared = hint_group_count(runs, compared, ["shell_find", "shell_rg", "shell_cat_or_sed"])
    discovery_baseline = hint_group_count(runs, baseline, ["shell_find", "shell_rg", "shell_cat_or_sed"])

    lines.append("What this telemetry can and cannot prove:")
    lines.append("")
    lines.append(
        "- Observed cost levels: "
        f"no-skills {fmt_int(run_value(runs, baseline, 'elapsed_seconds'))}s, "
        f"{fmt_short(run_value(runs, baseline, 'token_count'))} tokens, "
        f"{fmt_int(activity_value(runs, baseline, 'command_count'))} commands; "
        f"skills eval-off {fmt_int(run_value(runs, compared, 'elapsed_seconds'))}s, "
        f"{fmt_short(run_value(runs, compared, 'token_count'))} tokens, "
        f"{fmt_int(activity_value(runs, compared, 'command_count'))} commands."
    )
    if runtime_delta is not None:
        lines.append(
            f"- Measured runtime gap: skills eval-off was {fmt_signed_int(runtime_delta, 's')} relative to no-skills."
        )
    if (
        as_number(compared_commands) is not None
        and as_number(baseline_commands) is not None
        and as_number(compared_commands) < as_number(baseline_commands)
    ):
        lines.append(
            "- Command count is a counter-signal: skills eval-off was slower despite fewer commands. The report must not explain the runtime gap with command volume."
        )
    if token_delta is not None and token_delta < 0:
        lines.append(
            f"- Token use is also a counter-signal: skills eval-off used {fmt_short(abs(token_delta))} fewer tokens than no-skills. This artifact shows a wall-clock runtime gap, not a broad cost gap."
        )
    candidate_parts = []
    if skill_meta_compared > skill_meta_baseline:
        candidate_parts.append(f"skill/meta hits {fmt_int(skill_meta_baseline)}->{fmt_int(skill_meta_compared)}")
    if discovery_compared > discovery_baseline:
        candidate_parts.append(f"discovery/read/search {fmt_int(discovery_baseline)}->{fmt_int(discovery_compared)}")
    if validation_compared > validation_baseline:
        candidate_parts.append(
            f"validation-loop signals {fmt_int(validation_baseline)}->{fmt_int(validation_compared)}"
        )
    if evaluator_adjacent_compared > evaluator_adjacent_baseline:
        candidate_parts.append(
            f"evaluator-adjacent hits {fmt_int(evaluator_adjacent_baseline)}->{fmt_int(evaluator_adjacent_compared)}"
        )
    if candidate_parts:
        lines.append(
            "- Candidate skills-run overhead signals: "
            + "; ".join(candidate_parts)
            + ". These show what the skills run touched, but they are not elapsed-time attribution."
        )
        lines.append(
            "- Best defensible read: the runtime gap may come from a small number of longer skill/meta commands, model/runtime waiting around those steps, or other unclassified latency. The current artifact does not prove which one."
        )
    else:
        lines.append(
            "- No dominant skills-specific activity category is visible. The current telemetry is insufficient for a root-cause claim."
        )
    lines.append(
        "- To prove root cause, the harness needs per-command duration and step-level model/runtime timing, not just aggregate counts."
    )
    lines.append("")


def process_eval_report(root: Path, runs: dict[str, dict[str, Any]]) -> str:
    runs = {mode: dict(run) for mode, run in runs.items()}
    modes = REPORT_MODE_ORDER
    extra_run_names = collect_extra_run_names(root, set(modes))
    missing_modes = [mode for mode in modes if not runs[mode].get("available")]
    event_totals: Counter[str] = Counter()
    for mode in modes:
        event_types = runs[mode]["activity"].get("event_types")
        if isinstance(event_types, dict):
            event_totals.update(event_types)

    expected_metric = None
    for mode in modes:
        record = runs[mode].get("record") or {}
        policy = record.get("validation_metric_policy") if isinstance(record, dict) else None
        if isinstance(policy, dict) and policy.get("expected_primary_metric"):
            expected_metric = canonical_metric_name(policy["expected_primary_metric"])
            break
    for mode in modes:
        metric = runs[mode].get("validation_metric")
        parsed_metric = reported_validation_metric(runs[mode]["last_message"], expected_metric)
        if isinstance(parsed_metric, dict) and parsed_metric.get("name"):
            metric = parsed_metric
        elif not isinstance(metric, dict) or not metric.get("name"):
            metric = parsed_metric
        runs[mode]["validation_metric"] = metric
        runs[mode]["validation_metric_aligned"] = (
            bool(expected_metric)
            and canonical_metric_name(metric.get("name")) == canonical_metric_name(expected_metric)
            and (metric_has_value(metric) or metric_reported_value_count(metric) > 0)
        )

    runtime_winner = lowest_mode(modes, lambda mode: run_value(runs, mode, "elapsed_seconds"))
    token_winner = lowest_mode(modes, lambda mode: run_value(runs, mode, "token_count"))
    fl_algorithm = algorithm_consensus(runs, modes)

    def values(fn: Callable[[str], Any]) -> list[Any]:
        return [fn(mode) for mode in modes]

    lines: list[str] = []
    lines.append("# NVFLARE Codex Benchmark Insights Report")
    lines.append("")
    lines.append(f"Result root: `{root}`")
    lines.append(f"FL algorithm under test: **{markdown_cell(fl_algorithm)}**")
    lines.append("")
    lines.append("This report is configured for three benchmark runs:")
    lines.append("")
    lines.append(
        "| Run label | Raw run name | Agent | Model | Skills | Harness process flag | NVFLARE skill eval | Agent exit | Agent report exit | Final container exit | Wrapper status |"
    )
    lines.append("| --- | --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: |")
    for mode in modes:
        run = runs[mode]
        lines.append(
            f"| {run['label']} | `{mode}` | {markdown_cell(agent_display(run))} | {markdown_cell(agent_model_display(run))} | "
            f"{run['skills']} | {run['process_eval']} | {run['skill_eval']} | "
            f"{run_value(runs, mode, 'codex_exit_code')} | "
            f"{run_value(runs, mode, 'agent_report_exit_code')} | "
            f"{run_value(runs, mode, 'final_container_exit_code')} | {run['status']} |"
        )
    lines.append("")
    lines.append(
        "Available runs used the benchmark prompt copied into each run's `prompt.txt`; the FL algorithm below is read from harness/request metadata. Agent-generated conversion artifacts are not used to decide the reported benchmark algorithm."
    )
    lines.append("")
    lines.append("## Executive Summary")
    lines.append("")
    lines.append("| Topic | Summary |")
    lines.append("| --- | --- |")
    completed = [
        mode for mode in modes if runs[mode].get("available") and run_value(runs, mode, "codex_exit_code") == 0
    ]
    if missing_modes:
        lines.append("| Missing runs | " + ", ".join(REPORT_COL_LABELS[mode] for mode in missing_modes) + ". |")
    if extra_run_names:
        lines.append(
            "| Additional runs | "
            + markdown_cell(
                "Ignored by this three-mode comparison report: " + ", ".join(f"`{name}`" for name in extra_run_names)
            )
            + ". |"
        )
    available_modes = [mode for mode in modes if runs[mode].get("available")]
    lines.append("| Status | " + markdown_cell(status_summary(runs, modes)) + " |")
    failed_available_modes = [mode for mode in available_modes if run_failed(runs[mode])]
    if failed_available_modes:
        lines.append(
            "| Likely root cause | "
            + markdown_cell(
                "; ".join(
                    f"{REPORT_COL_LABELS[mode]}: {failure_root_cause(runs[mode])}" for mode in failed_available_modes
                )
            )
            + " |"
        )
    lines.append("| FL result quality gate | " + markdown_cell(benchmark_outcome_summary(runs, modes)) + " |")
    lines.append(f"| FL algorithm | **{markdown_cell(fl_algorithm)}** |")
    lines.append("| Source input protection | " + markdown_cell(source_input_protection_summary(runs, modes)) + " |")
    if result_issue_modes(runs, modes):
        lines.append("| Missing/partial result metrics | " + markdown_cell(result_issue_summary(runs, modes)) + " |")
    agent_bits = [
        f"{REPORT_COL_LABELS[mode]}={agent_display(runs[mode])}/{agent_model_display(runs[mode])}"
        for mode in available_modes or modes
    ]
    lines.append("| Agent/model | " + markdown_cell("; ".join(agent_bits)) + " |")
    available_modes = [mode for mode in modes if runs[mode].get("available")]
    if len(completed) != len(available_modes):
        lines.append(
            "| Completion | "
            + markdown_cell(
                ", ".join(f"{REPORT_COL_LABELS[mode]}: {human_readable_status(runs[mode])}" for mode in available_modes)
            )
            + " |"
        )
    if runs[NO_SKILLS_MODE]["status"] != "0" and run_value(runs, NO_SKILLS_MODE, "codex_exit_code") == 0:
        lines.append(f"| Wrapper status | No-skills wrapper `{runs[NO_SKILLS_MODE]['status']}`, agent exit `0`. |")
    if runtime_winner and token_winner and runtime_winner == token_winner:
        lines.append(
            f"| Cost winner | {REPORT_COL_LABELS[runtime_winner]}: {fmt_int(run_value(runs, runtime_winner, 'elapsed_seconds'))}s, {fmt_short(run_value(runs, runtime_winner, 'token_count'))} tokens. |"
        )
    elif runtime_winner or token_winner:
        lines.append(
            "| Cost result | No single cost winner: "
            + f"fastest runtime is {REPORT_COL_LABELS[runtime_winner] if runtime_winner else 'NA'}"
            + (f" ({fmt_int(run_value(runs, runtime_winner, 'elapsed_seconds'))}s); " if runtime_winner else "; ")
            + f"lowest token use is {REPORT_COL_LABELS[token_winner] if token_winner else 'NA'}"
            + (f" ({fmt_short(run_value(runs, token_winner, 'token_count'))}). |" if token_winner else ". |")
        )
    else:
        lines.append("| Cost winner | NA. |")
    if runs[SKILLS_EVAL_ON_MODE].get("available") and runs[SKILLS_EVAL_OFF_MODE].get("available"):
        lines.append(
            "| Skill eval cost | "
            f"Skill eval off: {fmt_int(run_value(runs, SKILLS_EVAL_OFF_MODE, 'elapsed_seconds'))}s, "
            f"{fmt_short(run_value(runs, SKILLS_EVAL_OFF_MODE, 'token_count'))} tokens; "
            f"skill eval on: {fmt_int(run_value(runs, SKILLS_EVAL_ON_MODE, 'elapsed_seconds'))}s, "
            f"{fmt_short(run_value(runs, SKILLS_EVAL_ON_MODE, 'token_count'))} tokens. |"
        )
    else:
        lines.append("| Skill eval cost | NA; both with-skills modes are required. |")
    lines.append("| Evaluator metrics | " + markdown_cell(evaluator_metric_summary(runs)) + " |")
    lines.append(
        "| Skill eval added signals | "
        + markdown_cell(evaluator_added_signal_summary(runs))
        + " Cost delta "
        + markdown_cell(skill_eval_extra_cost_summary(runs))
        + ". |"
    )
    lines.append(
        "| Structure | "
        + "; ".join(f"{REPORT_COL_LABELS[mode]} {fmt_percent(structure_score(runs[mode]))}" for mode in modes)
        + ". |"
    )
    mismatched = [
        mode
        for mode in modes
        if runs[mode].get("available") and expected_metric and not runs[mode]["validation_metric_aligned"]
    ]
    if mismatched:
        lines.append(
            f"| README metric | Expected `{expected_metric}`; mismatch: "
            + ", ".join(
                f"{REPORT_COL_LABELS[mode]}={metric_display(runs[mode]['validation_metric'])}" for mode in mismatched
            )
            + ". |"
        )
    else:
        lines.append(f"| README metric | Expected `{expected_metric or 'NA'}`; no mismatch detected. |")
    lines.append("")
    failure_analysis = failure_analysis_section(runs, modes)
    if failure_analysis:
        lines.append(failure_analysis)
        lines.append("")
    missing_results = missing_result_metrics_section(runs, modes)
    if missing_results:
        lines.append(missing_results)
        lines.append("")
    lines.append("## Outcome Metrics")
    lines.append("")
    lines.append(
        "These metrics are intentionally separate: a run can have a passing agent process, no evaluator result, and still fail the FL-result quality gate when no scalar FL metric is available."
    )
    lines.append("")
    lines.append(outcome_metrics_table(runs, modes))
    lines.append("")
    lines.append("## Skill Eval Added Signals")
    lines.append("")
    lines.append(
        "These signals are only available from the with-skills/skill-eval-on run in this artifact. "
        "They are evaluator evidence about conversion quality and instruction-following, not FL training metrics."
    )
    lines.append("")
    lines.append(f"Extra cost: {skill_eval_extra_cost_summary(runs)}.")
    lines.append("")
    lines.append(evaluator_added_signal_table(runs))
    lines.append("")
    lines.append("### Evaluator Score Rationale")
    lines.append("")
    lines.append(
        "Evaluator pass/fail is reported as captured, but benchmark quality requires a scalar FL result metric. "
        "A missing scalar result fails the FL-result quality gate even when the evaluator record says the final code shape was accepted."
    )
    lines.append("")
    lines.append(evaluator_score_rationale_table(runs, modes))
    lines.append("")
    lines.append("## Metrics Comparison")
    lines.append("")
    lines.append(embedded_bar_chart(runs))
    lines.append("")
    lines.append("## Evaluator Metrics")
    lines.append("")
    lines.append(evaluator_metric_summary(runs))
    lines.append("")
    lines.append(evaluator_metric_availability_table(runs, modes))
    lines.append("")
    lines.append("## Compact Bar Snapshot")
    lines.append("")
    lines.append("Bars are scaled independently within each metric. Longer means more of that metric.")
    lines.append("")
    lines.append("```text")
    metric_groups = [
        ("Runtime seconds", {mode: run_value(runs, mode, "elapsed_seconds") for mode in modes}, False, None),
        ("Total tokens", {mode: run_value(runs, mode, "token_count") for mode in modes}, True, None),
        ("Commands", {mode: activity_value(runs, mode, "command_count") for mode in modes}, False, None),
        ("Structure score", {mode: structure_score(runs[mode]) for mode in modes}, False, 100),
    ]
    for title, metric_values, short, max_override in metric_groups:
        lines.append(title)
        numeric_values = [as_number(value) for value in metric_values.values()]
        numeric_values = [value for value in numeric_values if value is not None]
        maximum = max_override if max_override is not None else max(numeric_values) if numeric_values else None
        for mode in modes:
            label = runs[mode]["label"]
            value = metric_values[mode]
            display = (
                fmt_percent(value) if title == "Structure score" else fmt_short(value) if short else fmt_int(value)
            )
            lines.append(f"{label:<28} {display:>8}  | {bar(value, maximum)}")
        lines.append("")
    if lines[-1] == "":
        lines.pop()
    lines.append("```")
    lines.append("")
    lines.append("## FL Algorithm")
    lines.append("")
    lines.append(
        "This is the federated learning aggregation algorithm requested or reported for the conversion. Keep this value visible when comparing results across different benchmark prompts or jobs."
    )
    lines.append("")
    lines.append("| Run | Algorithm | Source |")
    lines.append("| --- | --- | --- |")
    for mode in modes:
        signal = runs[mode].get("algorithm_signal") if isinstance(runs[mode].get("algorithm_signal"), dict) else {}
        lines.append(
            f"| {runs[mode]['label']} | {markdown_cell(signal.get('algorithm') or 'n/a')} | {markdown_cell(signal.get('source') or 'n/a')} |"
        )
    lines.append("")
    lines.append("## Key Metrics")
    lines.append("")
    lines.append("| Metric | " + " | ".join(REPORT_COL_LABELS[mode] for mode in modes) + " |")
    lines.append("| --- | ---: | ---: | ---: |")
    lines.append("| Agent | " + " | ".join(markdown_cell(agent_display(runs[mode])) for mode in modes) + " |")
    lines.append("| Model | " + " | ".join(markdown_cell(agent_model_display(runs[mode])) for mode in modes) + " |")
    lines.append(
        "| Agent process | " + " | ".join(markdown_cell(process_pass_display(runs[mode])) for mode in modes) + " |"
    )
    lines.append(
        "| Evaluator availability | "
        + " | ".join(markdown_cell(evaluator_availability_display(runs[mode])) for mode in modes)
        + " |"
    )
    lines.append(
        "| FL result quality gate | "
        + " | ".join(markdown_cell(benchmark_outcome(runs[mode])) for mode in modes)
        + " |"
    )
    lines.append(
        "| FL algorithm | " + " | ".join(markdown_cell(algorithm_display(runs[mode])) for mode in modes) + " |"
    )
    lines.append(
        "| Source input protection | "
        + " | ".join(markdown_cell(source_input_protection_display(runs[mode])) for mode in modes)
        + " |"
    )
    lines.append(
        "| Copied workspace changes | "
        + " | ".join(markdown_cell(workspace_change_display(runs[mode])) for mode in modes)
        + " |"
    )
    rows = [
        ("Elapsed seconds", lambda mode: run_value(runs, mode, "elapsed_seconds")),
        ("Agent exit", lambda mode: run_value(runs, mode, "codex_exit_code")),
        ("Agent report exit", lambda mode: run_value(runs, mode, "agent_report_exit_code")),
        ("Final container exit", lambda mode: run_value(runs, mode, "final_container_exit_code")),
        ("Agent runtime seconds", lambda mode: phase_value(runs, mode, "agent_runtime")),
        ("Total tokens", lambda mode: run_value(runs, mode, "token_count")),
        ("Max input tokens", lambda mode: usage_value(runs, mode, "max_input_tokens")),
        ("Max output tokens", lambda mode: usage_value(runs, mode, "max_output_tokens")),
        ("Events", lambda mode: activity_value(runs, mode, "event_count")),
        ("Commands", lambda mode: activity_value(runs, mode, "command_count")),
        ("Unique commands", lambda mode: activity_value(runs, mode, "unique_command_count")),
        ("Structure score", lambda mode: structure_score(runs[mode])),
        ("File changes", lambda mode: event_type(runs, mode, "file_change")),
        ("Agent messages", lambda mode: event_type(runs, mode, "agent_message")),
        ("Skill report time seconds", lambda mode: phase_value(runs, mode, "skill_reports")),
    ]
    for name, fn in rows:
        if name == "Structure score":
            lines.append("| Structure score | " + " | ".join(fmt_percent(value) for value in values(fn)) + " |")
        else:
            lines.append(table_row(name, values(fn)))
    lines.append(
        "| Structure required files | "
        + " | ".join(markdown_cell(structure_required_display(runs[mode])) for mode in modes)
        + " |"
    )
    lines.append(
        "| Structure optional files | "
        + " | ".join(markdown_cell(structure_optional_display(runs[mode])) for mode in modes)
        + " |"
    )
    lines.append(
        "| Reported validation metric | "
        + " | ".join(metric_display(runs[mode]["validation_metric"]) for mode in modes)
        + " |"
    )
    lines.append(
        "| Additional validation metric values from final message | "
        + " | ".join(additional_metric_values_display(runs[mode]["validation_metric"]) for mode in modes)
        + " |"
    )
    lines.append(
        "| Evaluator records | "
        + " | ".join(markdown_cell(evaluator_record_count_display(runs[mode])) for mode in modes)
        + " |"
    )
    lines.append(
        "| Evaluator pass | "
        + " | ".join(fmt_yes_no(evaluator_bool_value(runs[mode], "eval_passed")) for mode in modes)
        + " |"
    )
    lines.append(
        "| Evaluator score | "
        + " | ".join(
            fmt_score_value(evaluator_score_value(runs[mode]), evaluator_score_max(runs[mode])) for mode in modes
        )
        + " |"
    )
    lines.append(
        "| Conversion quality | "
        + " | ".join(fmt_na(evaluator_process_value(runs[mode], "conversion_quality")) for mode in modes)
        + " |"
    )
    lines.append(
        "| Validation commands | "
        + " | ".join(fmt_na(evaluator_process_value(runs[mode], "validation_commands_run")) for mode in modes)
        + " |"
    )
    lines.append(
        "| Mandatory pass rate | "
        + " | ".join(fmt_rate_value(evaluator_behavior_rate(runs[mode], "mandatory_behavior")) for mode in modes)
        + " |"
    )
    lines.append(
        "| Prohibited avoidance | "
        + " | ".join(fmt_rate_value(evaluator_behavior_rate(runs[mode], "prohibited_behavior")) for mode in modes)
        + " |"
    )
    lines.append(
        "| README primary metric alignment | "
        + " | ".join(
            ("pass" if runs[mode]["validation_metric_aligned"] else "fail") if expected_metric else "n/a"
            for mode in modes
        )
        + " |"
    )
    if expected_metric:
        lines.append(f"| README primary metric | `{expected_metric}` | `{expected_metric}` | `{expected_metric}` |")
    lines.append("")
    append_no_skills_advantage_analysis(lines, runs)
    lines.append("## Structure Correctness")
    lines.append("")
    lines.append(
        "The score checks only the ideal converted filenames `client.py`, `model.py`, and `job.py` from the captured final structure set. The inventory rows show observed file basenames by harness artifact category; counts such as `model.py (2 paths)` mean the same basename appears at multiple paths. Paths are intentionally hidden in the compact table, and no arbitrary Python filename is treated as a semantic component."
    )
    lines.append("")
    lines.append(structure_correctness_table(runs, modes))
    lines.append("")
    lines.append(structure_trees_section(runs, modes))
    lines.append("")
    lines.append("## Activity Insights")
    lines.append("")
    lines.append("| Activity signal | " + " | ".join(REPORT_COL_LABELS[mode] for mode in modes) + " | Interpretation |")
    lines.append("| --- | ---: | ---: | ---: | --- |")
    activity_rows = [
        (
            "Read commands (`cat`/`sed`/`nl`)",
            "shell_cat_or_sed",
            "Direct file-read behavior changed materially across modes.",
        ),
        ("`find` commands", "shell_find", "Filesystem discovery is a useful proxy for exploration overhead."),
        ("`rg` commands", "shell_rg", "Search use stayed low across runs."),
        (
            "Simulation references",
            "simulation",
            "Simulation activity helps separate useful validation from pure overhead.",
        ),
        ("Python compile checks", "py_compile", "Compile checks indicate validation effort."),
        ("Skill reference hits", "skill_references", "Only skills-enabled runs should show skill reference use."),
        (
            "Skill eval references",
            "skill_evals",
            "Shows interaction with skill-eval material, not necessarily successful quality scoring.",
        ),
        ("Agent inspect references", "agent_inspect", "Shows use of NVFLARE agent inspection."),
        ("Python job.py references", "python_job_py", "Shows repeated exercise of the generated job entry point."),
    ]
    for label, key, interpretation in activity_rows:
        lines.append(
            f"| {label} | " + " | ".join(str(hint_count(runs, mode, key)) for mode in modes) + " | "
            f"{interpretation} |"
        )
    lines.append("")
    lines.append("## Event Mix")
    lines.append("")
    lines.append("| Event type | " + " | ".join(REPORT_COL_LABELS[mode] for mode in modes) + " |")
    lines.append("| --- | ---: | ---: | ---: |")
    for key in ["command_execution", "item.completed", "item.started", "agent_message", "file_change", "todo_list"]:
        lines.append(f"| `{key}` | " + " | ".join(str(event_type(runs, mode, key)) for mode in modes) + " |")
    lines.append("")
    top_events = event_totals.most_common(5)
    if top_events:
        lines.append(
            "Across all runs, the dominant events were "
            + ", ".join(f"`{name}` with {count} total" for name, count in top_events)
            + "."
        )
    lines.append("")
    lines.append("## Quality And Outcome Notes")
    lines.append("")
    lines.append("| Signal | " + " | ".join(REPORT_COL_LABELS[mode] for mode in modes) + " |")
    lines.append("| --- | --- | --- | --- |")
    lines.append(
        "| Agent/wrapper outcome | "
        + " | ".join(markdown_cell(human_readable_status(runs[mode])) for mode in modes)
        + " |"
    )
    lines.append(
        "| Agent process | " + " | ".join(markdown_cell(process_pass_display(runs[mode])) for mode in modes) + " |"
    )
    lines.append(
        "| Evaluator availability | "
        + " | ".join(markdown_cell(evaluator_availability_display(runs[mode])) for mode in modes)
        + " |"
    )
    lines.append(
        "| FL result quality gate | "
        + " | ".join(markdown_cell(benchmark_outcome(runs[mode])) for mode in modes)
        + " |"
    )
    lines.append(
        "| Harness error | " + " | ".join(markdown_cell(harness_error_display(runs[mode])) for mode in modes) + " |"
    )
    lines.append(
        "| Source input protection | "
        + " | ".join(markdown_cell(source_input_protection_display(runs[mode])) for mode in modes)
        + " |"
    )
    lines.append(
        "| Copied workspace changes | "
        + " | ".join(markdown_cell(workspace_change_display(runs[mode])) for mode in modes)
        + " |"
    )
    lines.append(
        "| FL algorithm | " + " | ".join(markdown_cell(algorithm_display(runs[mode])) for mode in modes) + " |"
    )
    lines.append(
        "| Agent report exit | "
        + " | ".join(fmt_int(run_value(runs, mode, "agent_report_exit_code")) for mode in modes)
        + " |"
    )
    lines.append(
        "| Final container exit | "
        + " | ".join(fmt_int(run_value(runs, mode, "final_container_exit_code")) for mode in modes)
        + " |"
    )
    lines.append(
        "| Captured generated artifacts | " + " | ".join(artifact_summary(runs[mode]) for mode in modes) + " |"
    )
    lines.append(
        "| Structure required files | "
        + " | ".join(markdown_cell(structure_required_display(runs[mode])) for mode in modes)
        + " |"
    )
    lines.append(
        "| Structure optional files | "
        + " | ".join(markdown_cell(structure_optional_display(runs[mode])) for mode in modes)
        + " |"
    )
    lines.append(
        "| Validation metric from final message | "
        + " | ".join(metric_display(runs[mode]["validation_metric"]) for mode in modes)
        + " |"
    )
    lines.append(
        "| Additional validation metric values from final message | "
        + " | ".join(additional_metric_values_display(runs[mode]["validation_metric"]) for mode in modes)
        + " |"
    )
    lines.append(
        "| README primary metric alignment | "
        + " | ".join(
            ("pass" if runs[mode]["validation_metric_aligned"] else "fail") if expected_metric else "n/a"
            for mode in modes
        )
        + " |"
    )
    lines.append("| Evaluator-backed pass/fail | " + " | ".join(evaluator_display(runs[mode]) for mode in modes) + " |")
    lines.append("| Agent process record | " + " | ".join(record_display(runs[mode]) for mode in modes) + " |")
    lines.append("")
    lines.append(
        "The reported validation values are useful sanity checks, but they are not a substitute for a normalized evaluator. Metric choice is still a correctness signal: when the project README declares a primary metric, reporting a different metric should count against README-following and conversion correctness."
    )
    lines.append("")
    lines.append("## Interpretation")
    lines.append("")
    if runtime_winner and token_winner and runtime_winner == token_winner:
        lines.append(
            f"For this run, `{runtime_winner}` is the operational cost winner by runtime and token use. "
            "That is a cost result only; quality still needs to be judged against evaluator output and project instructions."
        )
    elif runtime_winner or token_winner:
        lines.append(
            f"For this run, runtime and token cost leaders differ: `{runtime_winner or 'n/a'}` is fastest, "
            f"while `{token_winner or 'n/a'}` uses the fewest tokens. Treat this as a split cost result, not a single winner; "
            "quality still needs to be judged against evaluator output and project instructions."
        )
    else:
        lines.append("Runtime and token winners cannot be determined because those metrics are unavailable.")
    lines.append(
        f"`{SKILLS_EVAL_ON_MODE}` measures NVFLARE skill-eval overhead relative to eval-off. That overhead may be worthwhile only when evaluator-grade quality signals justify the extra cost."
    )
    lines.append("")
    if (
        expected_metric
        and runs[NO_SKILLS_MODE].get("available")
        and not runs[NO_SKILLS_MODE]["validation_metric_aligned"]
    ):
        lines.append(
            f"The no-skills baseline outcome was {run_outcome(runs[NO_SKILLS_MODE])}; it reported {metric_display(runs[NO_SKILLS_MODE]['validation_metric'])} while the README primary metric is `{expected_metric}`. "
            "That should lower its instruction-following/correctness assessment even if its runtime or token cost is lower."
        )
    else:
        lines.append(
            "The no-skills baseline outcome should be read from its agent process exit code, wrapper status, final message, "
            "and captured artifact snapshot rather than from a job-specific assumption."
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate an insight-focused Markdown report for benchmark result roots."
    )
    parser.add_argument("result_root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    root = args.result_root.resolve()
    runs = collect_process_eval_runs(root)
    output = args.output or root / "benchmark_insights.md"
    output.write_text(process_eval_report(root, runs), encoding="utf-8")
    legacy_output = root / "direct_report.md"
    if legacy_output.exists() and legacy_output.resolve() != output.resolve():
        legacy_output.unlink()
    print(output)


if __name__ == "__main__":
    main()
