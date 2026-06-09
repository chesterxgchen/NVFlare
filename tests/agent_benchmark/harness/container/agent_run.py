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

from ..agents.base import AgentLaunchContext, SkillExposureContext
from ..agents.registry import load_agent_adapter
from ..artifacts import capture_workspace_delta, write_workspace_baseline
from ..common import bool_from_text, load_json, make_tree_readable, write_json
from ..modes import mode_spec
from ..records import AgentRecordSynthesisInputs, merge_record, synthesize_agent_record, write_run_summary
from ..timing import LifecycleEpochs, finalize_timing
from .skills import apply_skill_exposure
from .skills import copy_optional_metadata_files as _copy_optional_metadata_files

DEFAULT_CONTAINER_VENV_DIR = "/workspace/venv"
RUNTIME_ARTIFACT_ROOT = Path("/tmp/nvflare")


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
    job_input_dir: Path
    result_dir: Path
    records_dir: Path
    run_root: Path
    prompt_source: Path
    progress_interval_seconds: int
    nvflare_image_kind: str
    agent: str
    agent_model: str
    agent_home: Path
    agent_model_was_explicit: bool

    @property
    def skill_run_mode(self) -> str:
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
    def prompt_file_path(self) -> Path:
        return self.result_dir / "prompt.txt"

    @property
    def progress_log_path(self) -> Path:
        return self.result_dir / "progress.jsonl"

    @classmethod
    def from_env(cls) -> "AgentRunConfig":
        env = os.environ
        mode = env.get("MODE", "with_skills")
        try:
            spec = mode_spec(mode)
        except ValueError as exc:
            raise SystemExit(str(exc).replace("Unknown mode", "Unknown MODE")) from exc
        use_preinstalled = env.get("USE_PREINSTALLED_SKILLS")
        if use_preinstalled is None:
            use_preinstalled = "true" if spec.skills_enabled else "false"
        use_preinstalled_skills = required_bool("USE_PREINSTALLED_SKILLS", use_preinstalled)
        if use_preinstalled_skills != spec.skills_enabled:
            expected = "true" if spec.skills_enabled else "false"
            raise SystemExit(
                f"USE_PREINSTALLED_SKILLS={use_preinstalled} conflicts with MODE={mode}; expected {expected}."
            )
        job_input = env.get("JOB_INPUT_DIR") or env.get("TRAINING_CODE") or "/workspace/input"
        result_dir = env.get("RESULT_DIR", "/workspace/results")
        adapter = load_agent_adapter(env.get("BENCHMARK_AGENT", "codex"))
        agent_model = adapter.model_from_env(env)
        agent_home = Path(env.get("BENCHMARK_AGENT_HOME") or env.get(adapter.agent_home_env, adapter.container_home))
        return cls(
            mode=mode,
            use_preinstalled_skills=use_preinstalled_skills,
            job_input_dir=Path(job_input),
            result_dir=Path(result_dir),
            records_dir=Path(env.get("RECORDS_DIR", str(Path(result_dir) / "records"))),
            run_root=Path(env.get("RUN_ROOT", f"/workspace/run/{mode}")),
            prompt_source=Path(env.get("PROMPT_SOURCE", "/workspace/prompts/benchmark_prompt.txt")),
            progress_interval_seconds=int(env.get("PROGRESS_INTERVAL_SECONDS", "60") or "60"),
            nvflare_image_kind=env.get("NVFLARE_IMAGE_KIND", "unknown"),
            agent=adapter.name,
            agent_model=agent_model,
            agent_home=agent_home,
            agent_model_was_explicit=adapter.model_was_explicit(env),
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
    expected_venv = os.environ.get("BENCHMARK_CONTAINER_VENV_DIR") or os.environ.get(
        "VIRTUAL_ENV", DEFAULT_CONTAINER_VENV_DIR
    )
    expected_python = str(Path(expected_venv) / "bin" / "python")
    expected_nvflare = str(Path(expected_venv) / "bin" / "nvflare")
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
    build_metadata = load_json(config.agent_home / "build_metadata.json", {}) or {}
    wheel_metadata = load_json(config.agent_home / "nvflare_wheel_metadata.json", {}) or {}
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


def setup_skill_availability(config: AgentRunConfig) -> tuple[int, int]:
    start = epoch_seconds()
    adapter = load_agent_adapter(config.agent)
    spec = adapter.skill_exposure(
        SkillExposureContext(
            result_dir=config.result_dir,
            container_home=config.agent_home,
            mode=config.mode,
            skills_enabled=config.use_preinstalled_skills,
            nvflare_image_kind=config.nvflare_image_kind,
        )
    )
    result = apply_skill_exposure(
        spec=spec,
        skills_enabled=config.use_preinstalled_skills,
        result_dir=config.result_dir,
        nvflare_image_kind=config.nvflare_image_kind,
    )
    write_json(config.result_dir / "skills_exposure_result.json", result.__dict__)
    return start, epoch_seconds()


def copy_optional_metadata_files(source_dir: Path, result_dir: Path, names: tuple[str, ...]) -> dict[str, Any]:
    return _copy_optional_metadata_files(source_dir, result_dir, names)


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
            "note": "The harness copies the mounted prompt file verbatim and does not append mode, path, or skill instructions.",
        },
    )
    return start, epoch_seconds()


def write_agent_compatibility_copies(config: AgentRunConfig) -> None:
    # Use file copies rather than symlinks because benchmark results may live on
    # Docker volume mounts where symlink behavior varies by host platform.
    adapter = load_agent_adapter(config.agent)
    suffixes = {
        "events": config.agent_events_path,
        "usage": config.agent_usage_path,
        "activity": config.agent_activity_path,
        "last_message": config.agent_last_message_path,
        "stderr": config.agent_stderr_path,
    }
    for prefix in adapter.artifact_alias_prefixes():
        for suffix, source in suffixes.items():
            target = (
                config.result_dir
                / f"{prefix}_{suffix}.{'jsonl' if suffix == 'events' else 'json' if suffix in {'usage', 'activity'} else 'txt'}"
            )
            if source.exists() and source != target:
                shutil.copy2(source, target)


AGENT_ENV_DENYLIST = {
    "MODE",
    "USE_PREINSTALLED_SKILLS",
    "NVFLARE_IMAGE_KIND",
    "RESULT_DIR",
    "RECORDS_DIR",
    "NVFLARE_AGENT_RECORD",
    "RUN_ROOT",
    "PROMPT_SOURCE",
    "JOB_INPUT_DIR",
    "TRAINING_CODE",
    "PROGRESS_INTERVAL_SECONDS",
    "BENCHMARK_AGENT",
    "BENCHMARK_AGENT_MODEL",
    "BENCHMARK_AGENT_HOME",
}


def agent_subprocess_env(launch_env: dict[str, str], adapter=None) -> dict[str, str]:
    denied = set(AGENT_ENV_DENYLIST)
    if adapter is not None:
        denied.update(str(item) for item in adapter.model_env_names())
    env = {key: value for key, value in os.environ.items() if key not in denied}
    env.update(launch_env)
    return env


def run_agent(config: AgentRunConfig, progress: ProgressWriter) -> tuple[int, int, int]:
    start = epoch_seconds()
    config.progress_log_path.write_text("", encoding="utf-8")
    progress.write("agent_exec", "start", start)
    progress.start_heartbeat("agent_exec", config.progress_interval_seconds)
    agent_exit = 127
    launch_error: OSError | None = None
    adapter = load_agent_adapter(config.agent)
    launch = adapter.launch_spec(
        AgentLaunchContext(
            workspace_dir=config.run_workspace_dir,
            prompt_file=config.prompt_file_path,
            result_dir=config.result_dir,
            events_dest=config.agent_events_path,
            stderr_dest=config.agent_stderr_path,
            final_message_dest=config.agent_last_message_path,
            model=config.agent_model,
            model_was_explicit=config.agent_model_was_explicit,
        )
    )

    try:
        try:
            with (
                launch.prompt_file.open("rb") as prompt_stdin,
                launch.stdout_events_dest.open("w", encoding="utf-8") as events_out,
                launch.stderr_dest.open("wb") as stderr,
            ):
                stdin = prompt_stdin if launch.prompt_input_mode == "stdin" else subprocess.DEVNULL
                try:
                    process = subprocess.Popen(
                        launch.argv,
                        cwd=launch.cwd,
                        stdin=stdin,
                        stdout=subprocess.PIPE,
                        stderr=stderr,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        env=agent_subprocess_env(launch.environment, adapter),
                    )
                except OSError as exc:
                    launch_error = exc
                    message = f"Failed to start agent command: {type(exc).__name__}: {exc}\n"
                    stderr.write(message.encode("utf-8", errors="replace"))
                    print(message.rstrip(), file=sys.stderr)
                else:
                    if process.stdout is None:
                        raise RuntimeError("Agent stdout pipe was not created")
                    for line in process.stdout:
                        event = adapter.normalize_event(line)
                        normalized = (
                            json.dumps(event, sort_keys=True, separators=(",", ":")) if event is not None else None
                        )
                        if normalized:
                            events_out.write(normalized + "\n")
                            events_out.flush()
                    agent_exit = process.wait()
        except OSError as exc:
            launch_error = exc
            print(f"Failed to prepare agent command streams: {type(exc).__name__}: {exc}", file=sys.stderr)
    finally:
        progress.stop_heartbeat()

    end = epoch_seconds()
    progress.write("agent_exec", "failed_to_start" if launch_error is not None else "finished", end)
    return start, end, agent_exit


def post_process(
    config: AgentRunConfig, elapsed_seconds: int, agent_exit: int, run_start_time_ns: int
) -> tuple[int, int]:
    start = epoch_seconds()
    input_delta_manifest = config.result_dir / "input_delta_manifest.json"
    capture_workspace_delta(
        config.run_input_dir,
        config.result_dir / "input_baseline_manifest.json",
        config.result_dir / "input_delta",
        input_delta_manifest,
        RUNTIME_ARTIFACT_ROOT,
        delta_scope="input_snapshot",
        include_runtime_artifacts=False,
    )
    workspace_delta_manifest = config.result_dir / "workspace_delta_manifest.json"
    capture_workspace_delta(
        config.run_workspace_dir,
        config.result_dir / "workspace_baseline_manifest.json",
        config.result_dir / "workspace_delta",
        workspace_delta_manifest,
        RUNTIME_ARTIFACT_ROOT,
        delta_scope="agent_workspace",
    )
    adapter = load_agent_adapter(config.agent)
    write_json(config.agent_usage_path, adapter.parse_usage(config.agent_events_path))
    write_json(config.agent_activity_path, adapter.parse_activity(config.agent_events_path))
    write_agent_compatibility_copies(config)
    synthesize_agent_record(
        AgentRecordSynthesisInputs(
            agent_record_path=config.agent_record_path,
            records_dir=config.records_dir,
            events_path=config.agent_events_path,
            usage_path=config.agent_usage_path,
            activity_path=config.agent_activity_path,
            last_message_path=config.agent_last_message_path,
            input_dir=config.run_input_dir,
            mode=config.mode,
            elapsed_seconds=elapsed_seconds,
            agent_exit=agent_exit,
            skills_enabled=config.use_preinstalled_skills,
            skill_run_mode=config.skill_run_mode,
            agent=config.agent,
            agent_model=config.agent_model,
            run_start_time_ns=run_start_time_ns,
            workspace_delta_manifest_path=workspace_delta_manifest,
            input_delta_manifest_path=input_delta_manifest,
            prompt_path=config.prompt_file_path,
        )
    )
    merge_record(
        config.agent_record_path,
        config.final_record_path,
        config.agent_usage_path,
        config.mode,
        elapsed_seconds,
        agent_exit,
        config.use_preinstalled_skills,
        config.skill_run_mode,
        config.agent,
        config.agent_model,
    )
    write_run_summary(config.final_record_path, config.result_dir / "run_summary.json", print_summary=False)
    return start, epoch_seconds()


def report_exit_status(command_statuses: dict[str, int]) -> int:
    return 1 if any(status != 0 for status in command_statuses.values()) else 0


def record_has_policy_failure(record: dict[str, Any]) -> bool:
    metrics = record.get("process_metrics")
    if isinstance(metrics, dict) and metrics.get("source_input_immutable_violation"):
        return True
    violation = record.get("source_input_immutable_violation")
    return isinstance(violation, dict) and violation.get("status") == "fail"


def final_container_exit_status(agent_exit: int, report_statuses: dict[str, int], *, policy_failed: bool) -> int:
    if agent_exit != 0:
        return agent_exit
    if policy_failed:
        return 1
    return report_exit_status(report_statuses)


def write_report_outcome(config: AgentRunConfig, agent_exit: int, report_statuses: dict[str, int]) -> int:
    report_exit = report_exit_status(report_statuses)
    record = load_json(config.final_record_path, {}) or {}
    if not isinstance(record, dict):
        record = {}
    policy_failed = record_has_policy_failure(record)
    final_exit = final_container_exit_status(agent_exit, report_statuses, policy_failed=policy_failed)
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


def configure_process_record_environment(config: AgentRunConfig) -> None:
    # Record paths are harness-internal. The measured agent process receives a
    # sanitized environment in run_agent() and does not inherit these values.
    return None


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
    record = {
        "schema_version": "1",
        "mode": mode,
        "run_mode": "unknown" if skills_enabled is None else "with_skill" if skills_enabled else "without_skill",
        "agent": agent,
        "source": "agent_benchmark_harness",
        "agent_process_passed": False,
        "agent_process_exit_code": exit_code,
        "agent_model": agent_model,
        "skills_enabled": skills_enabled,
        "timestamp": error["timestamp"],
        "agent_record_present": False,
        "agent_record_valid": False,
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
            "agent_exit_code": exit_code,
            "agent_process_passed": 0,
            "harness_failure": 1,
            "agent_report_exit_code": 0,
            "agent_report_failed": 0,
            "final_container_exit_code": exit_code,
            "report_inclusive_exit_code": exit_code,
        },
    }
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
    records_dir = Path(env.get("RECORDS_DIR", str(result_dir / "records")))
    agent = env.get("BENCHMARK_AGENT", "codex")
    try:
        agent_model = load_agent_adapter(agent).model_from_env(env)
    except Exception:
        agent_model = env.get("BENCHMARK_AGENT_MODEL", "unspecified_default")
    return write_failure_record(
        result_dir=result_dir,
        records_dir=records_dir,
        mode=env.get("MODE", "unknown"),
        exit_code=exit_code,
        error_type=type(exc).__name__,
        message=str(exc),
        phase=phase,
        agent=agent,
        agent_model=agent_model,
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

        phase = "agent_exec"
        progress = ProgressWriter(config.mode, script_start, config.progress_log_path)
        agent_start, agent_end, agent_exit = run_agent(config, progress)
        elapsed_seconds = agent_end - agent_start
        phase = "post_process"
        post_start, post_end = post_process(config, elapsed_seconds, agent_exit, script_start_ns)
        normal_record_written = True
        phase = "report_outcome"
        report_start = epoch_seconds()
        report_statuses: dict[str, int] = {}
        final_exit = write_report_outcome(config, agent_exit, report_statuses)
        report_end = epoch_seconds()

        script_end = epoch_seconds()
        phase = "finalize_timing"
        finalize_timing(
            config.result_dir / "run_summary.json",
            config.final_record_path,
            config.result_dir / "timing.json",
            config.agent_activity_path,
            LifecycleEpochs(
                script_start=script_start,
                skill_availability_start=skill_start,
                skill_availability_end=skill_end,
                input_copy_start=input_start,
                input_copy_end=input_end,
                prompt_prep_start=prompt_start,
                prompt_prep_end=prompt_end,
                agent_start=agent_start,
                agent_end=agent_end,
                post_process_start=post_start,
                post_process_end=post_end,
                report_outcome_start=report_start,
                report_outcome_end=report_end,
                script_end=script_end,
            ),
        )
        print(
            "Benchmark run complete: "
            f"mode={config.mode}; elapsed_seconds={script_end - script_start}; "
            f"agent_elapsed_seconds={elapsed_seconds}; final_exit={final_exit}; result_dir={config.result_dir}",
            flush=True,
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
