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

"""Explicit BENCHMARK.md draft rendering for NVFLARE-owned agent skills."""

import os
import tempfile
from pathlib import Path
from typing import Optional

from nvflare.tool.agent.skill_performance import summarize_skill_performance

BENCHMARK_FILE_NAME = "BENCHMARK.md"
BENCHMARK_MAX_RECENT_RECORDS = 20


class SkillBenchmarkError(ValueError):
    """Benchmark rendering error surfaced as a structured CLI error."""

    def __init__(self, code: str, message: str, hint: str = "", detail: str = ""):
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint
        self.detail = detail


def render_skill_benchmark(
    *,
    skill_name: Optional[str],
    case_id: Optional[str] = None,
    records_path: Optional[Path | str] = None,
    output_path: Optional[Path | str] = None,
    dry_run: bool = False,
    source=None,
) -> dict:
    """Render a benchmark draft from runtime process-record summaries."""
    if not skill_name:
        raise SkillBenchmarkError(
            "BENCHMARK_SKILL_REQUIRED",
            "--skill is required for benchmark rendering.",
            "Pass --skill <name> so one skill's BENCHMARK.md is updated.",
        )

    from nvflare.tool.agent import skill_manager

    source = source or skill_manager.find_skill_source()
    skill = _select_skill(source.manifest.get("skills") or [], skill_name)
    performance = summarize_skill_performance(
        skill_name=skill_name,
        case_id=case_id,
        records_path=records_path,
        source=source,
    )
    output = _resolve_output_path(output_path, source, skill)
    content = _render_markdown(performance)

    written = False
    if not dry_run:
        _write_text_atomic(output, content)
        written = True

    return {
        "skill": skill_name,
        "case_id": case_id,
        "output_path": str(output),
        "dry_run": dry_run,
        "written": written,
        "content": content,
        "performance": performance,
    }


def _select_skill(skills: list[dict], skill_name: str) -> dict:
    for skill in skills:
        if skill.get("name") == skill_name:
            return skill
    raise SkillBenchmarkError(
        "AGENT_SKILL_NOT_FOUND",
        f"NVFLARE skill not found: {skill_name}",
        "Run 'nvflare agent skills list --agent codex --format json' to inspect available skills.",
    )


def _resolve_output_path(output_path: Optional[Path | str], source, skill: dict) -> Path:
    if output_path:
        return Path(output_path).expanduser()
    return source.root / skill["relative_path"] / BENCHMARK_FILE_NAME


def _render_markdown(performance: dict) -> str:
    filters = performance.get("filters") or {}
    source = performance.get("source") or {}
    lines = [
        "# Agent Skill Benchmark",
        "",
        "Generated from runtime process records. Review before treating as release evidence.",
        "",
        "## Scope",
        "",
        f"- Source: {source.get('type', 'unknown')} ({source.get('root', '')})",
        f"- Records root: {performance.get('records_root', '')} ({performance.get('records_status', 'unknown')})",
        f"- Skill filter: {filters.get('skill') or 'all'}",
        f"- Case filter: {filters.get('case_id') or 'all'}",
        "",
        "## Metric Contracts",
        "",
    ]
    _append_contracts(lines, performance.get("metric_contracts") or [])
    lines.extend(["", "## Runtime Summary", ""])
    _append_summaries(lines, performance.get("summaries") or [])
    lines.extend(["", "## Recent Records", ""])
    _append_records(lines, performance.get("records") or [])
    lines.append("")
    return "\n".join(lines)


def _append_contracts(lines: list[str], contracts: list[dict]) -> None:
    if not contracts:
        lines.append("No packaged process-metric contracts matched this scope.")
        return

    lines.append("| Skill | Case | Metrics |")
    lines.append("| --- | --- | --- |")
    for contract in contracts:
        metrics = ", ".join(metric.get("id", "") for metric in contract.get("metrics") or []) or "none"
        lines.append("| " f"{_md(contract.get('skill'))} | " f"{_md(contract.get('case_id'))} | " f"{_md(metrics)} |")


def _append_summaries(lines: list[str], summaries: list[dict]) -> None:
    if not summaries:
        lines.append("No runtime process records matched this scope.")
        return

    lines.append(
        "| Skill | Case | Mode | Source Hash | Records | Time Avg | Token Avg | Corrections Avg | Quality Avg |"
    )
    lines.append("| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |")
    for summary in summaries:
        lines.append(
            "| "
            f"{_md(summary.get('skill'))} | "
            f"{_md(summary.get('case_id'))} | "
            f"{_md(summary.get('run_mode') or '')} | "
            f"{_short_hash(summary.get('source_hash'))} | "
            f"{summary.get('record_count', 0)} | "
            f"{_metric_avg(summary, 'elapsed_seconds')} | "
            f"{_metric_avg(summary, 'token_count')} | "
            f"{_metric_avg(summary, 'user_correction_count')} | "
            f"{_metric_avg(summary, 'conversion_quality')} |"
        )


def _append_records(lines: list[str], records: list[dict]) -> None:
    if not records:
        lines.append("No individual runtime records matched this scope.")
        return

    lines.append("| Timestamp | Skill | Case | Path |")
    lines.append("| --- | --- | --- | --- |")
    for record in records[:BENCHMARK_MAX_RECENT_RECORDS]:
        lines.append(
            "| "
            f"{_md(record.get('timestamp'))} | "
            f"{_md(record.get('skill'))} | "
            f"{_md(record.get('case_id'))} | "
            f"{_md(record.get('path'))} |"
        )


def _metric_avg(summary: dict, key: str) -> str:
    metric = summary.get(key) or {}
    if not isinstance(metric, dict):
        return "n/a"
    avg = _format_number(metric.get("avg"))
    available = metric.get("available", 0)
    unavailable = metric.get("unavailable", 0)
    return f"{avg} (n={available}, missing={unavailable})"


def _short_hash(value) -> str:
    if not value:
        return ""
    text = str(value)
    return _md(text[:12])


def _format_number(value, *, default: str = "n/a") -> str:
    if value is None:
        return default
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return f"{value:.3g}"
    return str(value)


def _md(value) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ").strip()


def _write_text_atomic(path: Path, content: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as f:
            temp_path = Path(f.name)
            f.write(content)
        os.replace(temp_path, path)
    except Exception as e:
        raise SkillBenchmarkError(
            "BENCHMARK_WRITE_FAILED",
            "failed to write benchmark file",
            "Pass --output to a writable location or fix filesystem permissions.",
            detail=str(e),
        ) from e
