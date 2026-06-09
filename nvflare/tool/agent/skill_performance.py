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

"""Read-only process-performance reporting for NVFLARE-owned agent skills."""

import json
import math
import os
from pathlib import Path
from typing import Any, Optional

EVALS_FILE = "evals/evals.json"
SCHEMA_VERSION = "1"
SUPPORTED_SCHEMA_VERSIONS = {SCHEMA_VERSION}
MAX_RECORD_FILES = int(os.environ.get("NVFLARE_AGENT_MAX_RECORD_FILES", "10000"))
MAX_RECORD_BYTES = int(os.environ.get("NVFLARE_AGENT_MAX_RECORD_BYTES", str(5 * 1024 * 1024)))
ALLOWED_STATUSES = {"pass", "fail", "missing", "not_applicable", "non_scoring_note"}
SUMMARY_METRICS = (
    "elapsed_seconds",
    "token_count",
    "turns_to_acceptable",
    "user_correction_count",
    "agent_self_correction_count",
    "missed_instruction_count",
    "conversion_quality",
    "layout_violations",
    "workflow_violations",
    "evidence_gap_violations",
)


class SkillPerformanceError(ValueError):
    """Runtime process-record error surfaced as a structured CLI error."""

    def __init__(self, code: str, message: str, hint: str = "", detail: str = ""):
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint
        self.detail = detail


def summarize_skill_performance(
    *,
    skill_name: Optional[str] = None,
    case_id: Optional[str] = None,
    records_path: Optional[Path | str] = None,
    source=None,
) -> dict:
    """Summarize packaged process metrics and optional runtime process records.

    This read-only reporting surface does not run skills, evaluate artifacts,
    infer correctness fields, mutate runtime records, or fill missing runtime
    fields from the currently packaged skill manifest.
    """
    from nvflare.tool.agent import skill_manager

    source = source or skill_manager.find_skill_source()
    selected_skills = _select_skills(source.manifest.get("skills") or [], skill_name)
    contracts = _metric_contracts(source.root, selected_skills, case_id=case_id)
    if case_id and not contracts:
        raise ValueError(f"NVFLARE eval case not found: {case_id}")

    resolved_records_path = Path(records_path).expanduser() if records_path else None
    loaded_records, records_status = (
        _load_records(resolved_records_path) if resolved_records_path else ([], "not_supplied")
    )
    selected_names = {skill["name"] for skill in selected_skills}
    matching_records = _filter_records(loaded_records, selected_names=selected_names, case_id=case_id)
    record_warnings = []
    if loaded_records and not selected_names and not skill_name:
        record_warnings.append(
            "No packaged skill names were available from the manifest; runtime records were not matched to summaries."
        )

    return {
        "source": {
            "type": source.source_type,
            "root": str(source.root),
            "skill_count": len(source.manifest.get("skills") or []),
        },
        "records_root": str(resolved_records_path) if resolved_records_path else None,
        "records_status": records_status,
        "filters": {
            "skill": skill_name,
            "case_id": case_id,
        },
        "metric_contracts": contracts,
        "summaries": _summaries(matching_records, selected_skills),
        "records": [_compact_record(record) for record in matching_records],
        "record_warnings": record_warnings,
    }


def format_skill_performance_human(data: dict) -> str:
    """Render a compact human-readable summary."""
    source = data.get("source") or {}
    filters = data.get("filters") or {}
    lines = [
        "NVFLARE Agent Skill Performance",
        f"source: {source.get('type', 'unknown')} ({source.get('skill_count', 0)} skills, root: {source.get('root', '')})",
        f"records root: {data.get('records_root', '')} ({data.get('records_status', 'unknown')})",
    ]
    filter_parts = []
    if filters.get("skill"):
        filter_parts.append(f"skill={filters['skill']}")
    if filters.get("case_id"):
        filter_parts.append(f"case={filters['case_id']}")
    if filter_parts:
        lines.append(f"filters: {', '.join(filter_parts)}")

    _append_contracts(lines, data.get("metric_contracts") or [])
    _append_summaries(lines, data.get("summaries") or [])
    return "\n".join(lines)


def _select_skills(skills: list[dict], skill_name: Optional[str]) -> list[dict]:
    if not skill_name:
        return skills

    selected = [skill for skill in skills if skill.get("name") == skill_name]
    if not selected:
        raise ValueError(f"NVFLARE skill not found: {skill_name}")
    return selected


def _metric_contracts(skills_root: Path, skills: list[dict], *, case_id: Optional[str]) -> list[dict]:
    contracts = []
    for skill in skills:
        skill_dir = skills_root / skill["relative_path"]
        for eval_case in _load_eval_cases(skill_dir):
            if case_id and eval_case.get("id") != case_id:
                continue
            contracts.append(
                {
                    "skill": skill["name"],
                    "skill_version": skill.get("skill_version"),
                    "case_id": eval_case.get("id"),
                    "metrics": _process_metrics(eval_case),
                }
            )
    return contracts


def _load_eval_cases(skill_dir: Path) -> list[dict]:
    evals_path = skill_dir / EVALS_FILE
    if not evals_path.is_file():
        return []
    data = _read_json_file(evals_path)
    return [eval_case for eval_case in data.get("evals") or [] if isinstance(eval_case, dict)]


def _process_metrics(eval_case: dict) -> list[dict]:
    nvflare = eval_case.get("nvflare") or {}
    process_metrics = nvflare.get("process_metrics") or []
    metrics = []
    for metric in process_metrics:
        if not isinstance(metric, dict):
            continue
        metric_id = metric.get("id")
        if metric_id:
            metrics.append({"id": metric_id, "description": metric.get("description", "")})
    return metrics


def _load_records(records_path: Path) -> tuple[list[dict], str]:
    if not records_path.exists():
        raise SkillPerformanceError(
            "PROCESS_RECORDS_PATH_NOT_FOUND",
            f"Process records path does not exist: {records_path}.",
            "Pass an existing --records file or directory.",
        )

    if records_path.is_file():
        return _read_record_file(records_path), "loaded"

    record_files = []
    for dirpath, dirnames, filenames in os.walk(records_path, followlinks=False):
        root = Path(dirpath)
        dirnames[:] = [dirname for dirname in dirnames if not (root / dirname).is_symlink()]
        for filename in filenames:
            path = root / filename
            if path.is_symlink() or not path.is_file():
                continue
            if path.suffix in (".json", ".jsonl"):
                record_files.append(path)
                if len(record_files) >= MAX_RECORD_FILES + 1:
                    raise SkillPerformanceError(
                        "PROCESS_RECORD_FILE_LIMIT_EXCEEDED",
                        f"Process records path has more than {MAX_RECORD_FILES} JSON/JSONL files: {records_path}.",
                        "Pass a narrower --records path or archive older benchmark records.",
                    )
    records = []
    for path in sorted(record_files):
        records.extend(_read_record_file(path))
    records.sort(key=lambda record: record.get("_sort_timestamp") or 0, reverse=True)
    for record in records:
        record.pop("_sort_timestamp", None)
    return records, "loaded"


def _read_record_file(path: Path) -> list[dict]:
    _validate_record_file_size(path)
    if path.suffix == ".jsonl":
        records = []
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as e:
            raise SkillPerformanceError(
                "PROCESS_RECORD_FILE_UNREADABLE",
                f"Could not read process record file {path}: {e}.",
                "Fix record file permissions or pass a different --records path.",
            ) from e
        for line_no, line in enumerate(lines, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                record = json.loads(stripped)
            except json.JSONDecodeError as e:
                raise SkillPerformanceError(
                    "INVALID_PROCESS_RECORD_JSONL",
                    f"Invalid JSONL process record in {path}:{line_no}: {e}.",
                    "Fix or remove the malformed process record file.",
                ) from e
            if isinstance(record, dict):
                _validate_record(record, path)
                records.append(_with_record_metadata(record, path))
        return records

    data = _read_record_json_file(path)
    if isinstance(data, list):
        records = []
        for record in data:
            if isinstance(record, dict):
                _validate_record(record, path)
                records.append(_with_record_metadata(record, path))
        return records
    if isinstance(data, dict):
        if isinstance(data.get("records"), list):
            records = []
            for record in data["records"]:
                if isinstance(record, dict):
                    _validate_record(record, path)
                    records.append(_with_record_metadata(record, path))
            return records
        _validate_record(data, path)
        return [_with_record_metadata(data, path)]
    return []


def _validate_record_file_size(path: Path) -> None:
    try:
        size = path.stat().st_size
    except OSError as e:
        raise SkillPerformanceError(
            "PROCESS_RECORD_FILE_UNREADABLE",
            f"Could not stat process record file {path}: {e}.",
            "Fix record file permissions or pass a different --records path.",
        ) from e
    if size > MAX_RECORD_BYTES:
        raise SkillPerformanceError(
            "PROCESS_RECORD_FILE_TOO_LARGE",
            f"Process record file exceeds {MAX_RECORD_BYTES} bytes: {path}.",
            "Pass a narrower --records path, remove oversized files, or raise NVFLARE_AGENT_MAX_RECORD_BYTES.",
            detail=f"size_bytes={size}",
        )


def _read_record_json_file(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise SkillPerformanceError(
            "INVALID_PROCESS_RECORD_JSON",
            f"Invalid JSON process record in {path}: {e}.",
            "Fix or remove the malformed process record file.",
        ) from e
    except (OSError, UnicodeDecodeError) as e:
        raise SkillPerformanceError(
            "PROCESS_RECORD_FILE_UNREADABLE",
            f"Could not read process record file {path}: {e}.",
            "Fix record file permissions, encoding, or pass a different --records path.",
        ) from e


def _read_json_file(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"invalid JSON file {path}: {e}") from e


def _with_record_metadata(record: dict, path: Path) -> dict:
    copied = dict(record)
    copied["_path"] = str(path)
    copied["_timestamp"] = _record_timestamp(record, path)
    copied["_sort_timestamp"] = _record_sort_timestamp(record, path)
    return copied


def _validate_record(record: dict, path: Path) -> None:
    schema_version = record.get("schema_version")
    if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        supported = ", ".join(sorted(SUPPORTED_SCHEMA_VERSIONS))
        raise SkillPerformanceError(
            "UNSUPPORTED_SCHEMA_VERSION",
            f"Unsupported runtime process record schema_version {schema_version!r} in {path}.",
            f"Use records with a supported schema_version: {supported}.",
        )
    for category in ("mandatory_behavior", "prohibited_behavior", "optional_behavior"):
        _validate_behavior_statuses(record.get(category), category, path)


def _validate_behavior_statuses(behavior_map: Any, category: str, path: Path) -> None:
    if behavior_map is None:
        return
    if not isinstance(behavior_map, dict):
        raise SkillPerformanceError(
            "AGENT_SKILL_PERFORMANCE_FAILED",
            f"Runtime process record {category} must be an object in {path}.",
        )
    for behavior_id, entry in behavior_map.items():
        if not isinstance(entry, dict):
            raise SkillPerformanceError(
                "AGENT_SKILL_PERFORMANCE_FAILED",
                f"Runtime process record behavior entry must be an object: {category}.{behavior_id} in {path}.",
            )
        status = entry.get("status")
        if status not in ALLOWED_STATUSES:
            raise SkillPerformanceError(
                "AGENT_SKILL_PERFORMANCE_FAILED",
                f"Unsupported behavior status {status!r} for {category}.{behavior_id} in {path}.",
            )


def _record_timestamp(record: dict, path: Path) -> Optional[str]:
    timestamp = record.get("timestamp")
    if isinstance(timestamp, str):
        return timestamp
    if path.stem and path.stem != "record":
        return path.stem
    try:
        return str(path.stat().st_mtime_ns)
    except OSError:
        return None


def _record_sort_timestamp(record: dict, path: Path) -> int:
    timestamp = record.get("timestamp")
    if isinstance(timestamp, str):
        try:
            from datetime import datetime

            text = timestamp[:-1] + "+00:00" if timestamp.endswith("Z") else timestamp
            return int(datetime.fromisoformat(text).timestamp() * 1_000_000_000)
        except ValueError:
            pass
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return -1


def _filter_records(records: list[dict], *, selected_names: set[str], case_id: Optional[str]) -> list[dict]:
    matching = []
    for record in records:
        record_skill = record.get("skill") or record.get("skill_name")
        if record_skill not in selected_names:
            continue
        if case_id and record.get("case_id") != case_id:
            continue
        matching.append(record)
    return matching


def _summaries(records: list[dict], skills: list[dict]) -> list[dict]:
    if not records:
        return []

    groups = {}
    for record in records:
        skill = record.get("skill") or record.get("skill_name")
        case_id = record.get("case_id") or "unknown"
        skill_version = record.get("skill_version")
        key = _summary_key(skill, skill_version, case_id, record.get("run_mode"), record.get("source_hash"))
        groups.setdefault(key, []).append(record)

    summaries = []
    for key, group_records in sorted(groups.items(), key=lambda item: _sortable_summary_key(item[0])):
        skill, skill_version, case_id, run_mode, source_hash = key
        summary = {
            "skill": skill,
            "skill_version": skill_version,
            "case_id": case_id,
            "record_count": len(group_records),
        }
        for metric_id in SUMMARY_METRICS:
            summary[metric_id] = _numeric_summary(
                [_process_metric(record, metric_id) for record in group_records],
                len(group_records),
            )
        if run_mode is not None:
            summary["run_mode"] = run_mode
        if source_hash is not None:
            summary["source_hash"] = source_hash
        summaries.append(summary)
    return summaries


def _summary_key(
    skill: Optional[str], skill_version: Optional[str], case_id: Optional[str], run_mode: Any, source_hash: Any
) -> tuple:
    return (skill, skill_version, case_id, run_mode, source_hash)


def _sortable_summary_key(key: tuple) -> tuple:
    return tuple("" if value is None else str(value) for value in key)


def _process_metric(record: dict, metric_id: str) -> Optional[float]:
    process_metrics = record.get("process_metrics") or {}
    if isinstance(process_metrics, dict):
        return _as_float(process_metrics.get(metric_id))
    return None


def _numeric_summary(values: list[Optional[float]], total: int) -> dict:
    available_values = [value for value in values if value is not None]
    if not available_values:
        return {"avg": None, "available": 0, "unavailable": total}
    return {
        "avg": _round(sum(available_values) / len(available_values)),
        "available": len(available_values),
        "unavailable": total - len(available_values),
    }


def _compact_record(record: dict) -> dict:
    compact = {
        "path": record.get("_path"),
        "timestamp": record.get("_timestamp"),
        "skill": record.get("skill") or record.get("skill_name"),
        "skill_version": record.get("skill_version"),
        "case_id": record.get("case_id"),
    }
    if record.get("run_mode") is not None:
        compact["run_mode"] = record.get("run_mode")
    if record.get("source_hash") is not None:
        compact["source_hash"] = record.get("source_hash")
    return compact


def _append_contracts(lines: list[str], contracts: list[dict]) -> None:
    lines.append("")
    lines.append("metric contracts:")
    if not contracts:
        lines.append("  none")
        return

    for contract in contracts:
        metrics = contract.get("metrics") or []
        metric_text = ", ".join(metric["id"] for metric in metrics) if metrics else "none"
        lines.append(
            "  - "
            f"{contract.get('skill', '<unknown>')} / {contract.get('case_id', '<unknown>')}: "
            f"{len(metrics)} metrics ({metric_text})"
        )


def _append_summaries(lines: list[str], summaries: list[dict]) -> None:
    lines.append("")
    lines.append("runtime summaries:")
    if not summaries:
        lines.append("  none")
        return

    for summary in summaries:
        lines.append(
            "  - "
            f"{summary.get('skill', '<unknown>')} / {summary.get('case_id', '<unknown>')}: "
            f"records {summary.get('record_count', 0)}"
        )
        for metric_id in SUMMARY_METRICS:
            metric = summary.get(metric_id) or {}
            if metric.get("available"):
                lines.append(
                    "      "
                    f"{metric_id}: avg {_format_number(metric.get('avg'))} "
                    f"(n {metric.get('available', 0)}, missing {metric.get('unavailable', 0)})"
                )


def _as_float(value: Any) -> Optional[float]:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _round(value: float) -> float:
    return round(value, 3)


def _format_number(value: Any, *, default: str = "n/a") -> str:
    if value is None:
        return default
    numeric = _as_float(value)
    if numeric is None:
        return str(value)
    if numeric.is_integer():
        return str(int(numeric))
    return f"{numeric:.3g}"
