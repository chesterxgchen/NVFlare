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

"""Report filter and evaluator-backed record helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..common import write_json
from ..record_identity import record_case, record_skill


def _json_records(path: Path) -> list[dict[str, Any]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    records = value if isinstance(value, list) else [value]
    return [record for record in records if isinstance(record, dict)]


def discover_report_filter(records_path: Path) -> dict[str, str]:
    skills: list[str] = []
    cases: list[str] = []
    paths = [records_path] if records_path.is_file() else sorted(records_path.rglob("*.json"))
    for path in paths:
        for record in _json_records(path):
            skill = record_skill(record)
            case = record_case(record)
            if skill and str(skill) not in skills:
                skills.append(str(skill))
            if case and str(case) not in cases:
                cases.append(str(case))
    # The current benchmark scenarios are single-job/single-skill. If future
    # scenarios mix skills or cases in one records tree, the report layer should
    # grow an explicit multi-filter contract instead of silently relying on this
    # first identity.
    return {"skill": skills[0] if skills else "", "case": cases[0] if cases else ""}


def write_report_filter(path: Path, skill: str, case: str) -> None:
    write_json(
        path,
        {
            "requested_skill": None,
            "requested_case": None,
            "report_skill": skill or None,
            "report_case": case or None,
            "source": "harness_process_records",
        },
    )


def record_is_evaluator_backed(record: dict[str, Any]) -> bool:
    if not isinstance(record.get("eval_passed"), bool):
        return False
    sources = {
        str(record.get("agent_record_source") or ""),
        str(record.get("eval_passed_source") or ""),
    }
    evaluation = record.get("evaluation") if isinstance(record.get("evaluation"), dict) else {}
    scoring_source = str(evaluation.get("scoring_source") or "")
    return "nvflare_skill_evaluator_record" in sources or scoring_source == "nvflare agent skills evaluate"


def has_evaluator_backed_record(path: Path) -> bool:
    paths = [path] if path.is_file() else sorted(path.rglob("*.json"))
    for record_path in paths:
        if any(record_is_evaluator_backed(record) for record in _json_records(record_path)):
            return True
    return False


def write_report_status(
    path: Path,
    performance_json_status: int,
    performance_text_status: int,
    benchmark_status: int,
    skipped: bool,
    skip_reason: str,
    evaluator_backed_record: bool,
    *,
    report_runner: str | None = None,
    report_image: str | None = None,
) -> None:
    status: dict[str, Any] = {
        "skill_performance_json_exit_code": performance_json_status,
        "skill_performance_text_exit_code": performance_text_status,
        "skill_benchmark_exit_code": benchmark_status,
        "evaluator_backed_record": evaluator_backed_record,
    }
    if skipped:
        status["skipped_inside_agent_container"] = True
        status["skip_reason"] = skip_reason or None
    if report_runner:
        status["report_runner"] = report_runner
    if report_image:
        status["report_image"] = report_image
    write_json(path, status)
