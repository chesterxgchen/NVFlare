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

"""Host-side benchmark orchestration CLI."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Iterable

from ..common import write_json
from ..modes import PAIR_RUNS, ModeSpec, mode_spec
from ..reports.summaries import write_pair_summary
from .common import (
    CONTAINER_PROMPT_PATH,
    CaseConfig,
    ImageConfig,
    absolute_path,
    add_agent_auth_mounts,
    add_agent_passthrough_env,
    benchmark_agent_adapter_from_env,
    case_config,
    default_results_root,
    docker_args_for_case,
    docker_env,
    emit,
    parse_host_cli_options,
    stream_command,
    timestamp_slug,
    write_runtime_image,
)

STALE_RESULT_FILES = (
    "comprehensive_report.json",
    "comprehensive_report.md",
    "metrics_plots.png",
    "metrics_plots.svg",
    "metrics_summary.json",
    "process_eval_ablation_summary.json",
    "skill_benchmark.json",
    "skill_benchmark.md",
    "skill_performance.json",
    "skill_performance.txt",
    "skill_report_status.json",
)
STALE_RESULT_DIRS = (
    "process_eval_runs",
    "with_skills_eval_off",
    "with_skills_eval_on",
)


@dataclass(frozen=True)
class InteractiveRuntimeConfig:
    agent: str
    agent_model: str
    model_was_explicit: bool


def run_one_case(config: CaseConfig, *, logs: Iterable[Path] = (), prefix: str | None = None) -> int:
    config.result_dir.mkdir(parents=True, exist_ok=True)
    emit(f"Running mode={config.mode} with runtime image: {config.run_image}", logs=logs, prefix=prefix)
    emit(f"Report image: {config.images.report_image_name}", logs=logs, prefix=prefix)
    emit(f"Job folder: {config.job_input_dir} -> /workspace/input", logs=logs, prefix=prefix)
    emit(f"Prompt file: {config.prompt_path} -> {CONTAINER_PROMPT_PATH}", logs=logs, prefix=prefix)
    write_runtime_image(config)
    status = stream_command(docker_args_for_case(config, logs=logs, prefix=prefix), logs=logs, prefix=prefix)
    write_json(config.result_dir / "container_exit_code.json", {"exit_code": status})
    return combined_exit_status({config.mode: status})


def write_host_error(path: Path, exc: BaseException) -> None:
    write_json(
        path,
        {
            "error_type": type(exc).__name__,
            "message": str(exc),
            "traceback": "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
        },
    )


def run_case_safely(config: CaseConfig, *, logs: Iterable[Path] = (), prefix: str | None = None) -> int:
    try:
        return run_one_case(config, logs=logs, prefix=prefix)
    except Exception as exc:
        config.result_dir.mkdir(parents=True, exist_ok=True)
        write_host_error(config.result_dir / "host_case_error.json", exc)
        emit(
            f"Case failed before completion: {type(exc).__name__}: {exc}",
            logs=logs,
            prefix=prefix,
            stderr=True,
        )
        return 1


def run_one(argv: list[str]) -> int:
    options = parse_host_cli_options(argv, "run-one")
    images = ImageConfig.from_env()
    mode = os.environ.get("MODE", "with_skills")
    try:
        spec = mode_spec(mode)
    except ValueError as exc:
        raise SystemExit(str(exc).replace("Unknown mode", "Unknown MODE")) from exc

    use_preinstalled_skills = checked_bool_override(
        "USE_PREINSTALLED_SKILLS",
        spec.skills_enabled,
        mode,
    )
    config = case_config(
        mode=mode,
        use_preinstalled_skills=use_preinstalled_skills,
        job_input_dir=options.job_input,
        result_dir=single_result_dir(options, mode),
        prompt_path=options.prompt_path,
        images=images,
    )
    return run_case_safely(config)


def single_result_dir(options, mode: str) -> Path:
    if options.result_dir is not None:
        return options.result_dir
    if options.results_root is not None:
        return options.results_root / "single" / f"{timestamp_slug()}_{mode}"
    return absolute_path(
        os.environ.get("RESULT_DIR", str(default_results_root() / "single" / f"{timestamp_slug()}_{mode}"))
    )


def comparison_result_root(options, *, default_prefix: str | None = None) -> Path:
    if options.result_root is not None:
        return options.result_root
    timestamp = timestamp_slug()
    default_name = f"{default_prefix}_{timestamp}" if default_prefix else timestamp
    if options.results_root is not None:
        return options.results_root / default_name
    return absolute_path(os.environ.get("RESULT_ROOT", str(default_results_root() / default_name)))


def checked_bool_override(name: str, expected: bool, mode: str) -> bool:
    value = os.environ.get(name)
    if value is None:
        return expected
    if value not in {"true", "false"}:
        raise SystemExit(f"{name} must be true or false; got {value}")
    actual = value == "true"
    if actual != expected:
        expected_text = "true" if expected else "false"
        raise SystemExit(f"{name}={value} conflicts with MODE={mode}; expected {expected_text}.")
    return actual


def reject_parallel_comparison_runs(command: str) -> None:
    parallel = os.environ.get("PARALLEL_CASES", "false").strip().lower()
    if parallel not in {"", "0", "false", "no", "off"}:
        raise SystemExit(
            f"PARALLEL_CASES is no longer supported for benchmark comparisons; {command} runs sequentially."
        )


def run_case_spec(
    spec: ModeSpec,
    *,
    job_input: Path,
    prompt_path: Path,
    result_root: Path,
    images: ImageConfig,
    logs: Iterable[Path] = (),
    write_status_file: bool = False,
    use_case_log: bool = False,
) -> tuple[str, int]:
    case_log = result_root / f"{spec.mode}.console.log"
    case_logs = logs
    if use_case_log:
        case_log.write_text("", encoding="utf-8")
        case_logs = (*logs, case_log)
    emit(
        "Starting case={} use_preinstalled_skills={}{}".format(
            spec.mode,
            str(spec.skills_enabled).lower(),
            f" log={case_log}" if use_case_log else "",
        ),
        logs=case_logs,
        prefix=spec.mode,
    )
    config = case_config(
        mode=spec.mode,
        use_preinstalled_skills=spec.skills_enabled,
        job_input_dir=job_input,
        result_dir=result_root / spec.mode,
        prompt_path=prompt_path,
        images=images,
    )
    status = run_case_safely(config, logs=case_logs, prefix=spec.mode)
    if write_status_file:
        (result_root / f"{spec.mode}.status").write_text(f"{status}\n", encoding="utf-8")
    emit(
        f"Finished case={spec.mode} status={status}" + (f" log={case_log}" if use_case_log else ""),
        logs=case_logs,
        prefix=spec.mode,
    )
    return spec.mode, status


def copy_combined_records(result_root: Path, case_modes: Iterable[str]) -> Path:
    combined = result_root / "records"
    combined.mkdir(parents=True, exist_ok=True)
    for mode in case_modes:
        record = result_root / mode / "records" / f"{mode}_record.json"
        if record.is_file():
            shutil.copy2(record, combined / f"{mode}_record.json")
    return combined


def clean_pair_result_root(result_root: Path) -> None:
    """Remove generated artifacts from older harness layouts before a fresh pair run."""

    for spec in PAIR_RUNS:
        path = result_root / spec.mode
        if path.exists():
            shutil.rmtree(path)
    for name in STALE_RESULT_DIRS:
        path = result_root / name
        if path.exists():
            shutil.rmtree(path)
    for name in STALE_RESULT_FILES:
        path = result_root / name
        if path.exists() and path.is_file():
            path.unlink()


def run_report_generator(module: str, args: list[str], *, logs: Iterable[Path] = ()) -> int:
    status = stream_command([sys.executable, "-m", f"harness.reports.{module}", *args], logs=logs)
    if status != 0:
        emit(f"Report generator failed: {module} exit_code={status}", logs=logs, stderr=True)
    return status


def write_report_generator_status(result_root: Path, statuses: dict[str, int]) -> None:
    write_json(
        result_root / "report_generator_status.json",
        {
            "status": "ok" if all(status == 0 for status in statuses.values()) else "failed",
            "exit_codes": statuses,
        },
    )


def write_host_report_status(
    result_root: Path,
    *,
    report_generator_statuses: dict[str, int] | None = None,
) -> None:
    report_generator_statuses = report_generator_statuses or {}
    payload = {
        "status": "ok" if all(status == 0 for status in report_generator_statuses.values()) else "failed",
        "report_generators": report_generator_statuses,
    }
    write_json(
        result_root / "host_report_status.json",
        payload,
    )
    write_report_generator_status(result_root, report_generator_statuses)


def combined_exit_status(case_statuses: dict[str, int], report_statuses: dict[str, int] | None = None) -> int:
    report_statuses = report_statuses or {}
    return 1 if any(status != 0 for status in [*case_statuses.values(), *report_statuses.values()]) else 0


def run_pair(argv: list[str]) -> int:
    reject_parallel_comparison_runs("pair")
    options = parse_host_cli_options(argv, "pair")
    images = ImageConfig.from_env()
    result_root = comparison_result_root(options)
    result_root.mkdir(parents=True, exist_ok=True)
    clean_pair_result_root(result_root)
    console_log = result_root / "console_output.log"
    console_log.write_text("", encoding="utf-8")
    logs = (console_log,)

    emit(f"Result root: {result_root}", logs=logs)
    emit(f"Console log: {console_log}", logs=logs)
    emit(f"Skills image: {images.image_name}", logs=logs)
    emit(f"Baseline image: {images.baseline_image_name}", logs=logs)
    emit(f"Report image: {images.report_image_name}", logs=logs)
    emit(f"Job folder: {options.job_input}", logs=logs)
    emit(f"Prompt file: {options.prompt_path} -> {CONTAINER_PROMPT_PATH}", logs=logs)

    statuses: dict[str, int] = {}
    for spec in PAIR_RUNS:
        mode, status = run_case_spec(
            spec,
            job_input=options.job_input,
            prompt_path=options.prompt_path,
            result_root=result_root,
            images=images,
            logs=logs,
        )
        statuses[mode] = status

    write_pair_summary(result_root, statuses)
    combined = copy_combined_records(result_root, [spec.mode for spec in PAIR_RUNS])
    emit(f"Pair summary: {result_root / 'pair_summary.json'}", logs=logs)
    emit(f"Combined records: {combined}", logs=logs)
    report_generator_statuses = {
        "metrics_report": run_report_generator(
            "metrics_report",
            [str(result_root), "--title", "NVFLARE Agent Skills Benchmark Metrics"],
            logs=logs,
        ),
        "benchmark_insights": run_report_generator("benchmark_insights", [str(result_root)], logs=logs),
    }
    write_host_report_status(
        result_root,
        report_generator_statuses=report_generator_statuses,
    )
    return combined_exit_status(statuses, report_generator_statuses)


def run_interactive(argv: list[str]) -> int:
    options = parse_host_cli_options(argv, "interactive")
    images = ImageConfig.from_env()
    adapter = benchmark_agent_adapter_from_env()
    host_agent_home = absolute_path(str(adapter.host_home_from_env(os.environ)))
    container_records = os.environ.get("CONTAINER_RECORDS", "/tmp/nvflare/records")
    args = [
        "docker",
        "run",
        "--rm",
        "-it",
        "-v",
        f"{options.job_input}:/workspace/input",
        "-v",
        f"{options.prompt_path}:{CONTAINER_PROMPT_PATH}:ro",
        *docker_env("JOB_INPUT_DIR", "/workspace/input"),
        *docker_env("TRAINING_CODE", "/workspace/input"),
        *docker_env("PROMPT_SOURCE", CONTAINER_PROMPT_PATH),
        *docker_env("RECORDS_DIR", container_records),
    ]
    for name, value in sorted(
        adapter.runtime_env(
            InteractiveRuntimeConfig(
                agent=adapter.name,
                agent_model=agent_model_from_env(adapter),
                model_was_explicit=adapter.model_was_explicit(os.environ),
            )
        ).items()
    ):
        args.extend(docker_env(name, value))
    add_agent_passthrough_env(args, adapter)
    if adapter.mount_auth_from_env(os.environ):
        interactive_config = SimpleNamespace(host_agent_home=host_agent_home)
        add_agent_auth_mounts(args, mounts=adapter.auth_mounts(interactive_config))
    emit(f"Mounting job folder: {options.job_input} -> /workspace/input")
    emit(f"Using prompt file: {options.prompt_path} -> {CONTAINER_PROMPT_PATH}")
    try:
        return subprocess.call([*args, images.image_name, "bash"])
    except OSError as exc:
        emit(f"Failed to start interactive container: {type(exc).__name__}: {exc}", stderr=True)
        return 127


def agent_model_from_env(adapter) -> str:
    try:
        return adapter.model_from_env(os.environ)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] in {"-h", "--help"}:
        print(
            "Usage: python -m harness.host.runner {run-one,pair,interactive} "
            "--prompt PATH [--training-code PATH] [--results-root PATH] [PATH]"
        )
        raise SystemExit(0 if len(sys.argv) >= 2 else 2)
    command, argv = sys.argv[1], sys.argv[2:]
    if command == "run-one":
        status = run_one(argv)
    elif command == "pair":
        status = run_pair(argv)
    elif command == "interactive":
        status = run_interactive(argv)
    else:
        raise SystemExit(f"Unknown command: {command}")
    raise SystemExit(status)


if __name__ == "__main__":
    main()
