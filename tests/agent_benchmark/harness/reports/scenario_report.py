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

"""Scenario-level benchmark report rendering."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from ..common import write_json


def write_scenario_report(result_root: Path, summary: Mapping[str, Any]) -> None:
    reports_dir = result_root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    write_json(reports_dir / "scenario_report.json", dict(summary))
    lines = [
        f"# Scenario Report: {summary.get('scenario_name')}",
        "",
        f"Result root: `{result_root}`",
        f"Status: `{summary.get('status')}`",
        f"Runs: {summary.get('completed_run_count')}/{summary.get('expanded_case_count')} completed",
        "",
        "## Aggregate Results",
        "",
        "| Label | Runs | Quality pass | Median agent seconds | Median tokens |",
        "|---|---:|---:|---:|---:|",
    ]
    aggregates = (summary.get("aggregate_results") or {}).get("by_label") or {}
    for label, data in sorted(aggregates.items()):
        elapsed = data.get("agent_elapsed_seconds", {}).get("median")
        tokens = data.get("token_count", {}).get("median")
        lines.append(
            f"| {label} | {data.get('run_count')} | {data.get('quality_pass_count')} | "
            f"{elapsed if elapsed is not None else 'NA'} | {tokens if tokens is not None else 'NA'} |"
        )
    winner = (summary.get("aggregate_results") or {}).get("winner")
    lines.extend(["", "## Winner Policy", "", f"`{summary.get('winner_policy')}`"])
    if winner:
        lines.append(f"\nSelected winner: `{winner.get('label')}`.")
    else:
        lines.append("\nNo winner selected because no compared label passed the quality gate with timing data.")
    (reports_dir / "scenario_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
