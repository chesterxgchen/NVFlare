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

"""Run-summary writers for benchmark wrappers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from ..common import flatten_numbers, load_json, write_json
from ..modes import PAIR_MODE_NAMES, PAIR_WITH_MODE, PAIR_WITHOUT_MODE


def coerce_status(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 1


def status_map_for_modes(modes: Sequence[str], status_by_mode: dict[str, Any]) -> dict[str, int]:
    return {mode: coerce_status(status_by_mode.get(mode, 1)) for mode in modes}


def parse_status_map_arg(modes: Sequence[str], values: list[str]) -> dict[str, int]:
    if len(values) == 1 and values[0].lstrip().startswith("{"):
        try:
            parsed = json.loads(values[0])
        except json.JSONDecodeError as exc:
            raise SystemExit(f"status map must be JSON or positional statuses: {exc}") from exc
        if not isinstance(parsed, dict):
            raise SystemExit("status map JSON must be an object keyed by mode")
        return status_map_for_modes(modes, parsed)
    if len(values) != len(modes):
        raise SystemExit(f"expected {len(modes)} statuses for modes {', '.join(modes)}; got {len(values)}")
    return status_map_for_modes(modes, dict(zip(modes, values)))


def metrics_by_name_for_runs(runs: dict[str, dict[str, Any]]) -> dict[str, dict[str, float]]:
    metrics_by_name: dict[str, dict[str, float]] = {}
    for mode, run_summary in runs.items():
        if run_summary.get("missing_summary") is True:
            continue
        metrics = run_summary.get("all_metrics")
        if not isinstance(metrics, dict):
            metrics = flatten_numbers(run_summary)
        for name, value in metrics.items():
            metrics_by_name.setdefault(name, {})[mode] = value
    return dict(sorted(metrics_by_name.items()))


def format_seconds(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "NA"
    return f"{value:.1f}s"


def pair_summary_status_line(root: Path, summary: dict[str, Any]) -> str:
    statuses = summary.get("status") if isinstance(summary.get("status"), dict) else {}
    runs = summary.get("runs") if isinstance(summary.get("runs"), dict) else {}
    mode_parts = []
    for mode in PAIR_MODE_NAMES:
        run = runs.get(mode) if isinstance(runs.get(mode), dict) else {}
        mode_parts.append(
            f"{mode}: exit={statuses.get(mode, 'NA')}, elapsed={format_seconds(run.get('elapsed_seconds'))}"
        )
    return f"Pair summary written: {root / 'pair_summary.json'}; " + "; ".join(mode_parts)


def write_pair_summary(root: Path, status_by_mode: dict[str, Any], *, print_summary: bool = True) -> dict[str, Any]:
    modes = PAIR_MODE_NAMES
    statuses = status_map_for_modes(modes, status_by_mode)
    summary: dict[str, Any] = {"result_root": str(root), "runs": {}, "status": statuses}
    for mode in modes:
        path = root / mode / "run_summary.json"
        summary["runs"][mode] = (
            load_json(path, {"missing_summary": True}) if path.exists() else {"missing_summary": True}
        )

    without = summary["runs"].get(PAIR_WITHOUT_MODE, {})
    with_skills = summary["runs"].get(PAIR_WITH_MODE, {})

    def diff(key: str) -> float | None:
        left = without.get(key)
        right = with_skills.get(key)
        if isinstance(left, (int, float)) and isinstance(right, (int, float)):
            return right - left
        return None

    metrics_by_name = metrics_by_name_for_runs(summary["runs"])

    summary["comparison"] = {
        "elapsed_seconds_with_skills_minus_without_skills": diff("elapsed_seconds"),
        "token_count_with_skills_minus_without_skills": diff("token_count"),
    }
    summary["metrics_by_name"] = metrics_by_name
    summary["metric_comparisons"] = {
        name: {
            "with_skills_minus_without_skills": values[PAIR_WITH_MODE] - values[PAIR_WITHOUT_MODE],
        }
        for name, values in sorted(metrics_by_name.items())
        if PAIR_WITH_MODE in values and PAIR_WITHOUT_MODE in values
    }
    write_json(root / "pair_summary.json", summary)
    if print_summary:
        print(pair_summary_status_line(root, summary), flush=True)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    pair = subparsers.add_parser("pair")
    pair.add_argument("root", type=Path)
    pair.add_argument("statuses", nargs="+")

    args = parser.parse_args()
    if args.command == "pair":
        write_pair_summary(args.root, parse_status_map_arg(PAIR_MODE_NAMES, args.statuses))


if __name__ == "__main__":
    main()
