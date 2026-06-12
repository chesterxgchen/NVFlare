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

"""Record-driven benchmark insight report."""

from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path
from typing import Any

from ..common import load_json
from ..metric_artifacts import validation_metric_from_workspace_delta_manifest
from ..modes import BENCHMARK_RUNS, mode_names
from ..quality_signals import (
    canonical_metric_name,
    is_fl_summary_metric_label,
    is_numeric_metric_value,
    is_plausible_metric_value,
    metric_value_entries,
    reported_metric_payload,
)

MODE_LABELS = {spec.mode: spec.label for spec in BENCHMARK_RUNS}
REQUIRED_STRUCTURE_FILES = ("client.py", "model.py", "job.py")
OPTIONAL_STRUCTURE_FILES = ("prepare_data.py", "download_data.py")
CONFIG_STRUCTURE_SUFFIXES = (".cfg", ".ini", ".json", ".toml", ".yaml", ".yml")
TREE_SOURCE_SUFFIXES = (".py",)
TREE_RUNTIME_SUFFIXES = (".py",) + CONFIG_STRUCTURE_SUFFIXES
OBSERVED_METRIC_NAMES = ("AUROC", "accuracy", "loss", "f1")
ANSI_ESCAPE_PATTERN = re.compile(r"\x1b\[[0-9;]*m")
MAX_AGENT_EVENTS_TEXT_BYTES = 20 * 1024 * 1024


def read_text(path: Path, *, max_bytes: int | None = None) -> str:
    try:
        if max_bytes is None:
            return path.read_text(encoding="utf-8", errors="replace")
        with path.open("rb") as stream:
            return stream.read(max_bytes).decode("utf-8", errors="replace")
    except Exception:
        return ""


def markdown_cell(value: Any) -> str:
    text = "NA" if value is None or value == "" else str(value)
    return text.replace("|", "\\|").replace("\n", "<br>")


def fmt_number(value: Any) -> str:
    if isinstance(value, bool) or value is None:
        return "NA"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number.is_integer():
        return str(int(number))
    return f"{number:.4f}"


def as_number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def fmt_short(value: Any) -> str:
    number = as_number(value)
    if number is None:
        return "NA"
    abs_value = abs(number)
    sign = "-" if number < 0 else ""
    if abs_value >= 1_000_000:
        return f"{sign}{abs_value / 1_000_000:.1f}M"
    if abs_value >= 1_000:
        return f"{sign}{abs_value / 1_000:.1f}k"
    return str(int(number)) if number.is_integer() else f"{number:.1f}"


def fmt_percent(value: Any) -> str:
    number = as_number(value)
    if number is None:
        return "NA"
    return f"{number * 100:.0f}%"


def truncate(value: Any, limit: int = 180) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def first_non_empty(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return None


def mode_dir_for_benchmark(root: Path, mode: str) -> Path:
    legacy = root / mode
    if legacy.exists():
        return legacy

    run_plan = load_json(root / "run_plan.json", {}) or {}
    entries = (
        run_plan.get("entries") if isinstance(run_plan, dict) and isinstance(run_plan.get("entries"), list) else []
    )
    for entry in entries:
        if not isinstance(entry, dict) or str(entry.get("mode")) != mode:
            continue
        record_dir = entry.get("record_dir")
        if not record_dir:
            continue
        candidate = root / str(record_dir)
        if candidate.exists():
            return candidate

    records_root = root / "records"
    if records_root.exists():
        matches = sorted(records_root.glob(f"**/mode={mode}"))
        if len(matches) == 1:
            return matches[0]
    return legacy


def final_record_path(root: Path, mode: str) -> Path:
    mode_dir = mode_dir_for_benchmark(root, mode)
    benchmark_record = mode_dir / "benchmark_record.json"
    if benchmark_record.exists():
        return benchmark_record
    return mode_dir / "records" / f"{mode}_record.json"


def sanitized_validation_metric(metric: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(metric, dict) or not metric.get("name"):
        return metric if isinstance(metric, dict) else {}
    name = canonical_metric_name(metric.get("name"))
    entries = [entry for entry in metric.get("reported_value_entries") or [] if isinstance(entry, dict)]
    if not entries and is_numeric_metric_value(metric.get("value")):
        entry: dict[str, Any] = {"value": metric["value"]}
        if metric.get("summary_value_label"):
            entry["label"] = metric["summary_value_label"]
        entries = [entry]
    sanitized = reported_metric_payload(name, entries)
    sanitized["source"] = metric.get("source") or sanitized.get("source")
    return sanitized


def validation_metric_from_record(record: dict[str, Any]) -> dict[str, Any]:
    metric = record.get("validation_metric")
    if isinstance(metric, dict) and metric.get("name"):
        return sanitized_validation_metric(metric)
    metric = record.get("artifact_validation_metric")
    if isinstance(metric, dict) and metric.get("name"):
        return sanitized_validation_metric(metric)
    metric = record.get("reported_validation_metric")
    if isinstance(metric, dict) and metric.get("name"):
        return sanitized_validation_metric(metric)
    quality = record.get("quality_signals")
    if isinstance(quality, dict):
        signal = quality.get("job_guidance_primary_validation_metric") or quality.get(
            "readme_primary_validation_metric"
        )
        if isinstance(signal, dict):
            metric = signal.get("reported_validation_metric")
            if isinstance(metric, dict) and metric.get("name"):
                return sanitized_validation_metric(metric)
    return {}


def filter_mode_console(console_text: str, mode: str) -> str:
    if not console_text:
        return ""
    prefix = f"[{mode}] "
    lines = []
    for line in console_text.splitlines():
        if line.startswith(prefix):
            lines.append(line[len(prefix) :])
    return "\n".join(lines)


def collect_benchmark_runs(root: Path) -> dict[str, dict[str, Any]]:
    console_text = read_text(root / "console_output.log")
    runs: dict[str, dict[str, Any]] = {}
    run_plan = load_json(root / "run_plan.json", {}) or {}
    entries = (
        run_plan.get("entries") if isinstance(run_plan, dict) and isinstance(run_plan.get("entries"), list) else []
    )
    for spec in BENCHMARK_RUNS:
        mode = spec.mode
        run_plan_entry = next(
            (entry for entry in entries if isinstance(entry, dict) and str(entry.get("mode")) == mode),
            {},
        )
        mode_dir = mode_dir_for_benchmark(root, mode)
        mode_console_text = read_text(root / f"{mode}.console.log") or filter_mode_console(console_text, mode)
        summary = load_json(mode_dir / "run_summary.json", {}) if mode_dir.exists() else {}
        record = load_json(final_record_path(root, mode), {}) if mode_dir.exists() else {}
        workspace_delta_path = mode_dir / "workspace_delta_manifest.json"
        workspace_delta = load_json(workspace_delta_path, {}) if mode_dir.exists() else {}
        if not isinstance(summary, dict):
            summary = {}
        if not isinstance(record, dict):
            record = {}
        if not isinstance(workspace_delta, dict):
            workspace_delta = {}
        agent = first_non_empty(summary.get("agent"), record.get("agent"), run_plan_entry.get("agent"))
        agent_model = first_non_empty(
            summary.get("agent_model"),
            record.get("agent_model"),
            run_plan_entry.get("agent_model"),
        )
        record_metric = validation_metric_from_record(record)
        expected_metric = (
            record.get("validation_metric_policy", {}).get("expected_primary_metric")
            if isinstance(record.get("validation_metric_policy"), dict)
            else None
        )
        artifact_metric = validation_metric_from_workspace_delta_manifest(
            workspace_delta,
            workspace_delta_path,
            expected_metric,
        )
        runs[mode] = {
            "available": mode_dir.exists(),
            "mode": mode,
            "label": spec.label,
            "skills": "with skills" if spec.skills_enabled else "without skills",
            "agent": agent,
            "agent_model": agent_model,
            "model_source": first_non_empty(summary.get("model_source"), record.get("model_source"), run_plan_entry.get("model_source")),
            "run": summary,
            "record": record,
            "container_exit": load_json(mode_dir / "container_exit_code.json", {}) if mode_dir.exists() else {},
            "usage": load_json(mode_dir / "agent_usage.json", {}) if mode_dir.exists() else {},
            "activity": load_json(mode_dir / "agent_activity.json", {}) if mode_dir.exists() else {},
            "workspace_delta": workspace_delta,
            "runtime_image": load_json(mode_dir / "runtime_image.json", {}) if mode_dir.exists() else {},
            "agent_last_message": read_text(mode_dir / "agent_last_message.txt") if mode_dir.exists() else "",
            "agent_stderr": read_text(mode_dir / "agent_stderr.txt") if mode_dir.exists() else "",
            "agent_events_text": (
                read_text(mode_dir / "agent_events.jsonl", max_bytes=MAX_AGENT_EVENTS_TEXT_BYTES)
                if mode_dir.exists()
                else ""
            ),
            "console_text": mode_console_text,
            "validation_metric": artifact_metric or record_metric,
        }
    return runs


def run_identity_table(runs: dict[str, dict[str, Any]], modes: list[str]) -> str:
    lines = [
        "| Run | Agent | Model | Model source | Mode |",
        "|---|---|---|---|---|",
    ]
    for mode in modes:
        run = runs[mode]
        lines.append(
            f"| {markdown_cell(run.get('label') or mode)} | {markdown_cell(run.get('agent'))} | "
            f"{markdown_cell(run.get('agent_model'))} | {markdown_cell(run.get('model_source'))} | "
            f"{markdown_cell(mode)} |"
        )
    return "\n".join(lines)


def run_identity_summary(runs: dict[str, dict[str, Any]], modes: list[str]) -> str:
    return "; ".join(
        f"{runs[mode].get('label') or mode}: agent={runs[mode].get('agent') or 'NA'}, "
        f"model={runs[mode].get('agent_model') or 'NA'}"
        for mode in modes
    )


def exit_code(run: dict[str, Any]) -> int | None:
    summary = run.get("run") if isinstance(run.get("run"), dict) else {}
    container_exit = run.get("container_exit") if isinstance(run.get("container_exit"), dict) else {}
    for value in (
        summary.get("final_container_exit_code"),
        summary.get("report_inclusive_exit_code"),
        summary.get("agent_exit_code"),
        container_exit.get("exit_code"),
    ):
        if isinstance(value, bool) or value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def unsupported_model_message(text: str) -> str:
    match = re.search(r"The '[^']+' model is not supported[^.\n]*(?:\.[^\n]*)?", text)
    return match.group(0).strip() if match else ""


def combined_text(run: dict[str, Any]) -> str:
    return "\n".join(
        str(run.get(key) or "") for key in ("agent_events_text", "agent_stderr", "agent_last_message", "console_text")
    )


def strip_ansi(text: str) -> str:
    return ANSI_ESCAPE_PATTERN.sub("", text)


def message_content_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    message = payload.get("message")
    if not isinstance(message, dict):
        return []
    content = message.get("content")
    if not isinstance(content, list):
        return []
    return [item for item in content if isinstance(item, dict)]


def tool_result_output(payload: dict[str, Any], item: dict[str, Any]) -> str:
    parts = []
    result = payload.get("tool_use_result")
    if isinstance(result, dict):
        for key in ("stdout", "stderr"):
            value = result.get(key)
            text = str(value or "")
            if text and text not in parts:
                parts.append(text)
    elif result:
        text = str(result)
        if text not in parts:
            parts.append(text)
    for key in ("content", "text"):
        value = item.get(key)
        text = str(value or "")
        if text and text not in parts:
            parts.append(text)
    return strip_ansi("\n".join(parts))


def tool_result_exit(payload: dict[str, Any], item: dict[str, Any], output: str) -> tuple[int | None, str]:
    result = payload.get("tool_use_result")
    is_error = bool(item.get("is_error"))
    interrupted = False
    if isinstance(result, dict):
        is_error = is_error or bool(result.get("is_error"))
        interrupted = bool(result.get("interrupted"))
    exit_match = re.search(r"\bExit code\s+([0-9]+)\b", output, flags=re.IGNORECASE)
    exit_code = int(exit_match.group(1)) if exit_match else None
    if interrupted and exit_code is None:
        exit_code = 124
    if is_error and exit_code is None:
        exit_code = 1
    if exit_code is None and not is_error and not interrupted:
        exit_code = 0
    status = "failed" if (exit_code not in (None, 0) or is_error or interrupted) else "completed"
    return exit_code, status


def agent_command_events(run: dict[str, Any]) -> list[dict[str, Any]]:
    events = []
    pending_tool_commands: dict[str, dict[str, Any]] = {}
    for line in str(run.get("agent_events_text") or "").splitlines():
        try:
            payload = json.loads(line)
        except (TypeError, ValueError):
            continue
        if not isinstance(payload, dict):
            continue
        for content_item in message_content_items(payload):
            if content_item.get("type") == "tool_use" and content_item.get("name") == "Bash":
                tool_input = content_item.get("input") if isinstance(content_item.get("input"), dict) else {}
                command = str(tool_input.get("command") or "")
                tool_id = str(content_item.get("id") or "")
                if command and tool_id:
                    pending_tool_commands[tool_id] = {
                        "command": command,
                        "id": tool_id,
                        "index": len(events),
                    }
            elif content_item.get("type") == "tool_result":
                tool_id = str(content_item.get("tool_use_id") or "")
                pending = pending_tool_commands.pop(tool_id, None)
                if not pending:
                    continue
                output = tool_result_output(payload, content_item)
                exit_code, status = tool_result_exit(payload, content_item, output)
                events.append(
                    {
                        "command": pending["command"],
                        "exit_code": exit_code,
                        "id": pending["id"],
                        "index": len(events),
                        "output": output,
                        "status": status,
                    }
                )
        item = payload.get("item")
        if not isinstance(item, dict) or item.get("type") != "command_execution":
            continue
        command = str(item.get("command") or "")
        if not command:
            continue
        events.append(
            {
                "command": command,
                "exit_code": item.get("exit_code"),
                "id": item.get("id"),
                "index": len(events),
                "output": strip_ansi(str(item.get("aggregated_output") or "")),
                "status": str(item.get("status") or ""),
            }
        )
    return events


def command_failed(event: dict[str, Any]) -> bool:
    exit_value = event.get("exit_code")
    if isinstance(exit_value, bool):
        return False
    if exit_value not in (None, 0):
        return True
    return str(event.get("status") or "") == "failed"


def command_succeeded(event: dict[str, Any]) -> bool:
    return (event.get("exit_code") == 0 and str(event.get("status") or "") == "completed") or job_output_succeeded(
        str(event.get("output") or "")
    )


def command_recovery_key(command: str) -> str:
    command = str(command)
    if re.search(r"\bpip\s+install\b", command):
        requirements = re.search(r"-r\s+([A-Za-z0-9_./-]*requirements[A-Za-z0-9_.-]*\.txt)", command)
        return f"pip install {Path(requirements.group(1)).name}" if requirements else "pip install"
    script = re.search(r"\bpython(?:3)?\s+([A-Za-z0-9_./-]+\.py)\b", command)
    if script:
        role = "export" if "--export" in command else "run"
        return f"python {Path(script.group(1)).name} {role}"
    first_word = re.search(r"(?:^|['\"])([A-Za-z0-9_./-]+)", command)
    return first_word.group(1) if first_word else command[:80]


def python_script_name(command: str) -> str:
    match = re.search(r"\bpython(?:3)?\s+([A-Za-z0-9_./-]+\.py)\b", str(command))
    return Path(match.group(1)).name.lower() if match else ""


def job_entrypoint_match(command: str) -> str:
    """Return direct, ambiguous, or empty for Python scripts that look like job runners."""
    script_name = python_script_name(command)
    if not script_name:
        return ""
    stem = Path(script_name).stem
    if stem == "job":
        return "direct"
    tokens = re.split(r"[_.-]+", stem)
    helper_tokens = {"check", "validate", "verify", "test", "tests", "setup", "config", "lint", "probe"}
    action_tokens = {"run", "start", "launch", "execute"}
    if tokens[0] == "job":
        return "" if helper_tokens.intersection(tokens[1:]) else "direct"
    if tokens in (["run", "job"], ["start", "job"], ["launch", "job"], ["execute", "job"]):
        return "direct"
    if "job" not in tokens or helper_tokens.intersection(tokens):
        return ""
    if tokens[-1:] == ["job"] or action_tokens.intersection(tokens):
        return "ambiguous"
    return ""


def is_job_entrypoint_command(command: str) -> bool:
    return bool(job_entrypoint_match(command))


def is_simulation_entrypoint_command(command: str) -> bool:
    script_name = python_script_name(command)
    if not script_name:
        return False
    stem = Path(script_name).stem
    if "simulat" not in stem:
        return False
    tokens = set(re.split(r"[_.-]+", stem))
    return bool(tokens & {"run", "start", "launch", "execute"}) or stem in {"simulate", "simulation", "simulator"}


def is_simulation_or_job_command(command: str) -> bool:
    return is_job_entrypoint_command(command) or is_simulation_entrypoint_command(command)


def job_output_succeeded(output: str) -> bool:
    return bool(
        re.search(
            r"\bFinished\s+FedAvg\b|\bSimulation workspace:\s*|\bResult workspace:\s*",
            strip_ansi(output),
            flags=re.IGNORECASE,
        )
    )


def is_material_failed_command(event: dict[str, Any]) -> bool:
    command = str(event.get("command") or "")
    output = str(event.get("output") or "")
    if is_simulation_or_job_command(command):
        return True
    if re.search(r"\bpip\s+install\b", command):
        return True
    return bool(
        re.search(
            r"Traceback|RuntimeError|ConfigError|ModuleNotFoundError|No module named|Simulator run failed",
            output,
            flags=re.IGNORECASE,
        )
    )


def missing_python_module_name(output: str) -> str:
    text = strip_ansi(output)
    match = re.search(r"ModuleNotFoundError:\s+No module named ['\"]([^'\"]+)['\"]", text)
    if match:
        return match.group(1)
    match = re.search(r"No module named ['\"]([^'\"]+)['\"]", text)
    return match.group(1) if match else ""


def job_command_succeeded(event: dict[str, Any]) -> bool:
    command = str(event.get("command") or "")
    if not command_succeeded(event):
        return False
    job_match = job_entrypoint_match(command)
    if job_match == "direct":
        return True
    if job_match == "ambiguous":
        return job_output_succeeded(str(event.get("output") or ""))
    if is_simulation_entrypoint_command(command):
        return job_output_succeeded(str(event.get("output") or ""))
    return False


def command_error_summary(output: str) -> str:
    text = strip_ansi(output)
    patterns = (
        r"TypeError: [^\n]+",
        r"ConfigError: [^\n]+",
        r"RuntimeError: [^\n]+",
        r"ModuleNotFoundError: [^\n]+",
        r"No module named [^\n]+",
        r"sed: can't read [^\n]+",
        r"ERROR - [^\n]+",
        r"Error processing [^\n]+",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return truncate(match.group(0), 320)
    for line in text.splitlines():
        lowered = line.lower()
        if any(token in lowered for token in ("error", "failed", "traceback", "missing", "not found")):
            return truncate(line, 320)
    return truncate(text, 320) if text.strip() else "no command output captured"


def recovered_by_later_success(event: dict[str, Any], events: list[dict[str, Any]]) -> bool:
    key = command_recovery_key(str(event.get("command") or ""))
    index = int(event.get("index") or 0)
    for candidate in events:
        if int(candidate.get("index") or 0) <= index:
            continue
        candidate_command = str(candidate.get("command") or "")
        if command_recovery_key(candidate_command) != key:
            continue
        if is_simulation_or_job_command(candidate_command):
            if job_command_succeeded(candidate):
                return True
            continue
        if command_succeeded(candidate):
            return True
    return False


def recovered_by_later_successful_job(event: dict[str, Any], events: list[dict[str, Any]]) -> bool:
    index = int(event.get("index") or 0)
    for candidate in events:
        if int(candidate.get("index") or 0) <= index:
            continue
        if job_command_succeeded(candidate):
            return True
    return False


def metric_log_lines(output: str, limit: int = 4) -> list[str]:
    lines = []
    for line in strip_ansi(output).splitlines():
        clean = re.sub(r"^\d{4}-\d{2}-\d{2}[^-]*-\s+(?:INFO|WARNING|ERROR)\s+-\s+", "", line).strip()
        if re.search(r"\b(?:valid|validation|test|train)_[A-Za-z0-9_/-]+\s*=\s*[0-9]+\.[0-9]+", clean):
            lines.append(clean)
        elif re.search(r"\b(?:best\s+)?(?:aggregated|global|server)\s+validation\b", clean, flags=re.IGNORECASE):
            lines.append(clean)
        if len(lines) >= limit:
            break
    return lines


def last_successful_job_event(run: dict[str, Any]) -> dict[str, Any] | None:
    for event in reversed(agent_command_events(run)):
        if job_command_succeeded(event):
            command = str(event.get("command") or "")
            if "--help" not in command and "--export" not in command:
                return event
    return None


def result_permission_denial_count(run: dict[str, Any]) -> int:
    count = 0
    for line in str(run.get("agent_events_text") or "").splitlines():
        try:
            payload = json.loads(line)
        except (TypeError, ValueError):
            continue
        if not isinstance(payload, dict):
            continue
        denials = payload.get("permission_denials")
        if isinstance(denials, list):
            count = max(count, len(denials))
    return count


def bash_permission_denial_count(run: dict[str, Any]) -> int:
    events_text = str(run.get("agent_events_text") or "")
    needle = "requested permissions to use bash"
    raw_count = events_text.lower().count(needle)
    tool_result_count = 0
    for line in events_text.splitlines():
        try:
            payload = json.loads(line)
        except (TypeError, ValueError):
            continue
        if not isinstance(payload, dict):
            continue
        text_parts = [str(payload.get("tool_use_result") or "")]
        message = payload.get("message")
        if isinstance(message, dict):
            for item in message.get("content") or []:
                if isinstance(item, dict):
                    text_parts.append(str(item.get("content") or item.get("text") or ""))
        if any(needle in text.lower() for text in text_parts):
            tool_result_count += 1
    if tool_result_count:
        return max(result_permission_denial_count(run), tool_result_count)
    return max(result_permission_denial_count(run), raw_count)


def permission_denial_commands(run: dict[str, Any]) -> list[str]:
    commands = []
    for line in str(run.get("agent_events_text") or "").splitlines():
        try:
            payload = json.loads(line)
        except (TypeError, ValueError):
            continue
        if not isinstance(payload, dict):
            continue
        denials = payload.get("permission_denials")
        if not isinstance(denials, list):
            continue
        for denial in denials:
            if not isinstance(denial, dict):
                continue
            tool_input = denial.get("tool_input")
            if isinstance(tool_input, dict):
                command = str(tool_input.get("command") or "").strip()
                if command and command not in commands:
                    commands.append(command)
    return commands


def bash_blocked_diagnostic(run: dict[str, Any], *, recovered: bool = False) -> str | None:
    """Return a diagnostic string if Bash was blocked due to permission approval failures."""
    blocked_count = bash_permission_denial_count(run)
    if blocked_count == 0:
        return None
    if recovered:
        denied_commands = permission_denial_commands(run)
        command = f" Denied command: `{truncate(denied_commands[0], 180)}`." if denied_commands else ""
        return (
            f"Bash tool was blocked {blocked_count} time(s) earlier in this run, but a later simulator/job "
            f"command completed.{command} This usually means Claude rejected that specific command shape "
            "rather than Bash being unavailable for the whole run; it is still reported because the recovery "
            "costs extra tool turns, tokens, and elapsed time."
        )
    hint_counts = run.get("activity", {}).get("hint_counts") or {}
    sim_count = hint_counts.get("simulation", 0)
    py_count = hint_counts.get("python_job_py", 0)
    impact = ""
    if sim_count == 0 and py_count == 0:
        impact = " The simulation was never run as a result."
    elif sim_count == 0:
        impact = " The simulation step was never run."
    return (
        f"Bash tool was blocked {blocked_count} time(s) with 'requested permissions' errors. "
        f"In Claude Code --print (non-interactive) mode, tools require explicit allow rules even with "
        f"--dangerously-skip-permissions. Check that (1) BENCHMARK_AGENT_HOME/settings.json has "
        f"`Bash(*)` in permissions.allow, (2) --allowedTools includes `Bash(*)` in the agent launch argv, "
        f"and (3) no deny/ask rules exist at /etc/claude-code/managed-settings.json inside Docker. "
        f"Rebuild the Docker image after any agent config changes.{impact}"
    )


def job_run_status(run: dict[str, Any]) -> str:
    """Return one of 'completed', 'started_failed', 'not_started', or 'unknown'."""
    if not run.get("available"):
        return "unknown"
    executed_events = [
        event
        for event in agent_command_events(run)
        if is_simulation_or_job_command(str(event.get("command") or ""))
        and "--help" not in str(event.get("command") or "")
        and "--export" not in str(event.get("command") or "")
    ]
    attempted_commands = [
        command
        for command in commands_for_run(run)
        if is_simulation_or_job_command(command) and "--help" not in command and "--export" not in command
    ]
    attempted = bool(executed_events or attempted_commands)
    if not attempted:
        return "not_started"
    if last_successful_job_event(run):
        return "completed"
    return "started_failed"


def job_run_status_reason(run: dict[str, Any]) -> str:
    """Return a concise human-readable reason string for the job run status."""
    if not run.get("available"):
        return "run artifacts not available"
    status = job_run_status(run)
    hint_counts = run.get("activity", {}).get("hint_counts") or {}
    sim_count = int(hint_counts.get("simulation", 0) or 0)
    py_count = int(hint_counts.get("python_job_py", 0) or 0)

    # Check Bash blocking first — it's the most actionable reason for not_started
    bash_blocked_count = bash_permission_denial_count(run)

    if status == "not_started":
        failure_category = agent_failure_category(run)
        if exit_code(run) not in (None, 0) and failure_category and failure_category != "agent_unknown_failure":
            evidence = failure_evidence(run)
            if evidence:
                return (
                    "simulation not attempted — agent failed before starting job work "
                    f"({failure_category}: {truncate(evidence, 180)})"
                )
            return f"simulation not attempted — agent failed before starting job work ({failure_category})"
        if bash_blocked_count > 0:
            return (
                f"Bash blocked {bash_blocked_count} time(s) — simulation never ran "
                f"(permission errors prevented tool use)"
            )
        activity = run.get("activity") if isinstance(run.get("activity"), dict) else {}
        denials = activity.get("permission_denials") or []
        if denials:
            denial_summary = "; ".join(str(d) for d in denials[:3])
            return f"simulation not attempted — permission denials: {denial_summary}"
        commands = commands_for_run(run)
        if commands:
            return (
                "simulation not attempted — captured commands did not run job.py "
                f"(first command: `{truncate(commands[0], 120)}`)"
            )
        return "simulation not attempted — no captured job.py or simulator command"

    if status == "started_failed":
        if bash_blocked_count > 0:
            return (
                f"simulation command ran but Bash was blocked {bash_blocked_count} time(s); "
                f"simulation did not complete successfully"
            )
        # Look for a failed job event
        events = agent_command_events(run)
        for event in reversed(events):
            if command_failed(event) and is_simulation_or_job_command(str(event.get("command") or "")):
                output = str(event.get("output") or "")
                missing_module = missing_python_module_name(output)
                if missing_module:
                    return (
                        f"simulation command ran but missing Python dependency `{missing_module}` — "
                        f"{dependency_install_evidence(run)}"
                    )
                summary = command_error_summary(output)
                return f"simulation command ran but exited with error — {truncate(summary, 200)}"
        for event in reversed(events):
            if is_simulation_or_job_command(str(event.get("command") or "")):
                output = str(event.get("output") or "")
                missing_module = missing_python_module_name(output)
                if missing_module:
                    return (
                        f"simulation command ran but missing Python dependency `{missing_module}` — "
                        f"{dependency_install_evidence(run)}"
                    )
                summary = command_error_summary(output)
                return f"simulation command ran but success was not confirmed — {truncate(summary, 200)}"
        return "simulation command ran but no command output was captured"

    if status == "completed":
        event = last_successful_job_event(run)
        output = str(event.get("output") or "") if event else ""
        recovered_issue = completed_job_recovered_issue_summary(run)
        if "Finished" in output:
            reason = "simulation completed — FL workflow reached Finished state"
            return f"{reason}; {recovered_issue}" if recovered_issue else reason
        if sim_count > 0 or py_count > 0:
            reason = f"simulation completed successfully (hint count: simulation={sim_count}, python_job_py={py_count})"
            return f"{reason}; {recovered_issue}" if recovered_issue else reason
        reason = "simulation completed successfully"
        return f"{reason}; {recovered_issue}" if recovered_issue else reason

    return "status unknown — no simulation hint counts or events found"


def completed_job_recovered_issue_summary(run: dict[str, Any]) -> str:
    parts = []
    blocked_count = bash_permission_denial_count(run)
    if blocked_count:
        parts.append(f"Bash/tool permission was blocked {blocked_count} time(s) before a later job command completed")
    for event in agent_command_events(run):
        if not command_failed(event) or not is_material_failed_command(event):
            continue
        events = agent_command_events(run)
        if not (recovered_by_later_success(event, events) or recovered_by_later_successful_job(event, events)):
            continue
        output = str(event.get("output") or "")
        missing_module = missing_python_module_name(output)
        if missing_module:
            parts.append(
                f"earlier missing Python dependency `{missing_module}` was recovered "
                f"({dependency_install_evidence_brief(run)})"
            )
        else:
            parts.append(f"earlier command failure was recovered ({truncate(command_error_summary(output), 160)})")
        break
    return "; ".join(parts)


def job_run_action(run: dict[str, Any]) -> str:
    status = job_run_status(run)
    if status == "not_started":
        failure_category = agent_failure_category(run)
        if exit_code(run) not in (None, 0) and failure_category and failure_category != "agent_unknown_failure":
            if failure_category == "agent_auth_failure":
                return "Authenticate the selected agent in the mounted benchmark home, then rerun; the job never started."
            return "Fix the agent startup failure, then rerun; the job never started."
        if bash_permission_denial_count(run):
            return "Fix agent Bash/tool permissions and rerun; no FL metrics can be trusted until the job executes."
        return "Require the agent to run the generated job or simulator before reporting benchmark metrics."
    if status == "started_failed":
        reason = job_run_status_reason(run)
        if "missing Python dependency" in reason:
            if "no dependency install command was captured" in reason:
                return "Install the job requirements in the same Python environment before running the simulator, then rerun the benchmark."
            return "Inspect the dependency install command output and ensure the simulator uses the environment where requirements were installed."
        return "Inspect the failed job command output, fix the generated job, and rerun the benchmark."
    if status == "completed":
        if completed_job_recovered_issue_summary(run):
            return "Use the final successful job logs for metrics, but inspect recovered command failures before drawing conclusions."
        return "Use job logs and reported metrics for quality comparison."
    return "Inspect run artifacts; job execution evidence is unavailable."


def command_failure_diagnostics(run: dict[str, Any], limit: int = 3) -> list[str]:
    events = agent_command_events(run)
    failed_events = [event for event in events if command_failed(event)]
    material_events = [event for event in failed_events if is_material_failed_command(event)]
    selected_events = material_events or [
        event
        for event in failed_events
        if "git status" not in str(event.get("command") or "")
        and "rg: command not found" not in str(event.get("output") or "")
    ]
    diagnostics = []
    for event in selected_events:
        command = str(event.get("command") or "")
        output = str(event.get("output") or "")
        if recovered_by_later_success(event, events):
            recovery = "recovered by a later successful similar command"
        elif recovered_by_later_successful_job(event, events):
            recovery = "recovered by a later successful simulator/job command"
        else:
            recovery = "not recovered in this run"
        dependency_evidence = ""
        if missing_python_module_name(output):
            dependency_evidence = f" Dependency install evidence: {dependency_install_evidence(run)}."
        diagnostics.append(
            f"Command `{truncate(command, 160)}` failed with exit {event.get('exit_code')}; "
            f"{recovery}. Root cause evidence: {command_error_summary(output)}.{dependency_evidence}"
        )
        if len(diagnostics) >= limit:
            break
    return diagnostics


def successful_job_evidence(run: dict[str, Any]) -> str:
    event = last_successful_job_event(run)
    if not event:
        return ""
    output = str(event.get("output") or "")
    parts = ["a later simulator/job command exited 0"]
    if "Finished" in output:
        parts.append("the FL workflow reached a Finished state")
    workspace = re.search(r"Result workspace:\s*([^\n]+)", output)
    if workspace:
        parts.append(f"result workspace `{workspace.group(1).strip()}`")
    metric_lines = metric_log_lines(output)
    if metric_lines:
        parts.append("log metrics: " + "; ".join(metric_lines))
    return "; ".join(parts)


def metric_reporting_gap_evidence(run: dict[str, Any]) -> str:
    issues = run_quality_issues(run)
    if not issues:
        return ""
    record = run.get("record") if isinstance(run.get("record"), dict) else {}
    expected = quality_signal(record).get("expected_primary_metric") or "target metric"
    success = successful_job_evidence(run)
    if success and metric_value(run, canonical_metric_name(expected)) is None:
        return (
            f"Metric reporting gap: {success}, but the final response/benchmark record did not include one "
            f"aggregate `{expected}` scalar for comparison."
        )
    return ""


def referenced_requirements_files(text: str) -> list[str]:
    names = []
    for match in re.finditer(r"\bpip\s+install\s+-r\s+([A-Za-z0-9_./-]*requirements[A-Za-z0-9_.-]*\.txt)\b", text):
        name = Path(match.group(1)).name
        if name not in names:
            names.append(name)
    return names


def path_list_contains_filename(items: Any, filename: str) -> bool:
    if not isinstance(items, list):
        return False
    for item in items:
        if isinstance(item, dict) and Path(str(item.get("path") or "")).name == filename:
            return True
    return False


def dependency_file_origin(run: dict[str, Any], filename: str) -> str:
    source_delta = run_source_input_delta(run)
    workspace_delta = run_workspace_delta(run)
    if path_list_contains_filename(source_delta.get("final_files"), filename):
        return "original input file"
    for key, label in (
        ("workspace_added_files", "agent-generated file"),
        ("changed_files", "agent-created or modified file"),
        ("workspace_modified_files", "agent-modified original file"),
    ):
        if path_list_contains_filename(workspace_delta.get(key), filename):
            return label
    if path_list_contains_filename(workspace_delta.get("final_files"), filename):
        return "present in final agent workspace"
    return "not found in captured input or workspace manifests"


def dependency_reference_notes(run: dict[str, Any]) -> list[str]:
    notes = []
    for filename in referenced_requirements_files(combined_text(run)):
        notes.append(f"`{filename}` provenance: {dependency_file_origin(run, filename)}.")
    return notes


def metric_mismatch_with_reported_scalar(run: dict[str, Any]) -> bool:
    record = run.get("record") if isinstance(run.get("record"), dict) else {}
    signal = quality_signal(record)
    if not signal.get("mismatch"):
        return False
    metric = run.get("validation_metric") if isinstance(run.get("validation_metric"), dict) else {}
    actual_name = canonical_metric_name(metric.get("name"))
    return bool(actual_name) and metric_value(run, actual_name) is not None


def metric_mismatch_issue(run: dict[str, Any]) -> str:
    record = run.get("record") if isinstance(run.get("record"), dict) else {}
    signal = quality_signal(record)
    expected = signal.get("expected_primary_metric") or "target metric"
    metric = run.get("validation_metric") if isinstance(run.get("validation_metric"), dict) else {}
    actual_name = canonical_metric_name(metric.get("name"))
    actual = metric_display(run, actual_name or None)
    return f"Metric mismatch `primary_metric_reporting`: expected `{expected}`, reported {actual}."


def failure_evidence(run: dict[str, Any]) -> str:
    text = combined_text(run)
    model_error = unsupported_model_message(text)
    if model_error:
        return model_error
    for source_name in ("agent_last_message", "agent_stderr", "console_text", "agent_events_text"):
        for line in str(run.get(source_name) or "").splitlines():
            lowered = line.lower()
            if any(
                token in lowered
                for token in (
                    "error",
                    "failed",
                    "pull access denied",
                    "not supported",
                    "authentication_failed",
                    "not logged in",
                    "please run /login",
                    "api key",
                )
            ):
                return line.strip()[:500]
    return ""


def agent_failure_category(run: dict[str, Any]) -> str:
    record = run.get("record") if isinstance(run.get("record"), dict) else {}
    exit_summary = record.get("agent_exit_summary") if isinstance(record.get("agent_exit_summary"), dict) else {}
    failure_category = record.get("failure_category") or exit_summary.get("failure_category")
    if failure_category and failure_category != "agent_unknown_failure":
        return str(failure_category)
    text = combined_text(run).lower()
    if any(token in text for token in ("authentication_failed", "not logged in", "please run /login", "api key")):
        return "agent_auth_failure"
    if failure_category:
        return str(failure_category)
    return ""


def failure_root_cause(run: dict[str, Any]) -> str:
    record = run.get("record") if isinstance(run.get("record"), dict) else {}
    failure_category = agent_failure_category(run)
    if failure_category and failure_category != "agent_unknown_failure":
        return f"Agent failure category: {failure_category}"
    text = combined_text(run)
    model_error = unsupported_model_message(text)
    if model_error:
        return f"Agent model selection failed: {model_error}"
    lowered = text.lower()
    if "pull access denied" in lowered or "unable to find image" in lowered:
        return "Docker image unavailable: build the benchmark Docker images before running."
    error = record.get("harness_error") if isinstance(record.get("harness_error"), dict) else {}
    if error.get("message"):
        return f"Harness failure: {error['message']}"
    evidence = failure_evidence(run)
    if evidence:
        return evidence
    if failure_category:
        return f"Agent failure category: {failure_category}"
    code = exit_code(run)
    if code not in (None, 0):
        return f"Agent container failed with exit code {code}."
    return "No failure detected."


def run_quality_issues(run: dict[str, Any]) -> list[str]:
    issues = []
    record = run.get("record") if isinstance(run.get("record"), dict) else {}
    signal = quality_signal(record)
    expected = signal.get("expected_primary_metric")
    signal_status = str(signal.get("status") or "")
    if signal_status in {"fail", "missing"}:
        if metric_mismatch_with_reported_scalar(run):
            issues.append(metric_mismatch_issue(run))
        else:
            evidence = signal.get("evidence") or "final response did not satisfy the expected validation metric signal"
            issues.append(f"Failed check `primary_metric_reporting`: {evidence}")
    metric = run.get("validation_metric") if isinstance(run.get("validation_metric"), dict) else {}
    metric_name = canonical_metric_name(metric.get("name") or expected)
    if expected and metric_value(run, metric_name) is None:
        issues.append(
            f"Failed check `fl_metric_scalar`: no FL-level scalar value was found for expected metric `{expected}`."
        )
    delta = record.get("workspace_delta") if isinstance(record.get("workspace_delta"), dict) else {}
    if delta and not workspace_delta_has_artifact_evidence(delta):
        issues.append(
            "Failed check `workspace_delta`: no generated workspace files, final job structure, or runtime artifacts "
            "were captured."
        )
    return issues


def run_status_kind(run: dict[str, Any]) -> str:
    if not run.get("available"):
        return "missing"
    code = exit_code(run)
    if code not in (None, 0):
        return "failed"
    if run_quality_issues(run):
        return "needs review"
    return "passed"


def human_readable_status(run: dict[str, Any]) -> str:
    if not run.get("available"):
        return "missing"
    code = exit_code(run)
    if code == 0:
        issues = run_quality_issues(run)
        if issues:
            if metric_mismatch_with_reported_scalar(run):
                return f"completed with metric mismatch ({issues[0]})"
            return f"needs review ({issues[0]})"
        return "passed"
    detail = "unknown exit" if code is None else f"container exit {code}"
    return f"failed ({detail}; {failure_root_cause(run)})"


def run_analysis(run: dict[str, Any]) -> str:
    if not run.get("available"):
        return "Run artifacts are missing."
    issues = run_quality_issues(run)
    if exit_code(run) == 0 and issues:
        return issues[0]
    if exit_code(run) == 0:
        return "No failure detected."
    return failure_root_cause(run)


def status_summary(runs: dict[str, dict[str, Any]], modes: list[str] | None = None) -> str:
    modes = modes or mode_names(BENCHMARK_RUNS)
    parts = []
    for mode in modes:
        run = runs.get(mode, {"available": False, "label": MODE_LABELS.get(mode, mode)})
        parts.append(f"{run.get('label') or MODE_LABELS.get(mode, mode)}: {human_readable_status(run)}")
    return "; ".join(parts)


def metric_name_for_runs(runs: dict[str, dict[str, Any]]) -> str:
    common_name = comparable_metric_name(runs)
    if common_name:
        return common_name
    if metric_names_for_runs(runs):
        return "mixed validation metrics"
    return "result"


def metric_names_for_runs(runs: dict[str, dict[str, Any]]) -> list[str]:
    names = []
    for run in runs.values():
        metric = run.get("validation_metric")
        if isinstance(metric, dict) and metric.get("name"):
            name = canonical_metric_name(metric["name"])
            if name and name not in names:
                names.append(name)
    return names


def comparable_metric_name(runs: dict[str, dict[str, Any]]) -> str | None:
    names = metric_names_for_runs(runs)
    return names[0] if len(names) == 1 else None


def metric_value(run: dict[str, Any], metric_name: str | None = None) -> Any:
    metric = run.get("validation_metric")
    if not isinstance(metric, dict):
        return None
    if metric_name is not None and canonical_metric_name(metric.get("name")) != canonical_metric_name(metric_name):
        return None
    value = metric.get("value")
    if is_plausible_metric_value(canonical_metric_name(metric.get("name")), value):
        return value
    for entry in reversed(metric.get("reported_value_entries") or []):
        if not isinstance(entry, dict):
            continue
        value = entry.get("value")
        label = entry.get("label")
        if is_plausible_metric_value(canonical_metric_name(metric.get("name")), value) and is_fl_summary_metric_label(
            label
        ):
            return value
    return None


def metric_value_label(run: dict[str, Any], metric_name: str | None = None) -> str:
    metric = run.get("validation_metric")
    if not isinstance(metric, dict):
        return ""
    if metric_name is not None and canonical_metric_name(metric.get("name")) != canonical_metric_name(metric_name):
        return ""
    if metric.get("summary_value_label"):
        return str(metric["summary_value_label"])
    if is_plausible_metric_value(canonical_metric_name(metric.get("name")), metric.get("value")):
        return str(metric.get("value_scope") or "reported scalar")
    for entry in reversed(metric.get("reported_value_entries") or []):
        if not isinstance(entry, dict):
            continue
        if is_plausible_metric_value(
            canonical_metric_name(metric.get("name")), entry.get("value")
        ) and is_fl_summary_metric_label(entry.get("label")):
            return str(entry.get("label") or "")
    return ""


def metric_display(run: dict[str, Any], metric_name: str | None) -> str:
    metric = run.get("validation_metric")
    actual_name = None
    if isinstance(metric, dict) and metric.get("name"):
        actual_name = canonical_metric_name(metric["name"])
    display_name = actual_name if metric_name is None else metric_name
    if not display_name:
        record = run.get("record") if isinstance(run.get("record"), dict) else {}
        display_name = quality_signal(record).get("expected_primary_metric")
    if not display_name:
        display_name = "result"
    value = metric_value(run, metric_name)
    if value is None:
        return f"{display_name} NA"
    return f"{display_name} {fmt_number(value)}"


def metric_reported_value_count(metric: dict[str, Any] | None) -> int:
    if not isinstance(metric, dict):
        return 0
    values = metric.get("reported_values")
    if not isinstance(values, list):
        values = metric.get("site_values")
    if not isinstance(values, list):
        return 0
    return sum(1 for value in values if is_numeric_metric_value(value))


def additional_metric_values_display(run: dict[str, Any], metric_name: str | None = None) -> str:
    metric = run.get("validation_metric")
    if not isinstance(metric, dict):
        return "NA"
    if metric_name is not None and canonical_metric_name(metric.get("name")) != canonical_metric_name(metric_name):
        return "NA"
    values = metric.get("reported_values")
    labels = metric.get("reported_value_labels")
    if not isinstance(values, list):
        values = metric.get("site_values")
    if not isinstance(labels, list):
        labels = metric.get("site_value_labels")
    if not isinstance(values, list):
        return "NA"
    entries = []
    for index, value in enumerate(values):
        if not is_numeric_metric_value(value):
            continue
        label = labels[index] if isinstance(labels, list) and index < len(labels) else None
        label_text = str(label).strip() if label else f"value-{index + 1}"
        entries.append(f"{label_text}={fmt_number(value)}")
    if len(entries) <= 1:
        return "NA"
    return ", ".join(entries[:8]) + (f", +{len(entries) - 8} more" if len(entries) > 8 else "")


def metric_payload_display(payload: dict[str, Any]) -> str:
    name = canonical_metric_name(payload.get("name"))
    if not name:
        return "NA"
    value = payload.get("value")
    if is_numeric_metric_value(value):
        return f"{name} {fmt_number(value)}"
    values = payload.get("reported_values")
    if isinstance(values, list):
        numeric_values = [item for item in values if is_numeric_metric_value(item)]
        if numeric_values:
            rendered = ", ".join(fmt_number(item) for item in numeric_values[:4])
            suffix = f", +{len(numeric_values) - 4} more" if len(numeric_values) > 4 else ""
            return f"{name} values: {rendered}{suffix}"
    return f"{name} mentioned without numeric value"


def observed_metric_payloads(run: dict[str, Any]) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    seen: set[str] = set()
    metric = run.get("validation_metric")
    if isinstance(metric, dict) and metric.get("name"):
        name = canonical_metric_name(metric.get("name"))
        if name:
            payloads.append(metric)
            seen.add(name)
    text = str(run.get("agent_last_message") or "")
    for name in OBSERVED_METRIC_NAMES:
        canonical_name = canonical_metric_name(name)
        if canonical_name in seen:
            continue
        entries = metric_value_entries(name, text)
        if not entries:
            continue
        payload = reported_metric_payload(name, entries)
        if payload.get("reported_values"):
            payloads.append(payload)
            seen.add(canonical_name)
    return payloads


def observed_metric_evidence_display(run: dict[str, Any]) -> str:
    payloads = observed_metric_payloads(run)
    if not payloads:
        return "none"
    return "; ".join(metric_payload_display(payload) for payload in payloads)


def additional_or_observed_metric_values_display(run: dict[str, Any], metric_name: str | None = None) -> str:
    additional = additional_metric_values_display(run, metric_name)
    if additional != "NA":
        return additional
    observed = observed_metric_evidence_display(run)
    if observed != "none":
        return observed
    metric_lines = metric_log_lines(str((last_successful_job_event(run) or {}).get("output") or ""))
    if metric_lines:
        return "Final site metrics=NA; log/per-site evidence: " + "; ".join(metric_lines)
    simulation_refs = count_map(run, "hint_counts").get("simulation", 0)
    if simulation_refs == 0:
        return "NA (no simulation run detected; per-round/per-site values require the agent to run nvflare simulator)"
    return "NA"


def run_result_metric_status(run: dict[str, Any]) -> str:
    metric = run.get("validation_metric")
    if not isinstance(metric, dict) or not metric.get("name"):
        return "missing"
    value = metric_value(run, canonical_metric_name(metric.get("name")))
    if value is not None:
        label = metric_value_label(run, canonical_metric_name(metric.get("name")))
        suffix = f" ({label})" if label else ""
        return f"{canonical_metric_name(metric.get('name'))} {fmt_number(value)}{suffix}"
    count = metric_reported_value_count(metric)
    if count:
        return f"partial: {count} reported values, no FL-level scalar"
    return f"missing scalar: {canonical_metric_name(metric.get('name'))} mentioned without value"


def benchmark_outcome(run: dict[str, Any]) -> str:
    if not run.get("available"):
        return "fail: run artifacts missing"
    code = exit_code(run)
    if code not in (None, 0):
        return f"fail: container exit {code}"
    issues = run_quality_issues(run)
    if issues:
        if metric_mismatch_with_reported_scalar(run):
            return "warn: scalar metric reported, but it does not match the target metric instruction"
        return "fail: " + issues[0]
    return "pass: scalar FL result metric available"


def quality_signal(record: dict[str, Any]) -> dict[str, Any]:
    quality = record.get("quality_signals")
    if not isinstance(quality, dict):
        return {}
    signal = quality.get("job_guidance_primary_validation_metric") or quality.get("readme_primary_validation_metric")
    if not isinstance(signal, dict):
        return {}
    result = dict(signal)
    metric = result.get("reported_validation_metric")
    if isinstance(metric, dict) and metric.get("name"):
        sanitized = sanitized_validation_metric(metric)
        result["reported_validation_metric"] = sanitized
        values = sanitized.get("reported_values")
        if not isinstance(values, list):
            values = []
        has_numeric = is_numeric_metric_value(sanitized.get("value")) or any(
            is_numeric_metric_value(value) for value in values
        )
        expected = result.get("expected_primary_metric") or sanitized.get("name")
        if not has_numeric and sanitized.get("name"):
            result["status"] = "missing"
            result["metric_value_available"] = False
            result["metric_scalar_available"] = False
            result["aligned_with_job_guidance"] = False
            result["aligned_with_readme"] = False
            result["evidence"] = (
                f"Job guidance declares {expected} as the primary metric, and the final response mentioned "
                f"{sanitized.get('name')} but did not report a plausible numeric value."
            )
    return result


def quality_signal_table(runs: dict[str, dict[str, Any]], modes: list[str]) -> str:
    lines = [
        "| Run | Expected metric | Reported result | Status | Evidence |",
        "|---|---|---|---|---|",
    ]
    comparable_name = comparable_metric_name(runs)
    for mode in modes:
        run = runs[mode]
        signal = quality_signal(run.get("record") if isinstance(run.get("record"), dict) else {})
        metric = run.get("validation_metric") if isinstance(run.get("validation_metric"), dict) else {}
        expected = signal.get("expected_primary_metric") or metric.get("name")
        result = metric_display(run, comparable_name)
        label = metric_value_label(run, comparable_name)
        if label:
            result = f"{result} ({label})"
        evidence = signal.get("evidence") or "NA"
        lines.append(
            f"| {markdown_cell(run['label'])} | {markdown_cell(expected)} | {markdown_cell(result)} | "
            f"{markdown_cell(signal.get('status') or 'NA')} | {markdown_cell(evidence)} |"
        )
    return "\n".join(lines)


def output_changes_table(runs: dict[str, dict[str, Any]], modes: list[str]) -> str:
    lines = [
        "| Run | Changed files | Added | Modified | Notable files |",
        "|---|---:|---:|---:|---|",
    ]
    for mode in modes:
        run = runs[mode]
        record = run.get("record") if isinstance(run.get("record"), dict) else {}
        delta = record.get("workspace_delta") if isinstance(record.get("workspace_delta"), dict) else {}
        if not delta:
            delta = run.get("workspace_delta") if isinstance(run.get("workspace_delta"), dict) else {}
        changed_files = delta.get("changed_files") if isinstance(delta.get("changed_files"), list) else []
        changed_count = delta.get("changed_file_count")
        added = delta.get("workspace_added_file_count")
        modified = delta.get("workspace_modified_file_count")
        names = []
        for item in changed_files[:8]:
            if isinstance(item, dict) and item.get("path"):
                names.append(str(item["path"]))
        suffix = "" if len(changed_files) <= 8 else f"; +{len(changed_files) - 8} more"
        lines.append(
            f"| {markdown_cell(run['label'])} | {fmt_number(changed_count)} | {fmt_number(added)} | "
            f"{fmt_number(modified)} | {markdown_cell('; '.join(names) + suffix if names else 'NA')} |"
        )
    return "\n".join(lines)


def run_summary(run: dict[str, Any]) -> dict[str, Any]:
    summary = run.get("run")
    return summary if isinstance(summary, dict) else {}


def run_activity(run: dict[str, Any]) -> dict[str, Any]:
    activity = run.get("activity")
    return activity if isinstance(activity, dict) else {}


def run_record(run: dict[str, Any]) -> dict[str, Any]:
    record = run.get("record")
    return record if isinstance(record, dict) else {}


def run_workspace_delta(run: dict[str, Any]) -> dict[str, Any]:
    record = run_record(run)
    delta = record.get("workspace_delta") if isinstance(record.get("workspace_delta"), dict) else None
    if isinstance(delta, dict):
        return delta
    delta = run.get("workspace_delta")
    return delta if isinstance(delta, dict) else {}


def workspace_delta_has_artifact_evidence(delta: dict[str, Any]) -> bool:
    changed = as_number(delta.get("changed_file_count")) or 0
    workspace_changes = as_number(delta.get("workspace_change_count")) or 0
    runtime = as_number(delta.get("runtime_artifact_count")) or 0
    copied = as_number(delta.get("copied_file_count")) or 0
    final_structure = as_number(delta.get("final_structure_file_count")) or 0
    final_manifest = as_number(delta.get("final_file_manifest_count")) or 0
    final_structure_files = delta.get("final_structure_files")
    final_files = delta.get("final_files")
    return (
        changed > 0
        or workspace_changes > 0
        or runtime > 0
        or copied > 0
        or final_structure > 0
        or final_manifest > 0
        or (isinstance(final_structure_files, list) and bool(final_structure_files))
        or (isinstance(final_files, list) and bool(final_files))
    )


def run_source_input_delta(run: dict[str, Any]) -> dict[str, Any]:
    record = run_record(run)
    delta = record.get("source_input_delta") if isinstance(record.get("source_input_delta"), dict) else None
    return delta if isinstance(delta, dict) else {}


def artifact_summary(run: dict[str, Any]) -> str:
    delta = run_workspace_delta(run)
    changed = delta.get("changed_file_count")
    runtime = delta.get("runtime_artifact_count")
    copied = delta.get("copied_file_count")
    parts = []
    if changed is not None:
        parts.append(f"{fmt_number(changed)} changed/generated files")
    if runtime is not None:
        parts.append(f"{fmt_number(runtime)} runtime artifacts")
    if copied is not None:
        parts.append(f"{fmt_number(copied)} copied artifacts")
    return ", ".join(parts) if parts else "not captured"


def workspace_change_display(run: dict[str, Any]) -> str:
    delta = run_workspace_delta(run)
    changed = delta.get("changed_file_count")
    added = delta.get("workspace_added_file_count")
    modified = delta.get("workspace_modified_file_count")
    deleted = delta.get("workspace_deleted_baseline_file_count")
    if changed is None:
        return "not captured"
    parts = [f"{fmt_number(changed)} changed"]
    if added is not None:
        parts.append(f"{fmt_number(added)} added")
    if modified is not None:
        parts.append(f"{fmt_number(modified)} modified")
    if deleted:
        parts.append(f"{fmt_number(deleted)} deleted")
    return ", ".join(parts)


def source_input_protection_display(run: dict[str, Any]) -> str:
    record = run_record(run)
    policy = record.get("source_input_immutable_policy")
    if isinstance(policy, dict) and policy.get("status"):
        status = str(policy["status"])
        reason = policy.get("reason")
        return f"{status}: {reason}" if reason else status
    delta = run_source_input_delta(run)
    if not delta:
        return "not captured"
    changed = delta.get("changed_file_count")
    deleted = delta.get("deleted_file_count")
    if changed == 0 and deleted == 0:
        return "pass: immutable input snapshot unchanged"
    return f"fail: input snapshot changed={fmt_number(changed)}, deleted={fmt_number(deleted)}"


def manifest_paths(run: dict[str, Any], key: str) -> list[str]:
    delta = run_workspace_delta(run)
    values = delta.get(key)
    paths = []
    if isinstance(values, list):
        for item in values:
            if isinstance(item, dict) and item.get("path"):
                paths.append(str(item["path"]))
    return paths


def unique_paths(paths: list[str]) -> list[str]:
    result = []
    seen = set()
    for path in paths:
        if path not in seen:
            seen.add(path)
            result.append(path)
    return result


def basename_count_display(paths: list[str], limit: int = 6) -> str:
    if not paths:
        return "none"
    counts: dict[str, int] = {}
    for path in paths:
        name = Path(path).name
        counts[name] = counts.get(name, 0) + 1
    entries = []
    for name in sorted(counts)[:limit]:
        count = counts[name]
        entries.append(name if count == 1 else f"{name} ({count} paths)")
    if len(counts) > limit:
        entries.append(f"+{len(counts) - limit} more")
    return ", ".join(entries)


def current_workspace_structure_file_matches(run: dict[str, Any], filename: str) -> list[str]:
    paths = unique_paths(manifest_paths(run, "final_structure_files"))
    return [path for path in paths if Path(path).name == filename and len(Path(path).parts) == 1]


def nested_structure_file_matches(run: dict[str, Any], filename: str) -> list[str]:
    paths = unique_paths(manifest_paths(run, "final_structure_files") + manifest_paths(run, "changed_files"))
    return [path for path in paths if Path(path).name == filename and len(Path(path).parts) > 1]


def structure_score(run: dict[str, Any]) -> float | None:
    if not run.get("available"):
        return None
    present = sum(1 for filename in REQUIRED_STRUCTURE_FILES if current_workspace_structure_file_matches(run, filename))
    return present / len(REQUIRED_STRUCTURE_FILES)


def structure_required_display(run: dict[str, Any]) -> str:
    score = structure_score(run)
    if score is None:
        return "not captured"
    present = [filename for filename in REQUIRED_STRUCTURE_FILES if current_workspace_structure_file_matches(run, filename)]
    missing = [filename for filename in REQUIRED_STRUCTURE_FILES if filename not in present]
    text = f"{len(present)}/{len(REQUIRED_STRUCTURE_FILES)} present"
    if missing:
        text += "; missing " + ", ".join(missing)
    nested = {
        filename: nested_structure_file_matches(run, filename)
        for filename in REQUIRED_STRUCTURE_FILES
        if nested_structure_file_matches(run, filename)
    }
    if nested:
        folders = sorted({str(Path(path).parent) for paths in nested.values() for path in paths})
        text += "; nested copies ignored for current-structure score: " + ", ".join(folders[:3])
        if len(folders) > 3:
            text += f", +{len(folders) - 3} more"
    return text


def structure_optional_display(run: dict[str, Any]) -> str:
    if structure_score(run) is None:
        return "not captured"
    present = [
        filename for filename in OPTIONAL_STRUCTURE_FILES if current_workspace_structure_file_matches(run, filename)
    ]
    return ", ".join(present) if present else "none"


def nested_generated_structure_display(run: dict[str, Any]) -> str:
    folders: dict[str, set[str]] = {}
    for filename in REQUIRED_STRUCTURE_FILES:
        for path in nested_structure_file_matches(run, filename):
            folders.setdefault(str(Path(path).parent), set()).add(filename)
    if not folders:
        return "none"
    entries = []
    for folder in sorted(folders)[:4]:
        entries.append(f"{folder} ({', '.join(sorted(folders[folder]))})")
    if len(folders) > 4:
        entries.append(f"+{len(folders) - 4} more")
    return "; ".join(entries)


def structure_inventory_display(run: dict[str, Any], key: str, suffixes: tuple[str, ...]) -> str:
    paths = [path for path in manifest_paths(run, key) if Path(path).suffix in suffixes]
    return basename_count_display(paths)


def tree_from_paths(paths: list[str], *, max_paths: int = 80) -> str:
    sorted_paths = sorted(unique_paths(paths))
    truncated = len(sorted_paths) > max_paths
    paths = sorted_paths[:max_paths]
    if not paths:
        return "none"
    tree: dict[str, Any] = {}
    for path in paths:
        node = tree
        for part in Path(path).parts:
            if not part or part == ".":
                continue
            node = node.setdefault(part, {})

    lines = ["."]

    def render(node: dict[str, Any], prefix: str = "") -> None:
        entries = sorted(node)
        for index, name in enumerate(entries):
            connector = "`-- " if index == len(entries) - 1 else "|-- "
            lines.append(f"{prefix}{connector}{name}")
            child = node[name]
            if child:
                extension = "    " if index == len(entries) - 1 else "|   "
                render(child, prefix + extension)

    render(tree)
    if truncated:
        lines.append(f"... {len(sorted_paths) - max_paths} more paths not shown")
    return "\n".join(lines)


def tree_paths_for_keys(
    run: dict[str, Any],
    keys: tuple[str, ...],
    *,
    suffixes: tuple[str, ...] | None = None,
) -> list[str]:
    paths = []
    for key in keys:
        for path in manifest_paths(run, key):
            if suffixes is not None and Path(path).suffix not in suffixes:
                continue
            paths.append(path)
    return unique_paths(paths)


def structure_correctness_table(runs: dict[str, dict[str, Any]], modes: list[str]) -> str:
    rows = [
        ("Required converted files", structure_required_display),
        ("Nested generated job source", nested_generated_structure_display),
        ("Optional helper files", structure_optional_display),
        ("Final workspace Python inventory", lambda run: structure_inventory_display(run, "final_files", (".py",))),
        (
            "Changed/generated Python inventory",
            lambda run: structure_inventory_display(run, "changed_files", (".py",)),
        ),
        (
            "Runtime artifact config inventory",
            lambda run: structure_inventory_display(run, "runtime_artifacts", CONFIG_STRUCTURE_SUFFIXES),
        ),
    ]
    lines = [
        "| Structure signal | " + " | ".join(MODE_LABELS.get(mode, mode) for mode in modes) + " |",
        "|---|" + "|".join("---" for _ in modes) + "|",
    ]
    for label, getter in rows:
        lines.append(
            f"| {markdown_cell(label)} | " + " | ".join(markdown_cell(getter(runs[mode])) for mode in modes) + " |"
        )
    return "\n".join(lines)


def structure_trees_section(runs: dict[str, dict[str, Any]], modes: list[str]) -> str:
    lines = [
        "### Captured Structure Trees",
        "",
        "Trees are rendered from captured artifact manifests in tree-command format.",
    ]
    for mode in modes:
        run = runs[mode]
        lines.append("")
        lines.append(f"#### {run.get('label') or mode}")
        lines.append("")
        final_paths = tree_paths_for_keys(run, ("final_files",)) or tree_paths_for_keys(
            run,
            ("final_structure_files", "runtime_artifacts"),
            suffixes=TREE_RUNTIME_SUFFIXES,
        )
        changed_paths = tree_paths_for_keys(run, ("changed_files", "runtime_artifacts"))
        lines.append("Final workspace:")
        lines.append("")
        lines.append("```text")
        lines.append(tree_from_paths(final_paths))
        lines.append("```")
        lines.append("")
        lines.append("Changed/generated files:")
        lines.append("")
        lines.append("```text")
        lines.append(tree_from_paths(changed_paths))
        lines.append("```")
    return "\n".join(lines)


def count_map(run: dict[str, Any], key: str) -> dict[str, Any]:
    activity = run_activity(run)
    value = activity.get(key)
    return value if isinstance(value, dict) else {}


def hint_count(run: dict[str, Any], key: str) -> int:
    value = count_map(run, "hint_counts").get(key, 0)
    number = as_number(value)
    return int(number) if number is not None else 0


def event_type_count(run: dict[str, Any], key: str) -> int:
    value = count_map(run, "event_types").get(key, 0)
    number = as_number(value)
    return int(number) if number is not None else 0


def commands_for_run(run: dict[str, Any]) -> list[str]:
    commands = run_activity(run).get("commands")
    return [str(command) for command in commands] if isinstance(commands, list) else []


def dependency_install_attempted(run: dict[str, Any]) -> bool:
    for command in commands_for_run(run):
        lowered = command.lower()
        if "pip install" in lowered or "uv pip install" in lowered or "python -m pip" in lowered:
            return True
    return False


def is_dependency_install_command(command: str) -> bool:
    lowered = str(command).lower()
    return "pip install" in lowered or "uv pip install" in lowered or "python -m pip" in lowered


def dependency_install_events(run: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        event for event in agent_command_events(run) if is_dependency_install_command(str(event.get("command") or ""))
    ]


def dependency_install_evidence_brief(run: dict[str, Any]) -> str:
    events = dependency_install_events(run)
    if events:
        if any(command_failed(event) for event in events):
            return "dependency install was attempted and failed"
        if any(command_succeeded(event) for event in events):
            return "a dependency install command later succeeded"
        return "dependency install command was captured without success/failure status"
    if any(is_dependency_install_command(command) for command in commands_for_run(run)):
        return "dependency install command was listed but no command result was captured"
    return "no dependency install command was captured"


def dependency_install_evidence(run: dict[str, Any]) -> str:
    events = dependency_install_events(run)
    if events:
        failed = [event for event in events if command_failed(event)]
        if failed:
            event = failed[-1]
            return (
                f"dependency install attempted and failed (`{truncate(str(event.get('command') or ''), 100)}` "
                f"exit {event.get('exit_code')}: {truncate(command_error_summary(str(event.get('output') or '')), 160)})"
            )
        succeeded = [event for event in events if command_succeeded(event)]
        if succeeded:
            event = succeeded[-1]
            return f"dependency install command succeeded (`{truncate(str(event.get('command') or ''), 100)}`)"
        event = events[-1]
        return f"dependency install command captured without success/failure status (`{truncate(str(event.get('command') or ''), 100)}`)"
    commands = [command for command in commands_for_run(run) if is_dependency_install_command(command)]
    if commands:
        return f"dependency install command listed in activity but no command result was captured (`{truncate(commands[-1], 100)}`)"
    return "no dependency install command was captured before the failed job run"


def missing_result_metrics_section(runs: dict[str, dict[str, Any]], modes: list[str]) -> str:
    issue_modes = [mode for mode in modes if run_quality_issues(runs[mode])]
    if not issue_modes:
        return ""
    lines = [
        "## Missing, Partial, Or Mismatched Result Metrics",
        "",
        "A run can complete at the agent/container level and still need review when it omits the requested FL-level validation metric, reports only partial values, or reports a different metric than the job guidance requested.",
        "",
        "| Run | Result metric status | Final response metric evidence | Why results are missing, partial, or mismatched | Report action |",
        "|---|---|---|---|---|",
    ]
    for mode in issue_modes:
        run = runs[mode]
        issues = run_quality_issues(run)
        observed_metrics = observed_metric_evidence_display(run)
        action = "Require the final message or benchmark record to include one aggregate FL validation metric."
        if metric_mismatch_with_reported_scalar(run):
            action = (
                "Treat the run as completed with a reported scalar metric, but flag that it did not follow the target "
                "metric instruction."
            )
        if not metric_names_for_runs({mode: run}) and observed_metrics == "none":
            action = "Inspect the final message and generated job logs; no parseable validation metric was reported."
            if successful_job_evidence(run):
                action = (
                    "Simulator/job logs contain metric evidence, but the final response or benchmark record did not "
                    "report one aggregate FL validation metric."
                )
        lines.append(
            f"| {markdown_cell(run.get('label') or mode)} | {markdown_cell(run_result_metric_status(run))} | "
            f"{markdown_cell(observed_metrics)} | {markdown_cell('; '.join(issues))} | "
            f"{markdown_cell(action)} |"
        )
    return "\n".join(lines)


def activity_insights_table(runs: dict[str, dict[str, Any]], modes: list[str]) -> str:
    rows = [
        (
            "File reads (`cat`/`sed`/Read tool)",
            "shell_cat_or_sed",
            "Direct file-read behavior; includes shell cat/sed and Read tool calls.",
        ),
        ("`find` commands", "shell_find", "Filesystem discovery proxy."),
        ("`rg`/`grep` search commands", "shell_search", "Search use proxy; covers rg and grep."),
        ("Simulation references", "simulation", "Shows validation effort against generated jobs."),
        ("Python compile checks", "py_compile", "Shows syntax validation effort."),
        (
            "Skill calls / skill references",
            "skill_references",
            "Only skills-enabled runs should usually show these; includes Skill tool calls.",
        ),
        (
            "Agent / inspect calls",
            "agent_inspect",
            "Shows use of agent inspection commands; includes Agent tool calls.",
        ),
        ("Python job.py references", "python_job_py", "Shows repeated exercise of generated job entry points."),
    ]
    lines = [
        "| Activity signal | " + " | ".join(MODE_LABELS.get(mode, mode) for mode in modes) + " | Interpretation |",
        "|---|" + "|".join("---:" for _ in modes) + "|---|",
    ]
    for label, key, note in rows:
        lines.append(
            f"| {markdown_cell(label)} | "
            + " | ".join(str(hint_count(runs[mode], key)) for mode in modes)
            + f" | {markdown_cell(note)} |"
        )
    return "\n".join(lines)


def event_mix_table(runs: dict[str, dict[str, Any]], modes: list[str]) -> str:
    keys = sorted({key for mode in modes for key in count_map(runs[mode], "event_types")})
    if not keys:
        keys = ["command_execution", "agent_message", "file_change", "todo_list"]
    lines = [
        "| Event type | " + " | ".join(MODE_LABELS.get(mode, mode) for mode in modes) + " |",
        "|---|" + "|".join("---:" for _ in modes) + "|",
    ]
    for key in keys:
        lines.append(
            f"| `{markdown_cell(key)}` | " + " | ".join(str(event_type_count(runs[mode], key)) for mode in modes) + " |"
        )
    return "\n".join(lines)


def outcome_details_table(runs: dict[str, dict[str, Any]], modes: list[str]) -> str:
    comparable_name = comparable_metric_name(runs)
    rows = [
        ("Agent/container outcome", human_readable_status),
        ("FL result quality gate", benchmark_outcome),
        ("Reported validation metric", lambda run: metric_display(run, comparable_name)),
        (
            "Additional/other validation metric values",
            lambda run: additional_or_observed_metric_values_display(run, comparable_name),
        ),
        ("Source input protection", source_input_protection_display),
        ("Copied workspace changes", workspace_change_display),
        ("Captured generated artifacts", artifact_summary),
        ("Required structure files", structure_required_display),
        ("Optional structure files", structure_optional_display),
    ]
    lines = [
        "| Signal | " + " | ".join(MODE_LABELS.get(mode, mode) for mode in modes) + " |",
        "|---|" + "|".join("---" for _ in modes) + "|",
    ]
    for label, getter in rows:
        lines.append(
            f"| {markdown_cell(label)} | " + " | ".join(markdown_cell(getter(runs[mode])) for mode in modes) + " |"
        )
    return "\n".join(lines)


def cost_comparison_section(runs: dict[str, dict[str, Any]], modes: list[str]) -> str:
    if len(modes) != 2:
        return ""
    left, right = modes
    left_run = runs[left]
    right_run = runs[right]
    left_summary = run_summary(left_run)
    right_summary = run_summary(right_run)
    rows = [
        ("Elapsed seconds", left_summary.get("elapsed_seconds"), right_summary.get("elapsed_seconds")),
        ("Total tokens", left_summary.get("token_count"), right_summary.get("token_count")),
        ("Commands", run_activity(left_run).get("command_count"), run_activity(right_run).get("command_count")),
        (
            "Unique commands",
            run_activity(left_run).get("unique_command_count"),
            run_activity(right_run).get("unique_command_count"),
        ),
        (
            "Changed/generated files",
            run_workspace_delta(left_run).get("changed_file_count"),
            run_workspace_delta(right_run).get("changed_file_count"),
        ),
        (
            "Runtime artifacts",
            run_workspace_delta(left_run).get("runtime_artifact_count"),
            run_workspace_delta(right_run).get("runtime_artifact_count"),
        ),
    ]
    lines = [
        "## Cost And Work Comparison",
        "",
        "Cost numbers are descriptive only. Quality gates decide whether a cost comparison is meaningful.",
        "",
        f"| Signal | {markdown_cell(left_run.get('label') or left)} | {markdown_cell(right_run.get('label') or right)} | Delta right-left |",
        "|---|---:|---:|---:|",
    ]
    for label, left_value, right_value in rows:
        left_num = as_number(left_value)
        right_num = as_number(right_value)
        delta = right_num - left_num if left_num is not None and right_num is not None else None
        formatter = fmt_short if label == "Total tokens" else fmt_number
        lines.append(
            f"| {markdown_cell(label)} | {formatter(left_value)} | {formatter(right_value)} | {formatter(delta)} |"
        )
    return "\n".join(lines)


def _run_usage(run: dict[str, Any]) -> dict[str, Any]:
    usage = run.get("usage")
    return usage if isinstance(usage, dict) else {}


def _thinking_token_events(run: dict[str, Any]) -> int:
    return event_type_count(run, "system.thinking_tokens")


def _assistant_turns(run: dict[str, Any]) -> int:
    return event_type_count(run, "assistant")


def _why_slower(with_run: dict[str, Any], base_run: dict[str, Any]) -> list[str]:
    with_label = with_run.get("label") or "With skills"
    base_label = base_run.get("label") or "No skills baseline"
    with_time = as_number(run_summary(with_run).get("elapsed_seconds")) or 0
    base_time = as_number(run_summary(base_run).get("elapsed_seconds")) or 0
    time_delta = with_time - base_time
    pct = round(time_delta / base_time * 100) if base_time > 0 else 0

    with_turns = _assistant_turns(with_run)
    base_turns = _assistant_turns(base_run)
    with_think = _thinking_token_events(with_run)
    base_think = _thinking_token_events(base_run)
    with_tools = count_map(with_run, "tool_counts")
    base_tools = count_map(base_run, "tool_counts")
    skill_delta = with_tools.get("Skill", 0) - base_tools.get("Skill", 0)
    agent_delta = with_tools.get("Agent", 0) - base_tools.get("Agent", 0)
    search_delta = with_tools.get("ToolSearch", 0) - base_tools.get("ToolSearch", 0)

    lines = [f"**Why {with_label} is slower** (+{fmt_number(time_delta)}s / +{pct}% vs {base_label}):", ""]
    if with_turns != base_turns:
        turns_delta = with_turns - base_turns
        lines.append(
            f"- **More conversation turns** ({with_turns} vs {base_turns}, +{turns_delta}): "
            f"each turn is an API round-trip to the model. {turns_delta} extra turns account for most of the "
            f"wall-clock overhead; the per-turn latency itself is largely unchanged."
        )
    if with_think != base_think:
        think_delta = with_think - base_think
        lines.append(
            f"- **More extended reasoning** ({with_think} vs {base_think} thinking-token events, +{think_delta}): "
            f"the model engaged extended chain-of-thought significantly more often, "
            f"likely while interpreting skill documentation and planning how to apply it."
        )
    if skill_delta > 0:
        lines.append(
            f"- **Skill invocation overhead** ({with_tools.get('Skill', 0)} Skill call(s) vs {base_tools.get('Skill', 0)}): "
            f"each Skill call fetches and runs a skill, injecting documentation into context "
            f"and adding a round-trip before the agent can proceed."
        )
    if agent_delta > 0:
        lines.append(
            f"- **Subagent spawning** ({with_tools.get('Agent', 0)} Agent call(s) vs {base_tools.get('Agent', 0)}): "
            f"Agent tool calls launch child sessions with their own initialization overhead."
        )
    if search_delta > 0:
        lines.append(
            f"- **Tool schema lookups** ({with_tools.get('ToolSearch', 0)} ToolSearch call(s) vs {base_tools.get('ToolSearch', 0)}): "
            f"ToolSearch fetches tool definitions on demand, adding schema-loading latency."
        )
    if len(lines) == 2:
        lines.append("- Cause not resolved from available activity signals.")
    return lines


def _why_more_tokens(with_run: dict[str, Any], base_run: dict[str, Any]) -> list[str]:
    with_label = with_run.get("label") or "With skills"
    base_label = base_run.get("label") or "No skills baseline"
    with_tokens = as_number(run_summary(with_run).get("token_count")) or 0
    base_tokens = as_number(run_summary(base_run).get("token_count")) or 0
    token_delta = with_tokens - base_tokens
    pct = round(token_delta / base_tokens * 100) if base_tokens > 0 else 0

    with_usage = _run_usage(with_run)
    base_usage = _run_usage(base_run)
    with_cache_read = as_number(with_usage.get("cache_read_input_tokens")) or 0
    base_cache_read = as_number(base_usage.get("cache_read_input_tokens")) or 0
    with_cache_create = as_number(with_usage.get("cache_creation_input_tokens")) or 0
    base_cache_create = as_number(base_usage.get("cache_creation_input_tokens")) or 0
    with_output = as_number(with_usage.get("output_tokens")) or 0
    base_output = as_number(base_usage.get("output_tokens")) or 0
    with_cost = as_number(with_usage.get("total_cost_usd"))
    base_cost = as_number(base_usage.get("total_cost_usd"))
    with_turns = _assistant_turns(with_run)
    base_turns = _assistant_turns(base_run)
    with_tools = count_map(with_run, "tool_counts")
    base_tools = count_map(base_run, "tool_counts")
    skill_calls = with_tools.get("Skill", 0)
    base_skill_calls = base_tools.get("Skill", 0)

    lines = [f"**Why {with_label} uses more tokens** (+{fmt_short(token_delta)} / +{pct}% vs {base_label}):", ""]

    cache_read_delta = with_cache_read - base_cache_read
    if cache_read_delta > 0 and with_cache_read > 0 and token_delta > 0:
        cache_pct = round(cache_read_delta / token_delta * 100)
        lines.append(
            f"- **Prompt cache re-reads are the dominant driver** "
            f"({fmt_short(with_cache_read)} vs {fmt_short(base_cache_read)}, "
            f"+{fmt_short(cache_read_delta)}, {cache_pct}% of the total token delta): "
            f"cache-read tokens represent context cached from previous turns being re-read on each "
            f"new turn. The {with_label} run accumulated a larger cached context window — primarily "
            f"skill documentation injected via {skill_calls} Skill call(s) — and then re-read that "
            f"context across all {with_turns} turns (vs {base_turns} turns in the {base_label} run)."
        )
    if skill_calls > base_skill_calls:
        lines.append(
            f"- **Skill documentation injected into context** ({skill_calls} Skill call(s) vs {base_skill_calls}): "
            f"each Skill invocation adds skill documentation to the context window. "
            f"That content is written into the prompt cache on first use, then re-read as cached context "
            f"on every subsequent turn — compounding the cache-read cost with each additional turn."
        )
    cache_create_delta = with_cache_create - base_cache_create
    if abs(cache_create_delta) > 1000:
        if cache_create_delta > 0:
            lines.append(
                f"- **New context written to cache** (+{fmt_short(cache_create_delta)} cache-creation tokens): "
                f"the {with_label} run wrote more new content into the prompt cache "
                f"(skill docs, tool schemas, or conversation history not present in the {base_label} run)."
            )
        else:
            lines.append(
                f"- **Less new context cached** ({fmt_short(abs(cache_create_delta))} fewer cache-creation tokens): "
                f"the {base_label} run actually wrote more fresh content into the cache."
            )
    output_delta = with_output - base_output
    if abs(output_delta) > 500:
        if output_delta < 0:
            lines.append(
                f"- **Output tokens decreased** ({fmt_short(with_output)} vs {fmt_short(base_output)}, "
                f"{fmt_short(abs(output_delta))} fewer): "
                f"the {with_label} run generated less text overall — skill guidance focused the agent's "
                f"responses, reducing exploratory output even as context consumption grew."
            )
        else:
            lines.append(
                f"- **Output tokens increased** ({fmt_short(with_output)} vs {fmt_short(base_output)}, "
                f"+{fmt_short(output_delta)}): "
                f"the {with_label} run generated more text, contributing directly to the token delta."
            )
    if with_cost is not None and base_cost is not None:
        cost_delta = with_cost - base_cost
        cost_pct = round(cost_delta / base_cost * 100) if base_cost > 0 else 0
        lines.append(
            f"- **Effective cost** (${with_cost:.4f} vs ${base_cost:.4f}, +${cost_delta:.4f} / +{cost_pct}%): "
            f"despite {pct}% more total tokens, the cost premium is much smaller because "
            f"cache-read tokens are priced significantly lower than regular input tokens."
        )
    if len(lines) == 2:
        lines.append("- Cause not resolved from available activity or usage signals.")
    return lines


def interpretation_section(runs: dict[str, dict[str, Any]], modes: list[str]) -> str:
    failed_quality = [runs[mode].get("label") or mode for mode in modes if run_quality_issues(runs[mode])]
    metric_name = comparable_metric_name(runs) or metric_name_for_runs(runs)
    lines = [
        "## Interpretation",
        "",
    ]
    if failed_quality:
        lines.append(
            "Quality comparison is incomplete because these runs failed a benchmark quality gate: "
            + ", ".join(failed_quality)
            + "."
        )
        lines.append(
            f"For this artifact, the missing/partial signal is `{metric_name}` reporting, not necessarily a Docker or Python execution crash."
        )
    else:
        lines.append("All available runs passed the benchmark quality gates captured by this report.")
    if len(modes) == 2:
        left, right = modes
        left_time = as_number(run_summary(runs[left]).get("elapsed_seconds"))
        right_time = as_number(run_summary(runs[right]).get("elapsed_seconds"))
        left_tokens = as_number(run_summary(runs[left]).get("token_count"))
        right_tokens = as_number(run_summary(runs[right]).get("token_count"))
        if left_time is not None and right_time is not None:
            faster_mode = left if left_time <= right_time else right
            slower_mode = right if left_time <= right_time else left
            faster = runs[faster_mode].get("label") or faster_mode
            time_delta = abs((right_time or 0) - (left_time or 0))
            lines.append(
                f"Runtime winner by wall-clock seconds: {faster} ({fmt_number(min(left_time, right_time))}s vs {fmt_number(max(left_time, right_time))}s, delta {fmt_number(time_delta)}s)."
            )
        if left_tokens is not None and right_tokens is not None:
            cheaper_mode = left if left_tokens <= right_tokens else right
            cheaper = runs[cheaper_mode].get("label") or cheaper_mode
            token_delta = abs((right_tokens or 0) - (left_tokens or 0))
            lines.append(
                f"Token-use winner: {cheaper} ({fmt_short(min(left_tokens, right_tokens))} vs {fmt_short(max(left_tokens, right_tokens))}, delta {fmt_short(token_delta)})."
            )
    lines.append(
        "Read cost winners only after checking the quality gates; a cheaper run that does not report the requested FL result is not a successful benchmark winner."
    )
    return "\n".join(lines)


def why_section(runs: dict[str, dict[str, Any]], modes: list[str]) -> str:
    """Explain why the with-skills run is slower or uses more tokens.

    Only rendered when with_skills is actually worse than the baseline on a
    given dimension — if skills help, there is nothing to explain here.
    """
    from ..modes import WITH_SKILLS_MODE

    if len(modes) != 2:
        return ""
    if WITH_SKILLS_MODE not in modes:
        return ""
    base_mode = next(m for m in modes if m != WITH_SKILLS_MODE)
    with_run = runs.get(WITH_SKILLS_MODE, {})
    base_run = runs.get(base_mode, {})
    with_time = as_number(run_summary(with_run).get("elapsed_seconds"))
    base_time = as_number(run_summary(base_run).get("elapsed_seconds"))
    with_tokens = as_number(run_summary(with_run).get("token_count"))
    base_tokens = as_number(run_summary(base_run).get("token_count"))
    sections: list[list[str]] = []
    if with_time is not None and base_time is not None and with_time > base_time:
        sections.append(_why_slower(with_run, base_run))
    if with_tokens is not None and base_tokens is not None and with_tokens > base_tokens:
        sections.append(_why_more_tokens(with_run, base_run))
    if not sections:
        return ""
    lines = ["## Why", ""]
    for section_lines in sections:
        lines.extend(section_lines)
        lines.append("")
    return "\n".join(lines)


def mixed_metric_note(runs: dict[str, dict[str, Any]]) -> str:
    parts = []
    for run in runs.values():
        metric = run.get("validation_metric")
        name = canonical_metric_name(metric.get("name")) if isinstance(metric, dict) else ""
        if name:
            parts.append(f"{run.get('label') or run.get('mode')}: {name}")
    return "; ".join(parts)


def chart_number(value: Any, kind: str) -> float | None:
    number = as_number(value)
    if number is None:
        return None
    if kind == "percent":
        return max(0.0, min(1.0, number))
    return max(0.0, number)


def chart_value_display(value: Any, kind: str) -> str:
    if value is None:
        return "NA"
    if kind == "short":
        return fmt_short(value)
    if kind == "percent":
        number = as_number(value)
        return "NA" if number is None else f"{number * 100:.0f}%"
    return fmt_number(value)


def benchmark_chart_metrics(runs: dict[str, dict[str, Any]], metric_name: str | None) -> list[dict[str, Any]]:
    return [
        {
            "label": "Runtime seconds",
            "kind": "number",
            "value": lambda run: run_summary(run).get("elapsed_seconds"),
        },
        {
            "label": "Total tokens",
            "kind": "short",
            "value": lambda run: run_summary(run).get("token_count"),
        },
        {
            "label": "Commands",
            "kind": "number",
            "value": lambda run: run_activity(run).get("command_count"),
        },
        {
            "label": "Structure score",
            "kind": "percent",
            "value": structure_score,
        },
        {
            "label": f"Metrics ({metric_name or 'result'})",
            "kind": "number",
            "value": lambda run: metric_value(run, metric_name),
        },
    ]


def chart_mode_label(mode: str, run: dict[str, Any]) -> str:
    if mode == "without_skills":
        return "No skills"
    if mode == "with_skills":
        return "With skills"
    return str(run.get("label") or MODE_LABELS.get(mode, mode))


def embedded_bar_chart(runs: dict[str, dict[str, Any]]) -> str:
    metric_name = comparable_metric_name(runs)
    if metric_name is None and metric_names_for_runs(runs):
        note = markdown_cell(mixed_metric_note(runs))
        return f"<section><h3>Metrics (mixed validation metrics)</h3><p>Not comparable: {note}</p></section>"
    modes = list(runs)
    metrics = benchmark_chart_metrics(runs, metric_name)
    width = 1180
    height = 430
    margin_x = 32
    top = 104
    panel_gap = 18
    panel_w = (width - margin_x * 2 - panel_gap * (len(metrics) - 1)) / len(metrics)
    axis_y = 328
    chart_h = 170
    bar_gap = 24 if len(modes) <= 2 else 12
    available_bar_w = max(40.0, panel_w - 44)
    bar_w = max(18.0, min(38.0, (available_bar_w - bar_gap * max(0, len(modes) - 1)) / max(1, len(modes))))
    colors = {
        "without_skills": "#16a34a",
        "with_skills": "#2563eb",
    }
    fallback_colors = ("#2563eb", "#16a34a", "#7c3aed", "#f97316")
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<text x="32" y="35" font-family="Arial, sans-serif" font-size="22" font-weight="700" fill="#111827">Run comparison</text>',
        '<text x="32" y="58" font-family="Arial, sans-serif" font-size="13" fill="#4b5563">Metrics are mode-local. Missing scalar results are shown as NA instead of drawing a numeric bar.</text>',
    ]
    for metric_index, item in enumerate(metrics):
        x0 = margin_x + metric_index * (panel_w + panel_gap)
        title = html.escape(str(item["label"]))
        values = [chart_number(item["value"](runs[mode]), item["kind"]) for mode in modes]
        numeric_values = [value for value in values if value is not None]
        maximum = max(numeric_values) if numeric_values else 1.0
        if maximum == 0:
            maximum = 1.0
        bar_group_w = len(modes) * bar_w + max(0, len(modes) - 1) * bar_gap
        bar_start_x = x0 + max(14.0, (panel_w - bar_group_w) / 2)
        lines.extend(
            [
                f'<text x="{x0:.1f}" y="{top:.1f}" font-family="Arial, sans-serif" font-size="16" font-weight="700" fill="#111827">{title}</text>',
                f'<line x1="{x0:.1f}" y1="{axis_y}" x2="{x0 + panel_w:.1f}" y2="{axis_y}" stroke="#d1d5db" stroke-width="1"/>',
                f'<line x1="{x0:.1f}" y1="{axis_y - chart_h}" x2="{x0:.1f}" y2="{axis_y}" stroke="#d1d5db" stroke-width="1"/>',
            ]
        )
        for bar_index, mode in enumerate(modes):
            run = runs[mode]
            value = item["value"](run)
            numeric_value = values[bar_index]
            bx = bar_start_x + bar_index * (bar_w + bar_gap)
            run_label = html.escape(chart_mode_label(mode, run))
            color = colors.get(mode, fallback_colors[bar_index % len(fallback_colors)])
            if numeric_value is None:
                lines.extend(
                    [
                        f'<rect x="{bx:.1f}" y="{axis_y - 24}" width="{bar_w:.1f}" height="20" fill="#e5e7eb" rx="3"/>',
                        f'<text x="{bx + bar_w / 2:.1f}" y="{axis_y - 9}" text-anchor="middle" font-family="Arial, sans-serif" font-size="11" font-weight="700" fill="#4b5563">NA</text>',
                    ]
                )
            else:
                height_px = max(4.0, numeric_value / maximum * chart_h)
                by = axis_y - height_px
                value_text = html.escape(chart_value_display(value, item["kind"]))
                lines.extend(
                    [
                        f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bar_w:.1f}" height="{height_px:.1f}" fill="{color}" rx="3"/>',
                        f'<text x="{bx + bar_w / 2:.1f}" y="{by - 7:.1f}" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#111827">{value_text}</text>',
                    ]
                )
            lines.append(
                f'<text x="{bx + bar_w / 2:.1f}" y="{axis_y + 19}" text-anchor="middle" font-family="Arial, sans-serif" font-size="11" fill="#374151">{run_label}</text>'
            )
    legend_x = 32
    legend_y = 392
    for index, mode in enumerate(modes):
        run = runs[mode]
        color = colors.get(mode, fallback_colors[index % len(fallback_colors)])
        x = legend_x + index * 220
        label = html.escape(str(run.get("label") or MODE_LABELS.get(mode, mode)))
        lines.extend(
            [
                f'<rect x="{x}" y="{legend_y}" width="14" height="14" fill="{color}" rx="2"/>',
                f'<text x="{x + 22}" y="{legend_y + 12}" font-family="Arial, sans-serif" font-size="13" fill="#111827">{label}</text>',
            ]
        )
    lines.append("</svg>")
    return "\n".join(lines)


def outcome_metrics_table(runs: dict[str, dict[str, Any]], modes: list[str] | None = None) -> str:
    modes = modes or mode_names(BENCHMARK_RUNS)
    comparable_name = comparable_metric_name(runs)
    metric_name = comparable_name or metric_name_for_runs(runs)
    labels = [markdown_cell((runs.get(mode) or {}).get("label") or MODE_LABELS.get(mode, mode)) for mode in modes]
    values = [metric_display(runs.get(mode, {}), comparable_name) for mode in modes]
    return "\n".join(
        [
            "| Metric | " + " | ".join(labels) + " |",
            "|---|" + "|".join("---" for _ in modes) + "|",
            f"| Metrics ({markdown_cell(metric_name)}) | "
            + " | ".join(markdown_cell(value) for value in values)
            + " |",
        ]
    )


def status_table(runs: dict[str, dict[str, Any]], modes: list[str]) -> str:
    lines = ["| Run | Status | Analysis |", "|---|---|---|"]
    for mode in modes:
        run = runs[mode]
        lines.append(
            f"| {markdown_cell(run['label'])} | {markdown_cell(human_readable_status(run))} | "
            f"{markdown_cell(run_analysis(run))} |"
        )
    return "\n".join(lines)


def job_run_status_section(runs: dict[str, dict[str, Any]], modes: list[str]) -> str:
    lines = [
        "## Job Run Status",
        "",
        "This section tracks whether the generated NVFLARE job or simulator actually ran. Agent/container exit code 0 only means the agent process finished; it does not prove the generated job executed.",
        "",
        "| Run | Job run status | Evidence | Action |",
        "|---|---|---|---|",
    ]
    for mode in modes:
        run = runs[mode]
        lines.append(
            f"| {markdown_cell(run.get('label') or mode)} | {markdown_cell(job_run_status(run))} | "
            f"{markdown_cell(job_run_status_reason(run))} | {markdown_cell(job_run_action(run))} |"
        )
    return "\n".join(lines)


def job_execution_summary(runs: dict[str, dict[str, Any]], modes: list[str]) -> str:
    return "; ".join(
        f"{runs[mode].get('label') or mode}: {job_run_status(runs[mode])} ({job_run_status_reason(runs[mode])})"
        for mode in modes
    )


def failure_analysis_section(runs: dict[str, dict[str, Any]], modes: list[str]) -> str:
    lines = []
    for mode in modes:
        run = runs[mode]
        label = run.get("label") or mode
        status_kind = run_status_kind(run)
        lines.append(f"### {label}")
        lines.append("")
        lines.append(f"- Job run status: {job_run_status(run)} — {job_run_status_reason(run)}")
        if status_kind == "passed":
            metric = metric_display(run, comparable_metric_name(runs))
            label_text = metric_value_label(run, comparable_metric_name(runs))
            if label_text:
                metric = f"{metric} ({label_text})"
            lines.append(f"- Outcome: passed. {metric}.")
        elif status_kind == "needs review":
            lines.append(
                "- Outcome: needs review. The agent process completed, but benchmark quality checks found issues."
            )
            for issue in run_quality_issues(run):
                lines.append(f"- Issue: {issue}")
        elif status_kind == "failed":
            lines.append(f"- Outcome: failed. {failure_root_cause(run)}")
            evidence = failure_evidence(run)
            if evidence:
                lines.append(f"- Evidence: {evidence}")
        else:
            lines.append("- Outcome: missing. No run artifacts were found for this mode.")
        record = run.get("record") if isinstance(run.get("record"), dict) else {}
        signal = quality_signal(record)
        if signal.get("evidence"):
            lines.append(f"- Metric evidence: {signal['evidence']}")
        if status_kind == "passed":
            bash_blocked = bash_blocked_diagnostic(run, recovered=True)
            if bash_blocked:
                lines.append(f"- Recovered Bash/tool issue: {bash_blocked}")
            for diagnostic in command_failure_diagnostics(run):
                if "not recovered in this run" not in diagnostic:
                    lines.append(f"- Recovered command evidence: {diagnostic}")
        else:
            bash_blocked = bash_blocked_diagnostic(run)
            if bash_blocked:
                lines.append(f"- Bash blocking: {bash_blocked}")
            for diagnostic in command_failure_diagnostics(run):
                lines.append(f"- Command evidence: {diagnostic}")
            success_evidence = successful_job_evidence(run)
            if success_evidence:
                lines.append(f"- Recovery evidence: {success_evidence}.")
            metric_gap = metric_reporting_gap_evidence(run)
            if metric_gap:
                lines.append(f"- {metric_gap}")
        for note in dependency_reference_notes(run):
            lines.append(f"- Dependency reference: {note}")
        lines.append("")
    return "\n".join(lines).rstrip()


def runtime_table(runs: dict[str, dict[str, Any]], modes: list[str]) -> str:
    lines = ["| Run | Elapsed seconds | Tokens | Commands |", "|---|---:|---:|---:|"]
    for mode in modes:
        run = runs[mode]
        summary = run.get("run") if isinstance(run.get("run"), dict) else {}
        activity = run.get("activity") if isinstance(run.get("activity"), dict) else {}
        lines.append(
            f"| {markdown_cell(run['label'])} | {fmt_number(summary.get('elapsed_seconds'))} | "
            f"{fmt_number(summary.get('token_count'))} | {fmt_number(activity.get('command_count'))} |"
        )
    return "\n".join(lines)


def benchmark_report(root: Path, runs: dict[str, dict[str, Any]]) -> str:
    modes = mode_names(BENCHMARK_RUNS)
    missing_metrics = missing_result_metrics_section(runs, modes)
    cost_comparison = cost_comparison_section(runs, modes)
    quality_gate_summary = "; ".join(
        f"{runs[mode].get('label') or mode}: {benchmark_outcome(runs[mode])}" for mode in modes
    )
    missing_metric_summary = "; ".join(
        f"{runs[mode].get('label') or mode}: {run_result_metric_status(runs[mode])}"
        for mode in modes
        if run_quality_issues(runs[mode])
    )
    input_protection_summary = "; ".join(
        f"{runs[mode].get('label') or mode}: {source_input_protection_display(runs[mode])}" for mode in modes
    )
    artifact_summary_text = "; ".join(
        f"{runs[mode].get('label') or mode}: {artifact_summary(runs[mode])}" for mode in modes
    )
    lines = [
        "# Agent Benchmark Insights",
        "",
        f"Result root: `{root}`",
        "",
        "## Executive Summary",
        "",
        "| Signal | Value |",
        "|---|---|",
        f"| Status | {markdown_cell(status_summary(runs, modes))} |",
        f"| Agent/model | {markdown_cell(run_identity_summary(runs, modes))} |",
        f"| Job execution | {markdown_cell(job_execution_summary(runs, modes))} |",
        f"| FL result quality gate | {markdown_cell(quality_gate_summary)} |",
        f"| Missing/partial result metrics | {markdown_cell(missing_metric_summary or 'none')} |",
        f"| Source input protection | {markdown_cell(input_protection_summary)} |",
        f"| Captured generated artifacts | {markdown_cell(artifact_summary_text)} |",
        "",
        "## Status",
        "",
        status_table(runs, modes),
        "",
        "## Run Identity",
        "",
        run_identity_table(runs, modes),
        "",
        job_run_status_section(runs, modes),
        "",
        "## Failure Analysis",
        "",
        failure_analysis_section(runs, modes),
        "",
    ]
    if missing_metrics:
        lines.extend([missing_metrics, ""])
    lines.extend(
        [
            "## Metrics",
            "",
            embedded_bar_chart({mode: runs[mode] for mode in modes}),
            "",
            outcome_metrics_table(runs, modes),
            "",
            "## Quality Signals",
            "",
            quality_signal_table(runs, modes),
            "",
            "## Output Changes",
            "",
            output_changes_table(runs, modes),
            "",
            "## Outcome Details",
            "",
            outcome_details_table(runs, modes),
            "",
            "## Structure Correctness",
            "",
            "The structure checks look for the core converted source files and captured runtime/export artifacts. They are report signals, not a substitute for running the generated job.",
            "",
            structure_correctness_table(runs, modes),
            "",
            structure_trees_section(runs, modes),
            "",
            "## Activity Insights",
            "",
            activity_insights_table(runs, modes),
            "",
            "## Event Mix",
            "",
            event_mix_table(runs, modes),
            "",
        ]
    )
    if cost_comparison:
        lines.extend([cost_comparison, ""])
    why = why_section(runs, modes)
    if why:
        lines.extend([why, ""])
    lines.extend(
        [
            "## Runtime",
            "",
            runtime_table(runs, modes),
            "",
            interpretation_section(runs, modes),
            "",
            "## Artifacts",
            "",
            "- `metrics_report.md`",
            "- `metrics_report.html`",
            "- `records/`",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    runs = collect_benchmark_runs(args.root)
    output = args.output or args.root / "benchmark_insights.md"
    output.write_text(benchmark_report(args.root, runs), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
