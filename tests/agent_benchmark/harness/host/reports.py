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

"""Host-side NVFLARE skill report helpers."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Iterable

from ..common import make_tree_readable, write_json
from ..reports.reporting import (
    discover_report_filter,
    has_evaluator_backed_record,
    write_report_filter,
    write_report_status,
)
from .common import CaseConfig, command_stdout_to_file, emit

SKIPPED_REPORT_STATUSES = {
    "skill_benchmark": 0,
    "skill_performance_json": 0,
    "skill_performance_text": 0,
}


def remove_report_placeholders(result_dir: Path) -> None:
    for name in (
        "skill_report_filter.json",
        "skill_benchmark.json",
        "skill_benchmark.md",
        "skill_performance.json",
        "skill_performance.txt",
        "skill_report_status.json",
    ):
        (result_dir / name).unlink(missing_ok=True)


def write_skipped_reports(
    result_dir: Path,
    reason: str,
    *,
    report_runner: str | None = None,
    evaluator_backed: bool | None = None,
) -> None:
    payload: dict[str, Any] = {"status": "skipped", "reason": reason}
    write_json(result_dir / "skill_benchmark.json", payload)
    write_json(result_dir / "skill_performance.json", payload)
    (result_dir / "skill_performance.txt").write_text(f"skipped: {reason}\n", encoding="utf-8")
    status: dict[str, Any] = {"status": "skipped", "reason": reason}
    if report_runner:
        status["report_runner"] = report_runner
    if evaluator_backed is not None:
        status["evaluator_backed_record"] = evaluator_backed
    write_json(result_dir / "skill_report_status.json", status)


def docker_make_results_readable(result_dir: Path, report_image: str) -> None:
    try:
        subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{result_dir}:/workspace/results",
                report_image,
                "chmod",
                "-R",
                "u+rw,go+rX",
                "/workspace/results",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except OSError:
        pass


def prepare_result_dir_for_host_writes(result_dir: Path, report_image: str) -> None:
    result_dir.mkdir(parents=True, exist_ok=True)
    docker_make_results_readable(result_dir, report_image)
    make_tree_readable(result_dir)


def run_docker_skill_reports(
    *,
    records_host_path: Path,
    records_mount_arg: str,
    records_mount: list[str],
    result_dir: Path,
    report_image: str,
    logs: Iterable[Path] = (),
    prefix: str | None = None,
    report_runner: str | None = None,
    skip_reason: str = "no evaluator-backed eval_passed records are available; skipping NVFLARE skill quality reports",
) -> dict[str, int]:
    prepare_result_dir_for_host_writes(result_dir, report_image)
    remove_report_placeholders(result_dir)
    if not records_host_path.exists():
        write_skipped_reports(result_dir, "process_eval_runs directory is missing", report_runner=report_runner)
        prepare_result_dir_for_host_writes(result_dir, report_image)
        return dict(SKIPPED_REPORT_STATUSES)

    evaluator_backed = has_evaluator_backed_record(records_host_path)
    if not evaluator_backed:
        write_skipped_reports(result_dir, skip_reason, report_runner=report_runner, evaluator_backed=False)
        prepare_result_dir_for_host_writes(result_dir, report_image)
        return dict(SKIPPED_REPORT_STATUSES)

    report_filter = discover_report_filter(records_host_path)
    write_report_filter(result_dir / "skill_report_filter.json", report_filter["skill"], report_filter["case"])
    filter_args: list[str] = []
    if report_filter["skill"]:
        filter_args.extend(["--skill", report_filter["skill"]])
    if report_filter["case"]:
        filter_args.extend(["--case", report_filter["case"]])

    common = ["docker", "run", "--rm", *records_mount, "-v", f"{result_dir}:/workspace/results", report_image]
    benchmark_status = command_stdout_to_file(
        [
            *common,
            "nvflare",
            "--format",
            "json",
            "agent",
            "skills",
            "benchmark",
            *filter_args,
            "--records",
            records_mount_arg,
            "--output",
            "/workspace/results/skill_benchmark.md",
        ],
        result_dir / "skill_benchmark.json",
        logs=logs,
        prefix=prefix,
    )
    performance_json_status = command_stdout_to_file(
        [
            *common,
            "nvflare",
            "--format",
            "json",
            "agent",
            "skills",
            "performance",
            *filter_args,
            "--records",
            records_mount_arg,
        ],
        result_dir / "skill_performance.json",
        logs=logs,
        prefix=prefix,
    )
    performance_text_status = command_stdout_to_file(
        [
            *common,
            "nvflare",
            "agent",
            "skills",
            "performance",
            *filter_args,
            "--records",
            records_mount_arg,
        ],
        result_dir / "skill_performance.txt",
        logs=logs,
        prefix=prefix,
    )
    prepare_result_dir_for_host_writes(result_dir, report_image)
    write_report_status(
        result_dir / "skill_report_status.json",
        performance_json_status,
        performance_text_status,
        benchmark_status,
        False,
        "",
        evaluator_backed,
        report_runner=report_runner,
        report_image=report_image,
    )
    return {
        "skill_benchmark": benchmark_status,
        "skill_performance_json": performance_json_status,
        "skill_performance_text": performance_text_status,
    }


def run_host_skill_reports(
    config: CaseConfig, *, logs: Iterable[Path] = (), prefix: str | None = None
) -> dict[str, int]:
    records_dir = config.result_dir / "process_eval_runs"
    final_record = records_dir / f"{config.mode}_record.json"
    if final_record.is_file():
        # Mount a single synthesized mode record when available. The NVFLARE
        # report CLI accepts either a JSON record file or a directory of records;
        # keep the mount path and --records argument coupled in this branch.
        return run_docker_skill_reports(
            records_host_path=final_record,
            records_mount_arg="/workspace/process_record.json",
            records_mount=["-v", f"{final_record}:/workspace/process_record.json:ro"],
            result_dir=config.result_dir,
            report_image=config.images.report_image_name,
            logs=logs,
            prefix=prefix,
            report_runner="host_wrapper",
            skip_reason="no evaluator-backed eval_passed record is available; skipping NVFLARE skill quality reports",
        )
    # Fallback for early failures where only the records directory may exist.
    return run_docker_skill_reports(
        records_host_path=records_dir,
        records_mount_arg="/workspace/process_eval_runs",
        records_mount=["-v", f"{records_dir}:/workspace/process_eval_runs:ro"],
        result_dir=config.result_dir,
        report_image=config.images.report_image_name,
        logs=logs,
        prefix=prefix,
        report_runner="host_wrapper",
        skip_reason="no evaluator-backed eval_passed record is available; skipping NVFLARE skill quality reports",
    )


def print_performance_table(path: Path, *, logs: Iterable[Path] = ()) -> None:
    if not path.exists():
        return
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return
    data = report.get("data") if report.get("status") == "ok" else report
    summaries = data.get("summaries") if isinstance(data, dict) else None
    if not summaries:
        return

    def avg(summary: dict[str, Any], key: str) -> str:
        value = summary.get(key)
        if isinstance(value, dict):
            value = value.get("avg")
        return "n/a" if value is None else str(value)

    emit("", logs=logs)
    emit("NVFLARE performance by run mode:", logs=logs)
    emit("run_mode\trecords\tpass_rate\tscore_avg\telapsed_avg\ttoken_avg\tquality_avg", logs=logs)
    for summary in sorted(summaries, key=lambda item: str(item.get("run_mode") or "")):
        emit(
            "\t".join(
                [
                    str(summary.get("run_mode") or "unknown"),
                    str(summary.get("record_count", 0)),
                    str(summary.get("eval_pass_rate", "n/a")),
                    avg(summary, "score"),
                    avg(summary, "elapsed_seconds"),
                    avg(summary, "token_count"),
                    avg(summary, "conversion_quality"),
                ]
            ),
            logs=logs,
        )
