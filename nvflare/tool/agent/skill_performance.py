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
from pathlib import Path
from typing import Any, Optional

DEFAULT_RECORDS_ROOT = Path("~/.nvflare/agent_skill_eval_runs").expanduser()
EVALS_FILE = "evals/evals.json"
SUMMARY_METRICS = (
    "elapsed_seconds",
    "token_count",
    "turns_to_acceptable",
    "user_correction_count",
    "agent_self_correction_count",
    "conversion_quality",
)


def summarize_skill_performance(
    *,
    skill_name: Optional[str] = None,
    case_id: Optional[str] = None,
    records_path: Optional[Path | str] = None,
    source=None,
) -> dict:
    """Summarize packaged process metrics and optional runtime process records.

    This is the Milestone 6 reporting surface. It does not run skills, evaluate
    artifacts, infer scores, or mutate runtime records.
    """
    from nvflare.tool.agent import skill_manager

    source = source or skill_manager.find_skill_source()
    selected_skills = _select_skills(source.manifest.get("skills") or [], skill_name)
    contracts = _metric_contracts(source.root, selected_skills, case_id=case_id)
    if case_id and not contracts:
        raise ValueError(f"NVFLARE eval case not found: {case_id}")

    resolved_records_path = Path(records_path).expanduser() if records_path else DEFAULT_RECORDS_ROOT
    loaded_records, records_status = _load_records(resolved_records_path, explicit=records_path is not None)
    selected_names = {skill["name"] for skill in selected_skills}
    matching_records = _filter_records(loaded_records, selected_names=selected_names, case_id=case_id)

    return {
        "source": {
            "type": source.source_type,
            "root": str(source.root),
            "skill_count": len(source.manifest.get("skills") or []),
        },
        "records_root": str(resolved_records_path),
        "records_status": records_status,
        "filters": {
            "skill": skill_name,
            "case_id": case_id,
        },
        "metric_contracts": contracts,
        "summaries": _summaries(matching_records, selected_skills),
        "records": [_compact_record(record) for record in matching_records],
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
    process_evaluation = nvflare.get("process_evaluation") or {}
    metrics = []
    for metric in process_evaluation.get("metrics") or []:
        metric_id = metric.get("id")
        if metric_id:
            metrics.append({"id": metric_id, "description": metric.get("description", "")})
    return metrics


def _load_records(records_path: Path, *, explicit: bool) -> tuple[list[dict], str]:
    if not records_path.exists():
        if explicit:
            raise ValueError(f"process records path does not exist: {records_path}")
        return [], "not_found"

    if records_path.is_file():
        return _read_record_file(records_path), "loaded"

    records = []
    for path in sorted(records_path.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        if path.suffix in (".json", ".jsonl"):
            records.extend(_read_record_file(path))
    records.sort(key=lambda record: record.get("_timestamp") or "", reverse=True)
    return records, "loaded"


def _read_record_file(path: Path) -> list[dict]:
    if path.suffix == ".jsonl":
        records = []
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                record = json.loads(stripped)
            except json.JSONDecodeError as e:
                raise ValueError(f"invalid JSONL record in {path}:{line_no}: {e}") from e
            if isinstance(record, dict):
                records.append(_with_record_metadata(record, path))
        return records

    data = _read_json_file(path)
    if isinstance(data, list):
        return [_with_record_metadata(record, path) for record in data if isinstance(record, dict)]
    if isinstance(data, dict):
        if isinstance(data.get("records"), list):
            return [_with_record_metadata(record, path) for record in data["records"] if isinstance(record, dict)]
        return [_with_record_metadata(data, path)]
    return []


def _read_json_file(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"invalid JSON file {path}: {e}") from e


def _with_record_metadata(record: dict, path: Path) -> dict:
    copied = dict(record)
    copied["_path"] = str(path)
    copied["_timestamp"] = _record_timestamp(record, path)
    return copied


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

    skill_versions = {skill["name"]: skill.get("skill_version") for skill in skills}
    groups = {}
    for record in records:
        skill = record.get("skill") or record.get("skill_name")
        case_id = record.get("case_id") or "unknown"
        skill_version = record.get("skill_version") or skill_versions.get(skill)
        key = (skill, skill_version, case_id)
        groups.setdefault(key, []).append(record)

    summaries = []
    for (skill, skill_version, case_id), group_records in sorted(groups.items()):
        summary = {
            "skill": skill,
            "skill_version": skill_version,
            "case_id": case_id,
            "record_count": len(group_records),
            "eval_pass_rate": _eval_pass_rate(group_records),
            "score": _numeric_summary([_score_value(record) for record in group_records], len(group_records)),
        }
        for metric_id in SUMMARY_METRICS:
            summary[metric_id] = _numeric_summary(
                [_process_metric(record, metric_id) for record in group_records],
                len(group_records),
            )
        summaries.append(summary)
    return summaries


def _eval_pass_rate(records: list[dict]) -> float:
    if not records:
        return 0.0
    passed = sum(1 for record in records if record.get("eval_passed") is True)
    return _round(passed / len(records))


def _score_value(record: dict) -> Optional[float]:
    score = record.get("score") or {}
    return _as_float(score.get("value"))


def _process_metric(record: dict, metric_id: str) -> Optional[float]:
    process_metrics = record.get("process_metrics") or {}
    if isinstance(process_metrics, dict):
        value = _as_float(process_metrics.get(metric_id))
        if value is not None:
            return value

    # M6 accepts a few common harness aliases, but it does not infer missing
    # values from transcript text or raw artifacts.
    aliases = {
        "elapsed_seconds": (("elapsed_seconds",), ("duration_seconds",), ("timing", "elapsed_seconds")),
        "token_count": (("token_count",), ("total_tokens",), ("usage", "total_tokens")),
        "conversion_quality": (("conversion_quality",), ("final_result", "conversion_quality")),
    }
    for path in aliases.get(metric_id, ()):
        value = _nested_float(record, path)
        if value is not None:
            return value
    return None


def _nested_float(record: dict, path: tuple[str, ...]) -> Optional[float]:
    current = record
    for part in path:
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return _as_float(current)


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
    score = record.get("score") if isinstance(record.get("score"), dict) else {}
    return {
        "path": record.get("_path"),
        "timestamp": record.get("_timestamp"),
        "skill": record.get("skill") or record.get("skill_name"),
        "skill_version": record.get("skill_version"),
        "case_id": record.get("case_id"),
        "eval_passed": record.get("eval_passed"),
        "score": {
            "value": score.get("value"),
            "max": score.get("max", 5),
        },
    }


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
        score = summary.get("score") or {}
        lines.append(
            "  - "
            f"{summary.get('skill', '<unknown>')} / {summary.get('case_id', '<unknown>')}: "
            f"records {summary.get('record_count', 0)}, "
            f"pass {_format_number(summary.get('eval_pass_rate'))}, "
            f"score {_format_number(score.get('avg'))}/5 {_score_bar(score.get('avg'))}"
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
        return float(value)
    except (TypeError, ValueError):
        return None


def _round(value: float) -> float:
    return round(value, 3)


def _score_bar(score: Optional[float]) -> str:
    if score is None:
        return ""
    filled = max(0, min(10, int(round((score / 5.0) * 10))))
    return "[" + "#" * filled + "-" * (10 - filled) + "]"


def _format_number(value: Any, *, default: str = "n/a") -> str:
    if value is None:
        return default
    numeric = _as_float(value)
    if numeric is None:
        return str(value)
    if numeric.is_integer():
        return str(int(numeric))
    return f"{numeric:.3g}"
