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

"""In-container agent benchmark lifecycle runner."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..agents.base import normalize_agent_event
from ..artifacts import capture_workspace_delta, write_workspace_baseline
from ..common import bool_from_text, load_json, make_tree_readable, write_json
from ..events import parse_usage_and_activity
from ..records import merge_record, synthesize_agent_record, write_run_summary
from ..reports.reporting import (
    discover_report_filter,
    has_evaluator_backed_record,
    write_report_filter,
    write_report_status,
)
from ..timing import finalize_timing


def epoch_seconds() -> int:
    return int(time.time())


def epoch_nanoseconds() -> int:
    return time.time_ns()


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def required_bool(name: str, value: str) -> bool:
    if value not in {"true", "false"}:
        raise SystemExit(f"{name} must be true or false; got {value}")
    return bool_from_text(value)


@dataclass(frozen=True)
class AgentRunConfig:
    mode: str
    use_preinstalled_skills: bool
    process_eval: bool
    job_input_dir: Path
    result_dir: Path
    records_dir: Path
    run_root: Path
    prompt_source: Path
    nvflare_skill_eval: str
    progress_interval_seconds: int
    nvflare_image_kind: str
    agent: str
    agent_model: str
    codex_home: Path

    @property
    def eval_run_mode(self) -> str:
        return "with_skill" if self.use_preinstalled_skills else "without_skill"

    @property
    def run_input_dir(self) -> Path:
        return self.run_root / "input"

    @property
    def run_workspace_dir(self) -> Path:
        return self.run_root / "workspace"

    @property
    def agent_record_path(self) -> Path:
        return self.records_dir / f"{self.mode}_agent_record.json"

    @property
    def final_record_path(self) -> Path:
        return self.records_dir / f"{self.mode}_record.json"

    @property
    def agent_events_path(self) -> Path:
        return self.result_dir / "agent_events.jsonl"

    @property
    def agent_usage_path(self) -> Path:
        return self.result_dir / "agent_usage.json"

    @property
    def agent_activity_path(self) -> Path:
        return self.result_dir / "agent_activity.json"

    @property
    def agent_last_message_path(self) -> Path:
        return self.result_dir / "agent_last_message.txt"

    @property
    def agent_stderr_path(self) -> Path:
        return self.result_dir / "agent_stderr.txt"

    @property
    def codex_events_path(self) -> Path:
        return self.result_dir / "codex_events.jsonl"

    @property
    def codex_last_message_path(self) -> Path:
        return self.result_dir / "codex_last_message.txt"

    @property
    def codex_usage_path(self) -> Path:
        return self.result_dir / "codex_usage.json"

    @property
    def codex_activity_path(self) -> Path:
        return self.result_dir / "codex_activity.json"

    @property
    def codex_stderr_path(self) -> Path:
        return self.result_dir / "codex_stderr.txt"

    @property
    def prompt_file_path(self) -> Path:
        return self.result_dir / "prompt.txt"

    @property
    def progress_log_path(self) -> Path:
        return self.result_dir / "progress.jsonl"

    @classmethod
    def from_env(cls) -> "AgentRunConfig":
        env = os.environ
        mode = env.get("MODE", "with_skills_eval_off")
        use_preinstalled = env.get("USE_PREINSTALLED_SKILLS")
        if use_preinstalled is None:
            use_preinstalled = "false" if mode.startswith("without_skills") else "true"
        default_process_eval = "true" if mode.endswith("_eval_on") else "false"
        default_skill_eval = "on" if mode.endswith("_eval_on") else ""
        job_input = env.get("JOB_INPUT_DIR") or env.get("TRAINING_CODE") or "/workspace/input"
        result_dir = env.get("RESULT_DIR", "/workspace/results")
        return cls(
            mode=mode,
            use_preinstalled_skills=required_bool("USE_PREINSTALLED_SKILLS", use_preinstalled),
            process_eval=required_bool("PROCESS_EVAL", env.get("PROCESS_EVAL", default_process_eval)),
            job_input_dir=Path(job_input),
            result_dir=Path(result_dir),
            records_dir=Path(env.get("RECORDS_DIR", str(Path(result_dir) / "process_eval_runs"))),
            run_root=Path(env.get("RUN_ROOT", f"/workspace/run/{mode}")),
            prompt_source=Path(env.get("PROMPT_SOURCE", "/workspace/prompts/benchmark_prompt.txt")),
            nvflare_skill_eval=env.get("NVFLARE_SKILL_EVAL", default_skill_eval),
            progress_interval_seconds=int(env.get("PROGRESS_INTERVAL_SECONDS", "60") or "60"),
            nvflare_image_kind=env.get("NVFLARE_IMAGE_KIND", "unknown"),
            agent=env.get("BENCHMARK_AGENT", "codex"),
            agent_model=env.get("CODEX_MODEL", "unspecified_default"),
            codex_home=Path(env.get("CODEX_HOME", "/workspace/.codex")),
        )


class ProgressWriter:
    def __init__(self, mode: str, script_start_epoch: int, progress_log: Path):
        self.mode = mode
        self.script_start_epoch = script_start_epoch
        self.progress_log = progress_log
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def write(self, phase: str, status: str, epoch: int | None = None) -> None:
        epoch = epoch_seconds() if epoch is None else epoch
        elapsed = epoch - self.script_start_epoch
        timestamp = utc_timestamp()
        print(
            f"[{timestamp}] benchmark progress: mode={self.mode} phase={phase} "
            f"status={status} elapsed_seconds={elapsed}",
            file=sys.stderr,
            flush=True,
        )
        with self.progress_log.open("a", encoding="utf-8") as stream:
            stream.write(
                json.dumps(
                    {
                        "timestamp": timestamp,
                        "mode": self.mode,
                        "phase": phase,
                        "status": status,
                        "elapsed_seconds": elapsed,
                    },
                    separators=(",", ":"),
                )
                + "\n"
            )

    def start_heartbeat(self, phase: str, interval_seconds: int) -> None:
        if interval_seconds <= 0:
            return

        def loop() -> None:
            while not self._stop.wait(interval_seconds):
                self.write(phase, "running")

        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()

    def stop_heartbeat(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None


def discover_bundled_skills_root() -> str | None:
    try:
        from nvflare.tool.agent import skill_manager

        source = skill_manager.find_skill_source()
        root = getattr(source, "root", None)
        return str(root) if root else None
    except Exception:
        return None


def write_skipped_skill_reports(result_dir: Path, reason: str) -> None:
    payload = {"status": "skipped", "reason": reason}
    write_json(result_dir / "skill_benchmark.json", payload)
    write_json(result_dir / "skill_performance.json", payload)
    (result_dir / "skill_performance.txt").write_text(f"skipped: {reason}\n", encoding="utf-8")


def command_output(command: list[str]) -> str | None:
    try:
        return subprocess.check_output(command, text=True, stderr=subprocess.STDOUT).strip()
    except Exception:
        return None


def login_shell_runtime_probe() -> dict[str, Any]:
    script = "\n".join(
        [
            "printf 'PATH=%s\\n' \"$PATH\"",
            "printf 'python=%s\\n' \"$(command -v python)\"",
            "printf 'nvflare=%s\\n' \"$(command -v nvflare)\"",
            "nvflare --version | sed 's/^/nvflare_version=/'",
            'python -c \'import nvflare; print("nvflare_import_version=" + getattr(nvflare, "__version__", "unknown"))\'',
        ]
    )
    command = ["/bin/bash", "-lc", script]
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        return {
            "command": command,
            "exit_code": 127,
            "output": f"{type(exc).__name__}: {exc}",
            "ok": False,
            "reason": "failed_to_start_login_shell_probe",
        }

    values: dict[str, str] = {}
    for line in result.stdout.splitlines():
        key, sep, value = line.partition("=")
        if sep:
            values[key] = value
    expected_python = "/workspace/venv/bin/python"
    expected_nvflare = "/workspace/venv/bin/nvflare"
    ok = (
        result.returncode == 0 and values.get("python") == expected_python and values.get("nvflare") == expected_nvflare
    )
    reason = "ok"
    if result.returncode != 0:
        reason = f"probe_exit_code_{result.returncode}"
    elif values.get("python") != expected_python:
        reason = f"python_resolved_to_{values.get('python') or 'missing'}"
    elif values.get("nvflare") != expected_nvflare:
        reason = f"nvflare_resolved_to_{values.get('nvflare') or 'missing'}"
    return {
        "command": command,
        "exit_code": result.returncode,
        "output": result.stdout,
        "path": values.get("PATH"),
        "python": values.get("python"),
        "nvflare": values.get("nvflare"),
        "nvflare_version": values.get("nvflare_version"),
        "nvflare_import_version": values.get("nvflare_import_version"),
        "expected_python": expected_python,
        "expected_nvflare": expected_nvflare,
        "ok": ok,
        "reason": reason,
    }


def persist_container_runtime_metadata(config: AgentRunConfig) -> None:
    build_metadata = load_json(config.codex_home / "build_metadata.json", {}) or {}
    wheel_metadata = load_json(config.codex_home / "nvflare_wheel_metadata.json", {}) or {}
    if build_metadata:
        write_json(config.result_dir / "image_build_metadata.json", build_metadata)
    if wheel_metadata:
        write_json(config.result_dir / "nvflare_wheel_metadata.json", wheel_metadata)

    runtime_path = config.result_dir / "runtime_image.json"
    runtime_metadata = load_json(runtime_path, {}) or {}
    probe = login_shell_runtime_probe()
    runtime_metadata.update(
        {
            "container_python_executable": sys.executable,
            "container_python_version": sys.version.split()[0],
            "container_virtual_env": os.environ.get("VIRTUAL_ENV"),
            "container_path_prefix": os.environ.get("PATH", "").split(":")[:3],
            "container_pip_version": command_output([sys.executable, "-m", "pip", "--version"]),
            "container_uv_version": command_output(["uv", "--version"]),
            "login_shell_runtime_probe": probe,
            "image_build_metadata": build_metadata,
            "nvflare_wheel_metadata": wheel_metadata,
        }
    )
    write_json(runtime_path, runtime_metadata)
    if not probe.get("ok"):
        raise RuntimeError(f"Login-shell runtime probe failed: {probe.get('reason')}")


def remove_skill_report_artifacts(result_dir: Path) -> None:
    for name in (
        "skill_report_filter.json",
        "skill_benchmark.json",
        "skill_benchmark.md",
        "skill_performance.json",
        "skill_performance.txt",
        "skill_report_status.json",
        "agent_report_exit_codes.json",
    ):
        (result_dir / name).unlink(missing_ok=True)


def disable_skills(skills_root: Path) -> dict[str, Any]:
    skills_root.mkdir(parents=True, exist_ok=True)
    for child in list(skills_root.iterdir()):
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink(missing_ok=True)

    bundled_root = discover_bundled_skills_root()
    removed = False
    if bundled_root:
        path = Path(bundled_root)
        if path.is_dir():
            shutil.rmtree(path)
            removed = True
    return {
        "codex_home_skills_removed": True,
        "packaged_skill_source_removed_during_agent": removed,
        "packaged_skill_source_path": bundled_root,
    }


def setup_skill_availability(config: AgentRunConfig) -> tuple[int, int]:
    start = epoch_seconds()
    skills_root = config.codex_home / "skills"
    if config.use_preinstalled_skills:
        if not skills_root.is_dir() or not any(path.is_dir() for path in skills_root.iterdir()):
            write_json(
                config.result_dir / "skills_state.json",
                {"status": "error", "reason": "preinstalled Codex skills are missing from CODEX_HOME"},
            )
            raise SystemExit(2)
        write_json(
            config.result_dir / "skills_state.json",
            {
                "status": "enabled",
                "source": config.nvflare_image_kind,
                "skills_enabled": True,
            },
        )
        shutil.copy2(
            config.codex_home / "nvflare_skills_build_install.json", config.result_dir / "skills_build_install.json"
        )
        shutil.copy2(config.codex_home / "nvflare_skills_list.json", config.result_dir / "skills_list.json")
    else:
        disabled = disable_skills(skills_root)
        write_json(
            config.result_dir / "skills_state.json",
            {
                "status": "disabled",
                "source": config.nvflare_image_kind,
                "skills_enabled": False,
                "image_kind": config.nvflare_image_kind,
                "reason": "baseline image installs a local no-skills NVFLARE wheel and does not preinstall Codex skills",
                **disabled,
                "reporting_note": "Wrapper-side reports run from the skills image so benchmark contracts are available outside the measured agent container.",
            },
        )
        write_json(
            config.result_dir / "skills_list.json",
            {"status": "skipped", "installed": [], "reason": "skills intentionally removed for baseline run"},
        )
    return start, epoch_seconds()


def prepare_input_workspace(config: AgentRunConfig) -> tuple[int, int]:
    start = epoch_seconds()
    config.run_root.mkdir(parents=True, exist_ok=True)
    for name in ("input", "generated", "job_config", "workspace"):
        shutil.rmtree(config.run_root / name, ignore_errors=True)
    shutil.copytree(config.job_input_dir, config.run_input_dir, symlinks=True)
    shutil.copytree(config.run_input_dir, config.run_workspace_dir, symlinks=True)
    for name in ("generated", "job_config"):
        (config.run_root / name).mkdir(parents=True, exist_ok=True)
    return start, epoch_seconds()


def prepare_prompt(config: AgentRunConfig) -> tuple[int, int]:
    start = epoch_seconds()
    shutil.copy2(config.prompt_source, config.prompt_file_path)
    template_bytes = config.prompt_source.read_bytes()
    prompt_bytes = config.prompt_file_path.read_bytes()
    write_json(
        config.result_dir / "prompt_metadata.json",
        {
            "template_path": str(config.prompt_source),
            "prompt_path": str(config.prompt_file_path),
            "template_sha256": hashlib.sha256(template_bytes).hexdigest(),
            "prompt_sha256": hashlib.sha256(prompt_bytes).hexdigest(),
            "template_bytes": len(template_bytes),
            "prompt_bytes": len(prompt_bytes),
            "verbatim_copy": template_bytes == prompt_bytes,
            "harness_prompt_injection": False,
            "note": "The harness copies the mounted prompt file verbatim and does not append mode, path, skill, or evaluator instructions.",
        },
    )
    return start, epoch_seconds()


def write_agent_compatibility_aliases(config: AgentRunConfig) -> None:
    aliases = (
        (config.agent_events_path, config.codex_events_path),
        (config.agent_usage_path, config.codex_usage_path),
        (config.agent_activity_path, config.codex_activity_path),
        (config.agent_last_message_path, config.codex_last_message_path),
        (config.agent_stderr_path, config.codex_stderr_path),
    )
    for source, target in aliases:
        if source.exists() and source != target:
            shutil.copy2(source, target)


def run_codex(config: AgentRunConfig, progress: ProgressWriter) -> tuple[int, int, int]:
    start = epoch_seconds()
    config.progress_log_path.write_text("", encoding="utf-8")
    progress.write("codex_exec", "start", start)
    progress.start_heartbeat("codex_exec", config.progress_interval_seconds)
    codex_exit = 127
    launch_error: OSError | None = None

    command = [
        "codex",
        "exec",
        "--json",
        "--skip-git-repo-check",
        "--dangerously-bypass-approvals-and-sandbox",
        "-C",
        str(config.run_workspace_dir),
        "-o",
        str(config.agent_last_message_path),
    ]
    if os.environ.get("CODEX_MODEL"):
        command.extend(["-m", os.environ["CODEX_MODEL"]])
    command.append("-")

    try:
        try:
            with (
                config.prompt_file_path.open("rb") as stdin,
                config.agent_events_path.open("w", encoding="utf-8") as events_out,
                config.agent_stderr_path.open("wb") as stderr,
            ):
                try:
                    process = subprocess.Popen(
                        command,
                        cwd=config.run_workspace_dir,
                        stdin=stdin,
                        stdout=subprocess.PIPE,
                        stderr=stderr,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                    )
                except OSError as exc:
                    launch_error = exc
                    message = f"Failed to start Codex command: {type(exc).__name__}: {exc}\n"
                    stderr.write(message.encode("utf-8", errors="replace"))
                    print(message.rstrip(), file=sys.stderr)
                else:
                    if process.stdout is None:
                        raise RuntimeError("Codex stdout pipe was not created")
                    for line in process.stdout:
                        event = normalize_agent_event(config.agent, line)
                        normalized = (
                            json.dumps(event, sort_keys=True, separators=(",", ":")) if event is not None else None
                        )
                        if normalized:
                            events_out.write(normalized + "\n")
                            events_out.flush()
                    codex_exit = process.wait()
        except OSError as exc:
            launch_error = exc
            print(f"Failed to prepare Codex command streams: {type(exc).__name__}: {exc}", file=sys.stderr)
    finally:
        progress.stop_heartbeat()

    end = epoch_seconds()
    progress.write("codex_exec", "failed_to_start" if launch_error is not None else "finished", end)
    return start, end, codex_exit


def post_process(
    config: AgentRunConfig, elapsed_seconds: int, codex_exit: int, run_start_time_ns: int
) -> tuple[int, int]:
    start = epoch_seconds()
    input_delta_manifest = config.result_dir / "input_delta_manifest.json"
    capture_workspace_delta(
        config.run_input_dir,
        config.result_dir / "input_baseline_manifest.json",
        config.result_dir / "input_delta",
        input_delta_manifest,
        Path("/tmp/nvflare"),
        delta_scope="input_snapshot",
        include_runtime_artifacts=False,
    )
    workspace_delta_manifest = config.result_dir / "workspace_delta_manifest.json"
    capture_workspace_delta(
        config.run_workspace_dir,
        config.result_dir / "workspace_baseline_manifest.json",
        config.result_dir / "workspace_delta",
        workspace_delta_manifest,
        Path("/tmp/nvflare"),
        delta_scope="agent_workspace",
    )
    parse_usage_and_activity(
        config.agent_events_path,
        config.agent_usage_path,
        config.agent_activity_path,
    )
    write_agent_compatibility_aliases(config)
    synthesize_agent_record(
        config.agent_record_path,
        config.records_dir,
        config.agent_events_path,
        config.agent_usage_path,
        config.agent_activity_path,
        config.agent_last_message_path,
        config.run_input_dir,
        config.mode,
        elapsed_seconds,
        codex_exit,
        config.use_preinstalled_skills,
        config.process_eval,
        config.eval_run_mode,
        config.nvflare_skill_eval,
        config.agent,
        config.agent_model,
        run_start_time_ns,
        workspace_delta_manifest,
        input_delta_manifest,
    )
    merge_record(
        config.agent_record_path,
        config.final_record_path,
        config.agent_usage_path,
        config.mode,
        elapsed_seconds,
        codex_exit,
        config.use_preinstalled_skills,
        config.process_eval,
        config.eval_run_mode,
        config.nvflare_skill_eval,
        config.agent,
        config.agent_model,
    )
    write_run_summary(config.final_record_path, config.result_dir / "run_summary.json")
    return start, epoch_seconds()


def run_command_to_file(command: list[str], output_path: Path) -> int:
    try:
        with output_path.open("wb") as stdout:
            return subprocess.run(command, stdout=stdout).returncode
    except OSError as exc:
        program = command[0] if command else "<empty command>"
        print(f"Failed to start or capture command {program}: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 127


def report_exit_status(command_statuses: dict[str, int]) -> int:
    return 1 if any(status != 0 for status in command_statuses.values()) else 0


def record_has_policy_failure(record: dict[str, Any]) -> bool:
    metrics = record.get("process_metrics")
    if isinstance(metrics, dict) and metrics.get("source_input_immutable_violation"):
        return True
    violation = record.get("source_input_immutable_violation")
    return isinstance(violation, dict) and violation.get("status") == "fail"


def final_container_exit_status(codex_exit: int, report_statuses: dict[str, int], *, policy_failed: bool) -> int:
    if codex_exit != 0:
        return codex_exit
    if policy_failed:
        return 1
    return report_exit_status(report_statuses)


def write_report_outcome(config: AgentRunConfig, codex_exit: int, report_statuses: dict[str, int]) -> int:
    report_exit = report_exit_status(report_statuses)
    record = load_json(config.final_record_path, {}) or {}
    if not isinstance(record, dict):
        record = {}
    policy_failed = record_has_policy_failure(record)
    final_exit = final_container_exit_status(codex_exit, report_statuses, policy_failed=policy_failed)
    record["agent_report_exit_codes"] = report_statuses
    record["agent_report_exit_code"] = report_exit
    record["agent_report_failed"] = report_exit != 0
    record["harness_policy_failed"] = policy_failed
    record["final_container_exit_code"] = final_exit
    record["report_inclusive_exit_code"] = final_exit
    metrics = record.setdefault("process_metrics", {})
    if isinstance(metrics, dict):
        metrics["agent_report_exit_code"] = report_exit
        metrics["agent_report_failed"] = 1 if report_exit else 0
        metrics["harness_policy_failed"] = 1 if policy_failed else 0
        metrics["final_container_exit_code"] = final_exit
        metrics["report_inclusive_exit_code"] = final_exit
    write_json(config.final_record_path, record)
    write_run_summary(config.final_record_path, config.result_dir / "run_summary.json", print_summary=False)
    return final_exit


def write_skill_reports(config: AgentRunConfig) -> tuple[int, int, dict[str, int]]:
    start = epoch_seconds()
    remove_skill_report_artifacts(config.result_dir)
    report_filter = discover_report_filter(config.records_dir)
    write_report_filter(config.result_dir / "skill_report_filter.json", report_filter["skill"], report_filter["case"])

    report_args: list[str] = []
    if report_filter["skill"]:
        report_args.extend(["--skill", report_filter["skill"]])
    if report_filter["case"]:
        report_args.extend(["--case", report_filter["case"]])

    evaluator_backed = config.final_record_path.is_file() and has_evaluator_backed_record(config.final_record_path)
    skipped = False
    skip_reason = ""
    if config.use_preinstalled_skills and evaluator_backed:
        benchmark_status = run_command_to_file(
            [
                "nvflare",
                "--format",
                "json",
                "agent",
                "skills",
                "benchmark",
                *report_args,
                "--records",
                str(config.final_record_path),
                "--output",
                str(config.result_dir / "skill_benchmark.md"),
            ],
            config.result_dir / "skill_benchmark.json",
        )
        performance_json_status = run_command_to_file(
            [
                "nvflare",
                "--format",
                "json",
                "agent",
                "skills",
                "performance",
                *report_args,
                "--records",
                str(config.final_record_path),
            ],
            config.result_dir / "skill_performance.json",
        )
        performance_text_status = run_command_to_file(
            [
                "nvflare",
                "agent",
                "skills",
                "performance",
                *report_args,
                "--records",
                str(config.final_record_path),
            ],
            config.result_dir / "skill_performance.txt",
        )
    else:
        benchmark_status = 0
        performance_json_status = 0
        performance_text_status = 0
        skipped = True
        if config.use_preinstalled_skills:
            skip_reason = "no evaluator-backed eval_passed record is available; skipping NVFLARE skill quality reports"
        else:
            skip_reason = "baseline runtime image does not contain skill benchmark contracts; host wrapper reports from the skills image"
        write_skipped_skill_reports(config.result_dir, skip_reason)

    write_report_status(
        config.result_dir / "skill_report_status.json",
        performance_json_status,
        performance_text_status,
        benchmark_status,
        skipped,
        skip_reason,
        evaluator_backed,
    )
    command_statuses = {
        "skill_benchmark": benchmark_status,
        "skill_performance_json": performance_json_status,
        "skill_performance_text": performance_text_status,
    }
    write_json(config.result_dir / "agent_report_exit_codes.json", command_statuses)
    return start, epoch_seconds(), command_statuses


def configure_process_record_environment(config: AgentRunConfig) -> None:
    # This runs inside the benchmark container; mutating os.environ is intentional
    # so Codex and evaluator subprocesses inherit the process-record locations.
    os.environ["JOB_INPUT_DIR"] = str(config.job_input_dir)
    os.environ["TRAINING_CODE"] = str(config.job_input_dir)
    os.environ["PROCESS_EVAL_RECORDS"] = str(config.records_dir)
    os.environ["NVFLARE_AGENT_RECORD"] = str(config.agent_record_path)
    os.environ["NVFLARE_PROCESS_EVAL_MODE"] = config.mode
    os.environ["NVFLARE_SKILL_EVAL_RECORDS"] = str(config.records_dir)


def exit_code_from_exception(exc: BaseException, default: int = 1) -> int:
    if isinstance(exc, SystemExit) and isinstance(exc.code, int):
        return exc.code
    return default


def harness_error_payload(exc: BaseException, exit_code: int, phase: str) -> dict[str, Any]:
    return {
        "timestamp": utc_timestamp(),
        "phase": phase,
        "exit_code": exit_code,
        "error_type": type(exc).__name__,
        "message": str(exc),
    }


def write_failure_record(
    *,
    result_dir: Path,
    records_dir: Path,
    mode: str,
    exit_code: int,
    error_type: str,
    message: str,
    phase: str,
    agent: str = "codex",
    agent_model: str = "unspecified_default",
    skills_enabled: bool | None = None,
    process_eval: bool | None = None,
    nvflare_skill_eval: str = "",
) -> int:
    result_dir.mkdir(parents=True, exist_ok=True)
    records_dir.mkdir(parents=True, exist_ok=True)
    error = {
        "timestamp": utc_timestamp(),
        "phase": phase,
        "exit_code": exit_code,
        "error_type": error_type,
        "message": message,
    }
    process_eval_state = "unknown" if process_eval is None else "on" if process_eval else "off"
    nvflare_skill_eval_state = "on" if nvflare_skill_eval == "on" else "off"
    record = {
        "schema_version": "1",
        "mode": mode,
        "run_mode": "unknown" if skills_enabled is None else "with_skill" if skills_enabled else "without_skill",
        "agent": agent,
        "source": "docker_codex_benchmark",
        "agent_model": agent_model,
        "skills_enabled": skills_enabled,
        "process_eval_enabled": process_eval,
        "process_evaluator_state": process_eval_state,
        "process_eval_semantics": "harness metadata flag; NVFLARE_SKILL_EVAL is the runtime switch that enables NVFLARE skill evaluation",
        "nvflare_skill_eval": nvflare_skill_eval,
        "nvflare_skill_eval_state": nvflare_skill_eval_state,
        "timestamp": error["timestamp"],
        "codex_process_passed": False,
        "codex_process_exit_code": exit_code,
        "agent_record_present": False,
        "agent_record_valid": False,
        "eval_passed": None,
        "eval_passed_source": "unavailable",
        "score": {
            "value": None,
            "max": 5,
            "rationale": "Harness failure occurred before a normal run record could be produced.",
        },
        "harness_failure": True,
        "harness_error": error,
        "harness_errors": [error],
        "agent_report_exit_codes": {},
        "agent_report_exit_code": 0,
        "agent_report_failed": False,
        "final_container_exit_code": exit_code,
        "report_inclusive_exit_code": exit_code,
        "process_metrics": {
            "elapsed_seconds": 0,
            "token_count": None,
            "codex_exit_code": exit_code,
            "codex_process_passed": 0,
            "harness_failure": 1,
            "agent_report_exit_code": 0,
            "agent_report_failed": 0,
            "final_container_exit_code": exit_code,
            "report_inclusive_exit_code": exit_code,
        },
    }
    if process_eval is not None:
        record["process_metrics"]["process_eval_enabled"] = 1 if process_eval else 0
    record["process_metrics"]["nvflare_skill_eval_enabled"] = 1 if nvflare_skill_eval == "on" else 0
    final_record_path = records_dir / f"{mode}_record.json"
    write_json(final_record_path, record)
    write_json(
        result_dir / "early_failure.json",
        {
            **error,
            "record_path": str(final_record_path),
        },
    )
    write_run_summary(final_record_path, result_dir / "run_summary.json", print_summary=False)
    make_tree_readable(result_dir)
    return exit_code


def merge_harness_failure(config: AgentRunConfig, exc: BaseException, exit_code: int, phase: str) -> int | None:
    record = load_json(config.final_record_path, {}) or {}
    if not isinstance(record, dict) or not record:
        return None
    error = harness_error_payload(exc, exit_code, phase)
    record["harness_failure"] = True
    record["agent"] = record.get("agent") or config.agent
    record["agent_model"] = record.get("agent_model") or config.agent_model
    record["harness_error"] = error
    errors = record.get("harness_errors")
    if not isinstance(errors, list):
        errors = []
    errors.append(error)
    record["harness_errors"] = errors
    record["final_container_exit_code"] = exit_code
    record["harness_failure_exit_code"] = exit_code
    metrics = record.setdefault("process_metrics", {})
    if isinstance(metrics, dict):
        metrics["harness_failure"] = 1
        metrics["harness_failure_exit_code"] = exit_code
        metrics["final_container_exit_code"] = exit_code
    write_json(config.final_record_path, record)
    write_json(
        config.result_dir / "late_harness_failure.json",
        {
            **error,
            "record_path": str(config.final_record_path),
            "preserved_existing_record": True,
        },
    )
    write_run_summary(config.final_record_path, config.result_dir / "run_summary.json", print_summary=False)
    make_tree_readable(config.result_dir)
    return exit_code


def write_failure_record_from_env(exc: BaseException, exit_code: int, phase: str) -> int:
    env = os.environ
    result_dir = Path(env.get("RESULT_DIR", "/workspace/results"))
    records_dir = Path(env.get("RECORDS_DIR", str(result_dir / "process_eval_runs")))
    return write_failure_record(
        result_dir=result_dir,
        records_dir=records_dir,
        mode=env.get("MODE", "unknown"),
        exit_code=exit_code,
        error_type=type(exc).__name__,
        message=str(exc),
        phase=phase,
        agent=env.get("BENCHMARK_AGENT", "codex"),
        agent_model=env.get("CODEX_MODEL", "unspecified_default"),
        nvflare_skill_eval=env.get("NVFLARE_SKILL_EVAL", ""),
    )


def write_configured_failure(
    config: AgentRunConfig,
    exc: BaseException,
    exit_code: int,
    phase: str,
    *,
    preserve_existing_record: bool = False,
) -> int:
    if preserve_existing_record:
        merged_exit = merge_harness_failure(config, exc, exit_code, phase)
        if merged_exit is not None:
            return merged_exit
    return write_failure_record(
        result_dir=config.result_dir,
        records_dir=config.records_dir,
        mode=config.mode,
        exit_code=exit_code,
        error_type=type(exc).__name__,
        message=str(exc),
        phase=phase,
        agent=config.agent,
        agent_model=config.agent_model,
        skills_enabled=config.use_preinstalled_skills,
        process_eval=config.process_eval,
        nvflare_skill_eval=config.nvflare_skill_eval,
    )


def run_agent_benchmark() -> int:
    try:
        config = AgentRunConfig.from_env()
    except BaseException as exc:
        if isinstance(exc, KeyboardInterrupt):
            raise
        return write_failure_record_from_env(exc, exit_code_from_exception(exc, 2), "config")

    phase = "input_validation"
    normal_record_written = False
    try:
        if not config.prompt_source.is_file():
            message = (
                f"Prompt file is not mounted or does not exist: {config.prompt_source}. "
                "Mount a prompt file to /workspace/prompts/benchmark_prompt.txt or pass --prompt through the host wrapper scripts."
            )
            print(message, file=sys.stderr)
            return write_configured_failure(config, RuntimeError(message), 2, phase)
        if not config.job_input_dir.is_dir():
            message = f"Job input folder does not exist: {config.job_input_dir}"
            print(message, file=sys.stderr)
            return write_configured_failure(config, RuntimeError(message), 2, phase)

        config.result_dir.mkdir(parents=True, exist_ok=True)
        config.records_dir.mkdir(parents=True, exist_ok=True)
        config.run_root.mkdir(parents=True, exist_ok=True)
        phase = "runtime_metadata_probe"
        persist_container_runtime_metadata(config)
        configure_process_record_environment(config)

        script_start = epoch_seconds()
        script_start_ns = epoch_nanoseconds()
        phase = "skill_availability_setup"
        skill_start, skill_end = setup_skill_availability(config)
        phase = "input_copy"
        input_start, input_end = prepare_input_workspace(config)
        write_workspace_baseline(config.run_input_dir, config.result_dir / "input_baseline_manifest.json")
        write_workspace_baseline(config.run_workspace_dir, config.result_dir / "workspace_baseline_manifest.json")
        phase = "prompt_prepare"
        prompt_start, prompt_end = prepare_prompt(config)

        phase = "codex_exec"
        progress = ProgressWriter(config.mode, script_start, config.progress_log_path)
        codex_start, codex_end, codex_exit = run_codex(config, progress)
        elapsed_seconds = codex_end - codex_start
        phase = "post_process"
        post_start, post_end = post_process(config, elapsed_seconds, codex_exit, script_start_ns)
        normal_record_written = True
        phase = "skill_reports"
        report_start, report_end, report_statuses = write_skill_reports(config)
        final_exit = write_report_outcome(config, codex_exit, report_statuses)

        script_end = epoch_seconds()
        phase = "finalize_timing"
        finalize_timing(
            config.result_dir / "run_summary.json",
            config.final_record_path,
            config.result_dir / "timing.json",
            config.agent_activity_path,
            [
                script_start,
                skill_start,
                skill_end,
                input_start,
                input_end,
                prompt_start,
                prompt_end,
                codex_start,
                codex_end,
                post_start,
                post_end,
                report_start,
                report_end,
                script_end,
            ],
        )
        return final_exit
    except BaseException as exc:
        if isinstance(exc, KeyboardInterrupt):
            raise
        return write_configured_failure(
            config,
            exc,
            exit_code_from_exception(exc),
            phase,
            preserve_existing_record=normal_record_written,
        )
    finally:
        make_tree_readable(config.result_dir)


def main() -> None:
    raise SystemExit(run_agent_benchmark())


if __name__ == "__main__":
    main()
