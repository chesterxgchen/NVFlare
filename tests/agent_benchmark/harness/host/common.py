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

"""Shared host-side Docker benchmark helpers."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from ..common import write_json

SCRIPT_DIR = Path(__file__).resolve().parents[2]
PROMPT_FILE_NAME = "benchmark_prompt.txt"
OUTPUT_LOCK = threading.Lock()


def timestamp_slug() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def expand_home_path(value: str) -> str:
    if value == "~":
        return str(Path.home())
    if value.startswith("~/"):
        return str(Path.home() / value[2:])
    return value


def absolute_path(value: str) -> Path:
    expanded = Path(expand_home_path(value))
    return expanded if expanded.is_absolute() else Path.cwd() / expanded


def env_bool(name: str, default: str) -> bool:
    value = os.environ.get(name, default)
    if value not in {"true", "false"}:
        raise SystemExit(f"{name} must be true or false; got {value}")
    return value == "true"


def default_results_root() -> Path:
    return Path(
        os.environ.get(
            "AGENT_BENCHMARK_RESULTS_ROOT",
            os.environ.get("CODEX_DOCKER_RESULTS_ROOT", str(SCRIPT_DIR / "results")),
        )
    )


def print_usage(command: str) -> None:
    usage = {
        "run-one": "Run one agent benchmark case against an arbitrary job folder.",
        "pair": "Run paired skills/no-skills benchmark cases against a job folder.",
        "process-eval": "Run the three-mode skill-eval ablation against a job folder.",
        "interactive": "Start an interactive benchmark container with a job folder mounted.",
    }.get(command, "Run an agent benchmark command against a job folder.")
    print(
        f"Usage: {Path(sys.argv[0]).name} [--training-code PATH] [PATH]\n\n"
        f"{usage}\n\n"
        "Arguments:\n"
        "  PATH                    Job folder. Equivalent to --training-code.\n\n"
        "Options:\n"
        "  --training-code PATH    Job folder to mount into the benchmark container.\n"
        "  -h, --help              Show this help."
    )


def parse_job_input(argv: list[str], command: str) -> Path:
    job_input = os.environ.get("JOB_INPUT_DIR") or os.environ.get("TRAINING_CODE") or ""
    set_by_arg = False
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == "--training-code":
            if index + 1 >= len(argv):
                raise SystemExit("--training-code requires a path")
            if set_by_arg:
                raise SystemExit("Expected only one job folder")
            job_input = argv[index + 1]
            set_by_arg = True
            index += 2
        elif arg.startswith("--training-code="):
            if set_by_arg:
                raise SystemExit("Expected only one job folder")
            job_input = arg.split("=", 1)[1]
            set_by_arg = True
            index += 1
        elif arg in {"-h", "--help"}:
            print_usage(command)
            raise SystemExit(0)
        elif arg == "--":
            rest = argv[index + 1 :]
            if len(rest) > 1:
                raise SystemExit("Expected at most one job folder after --")
            if rest:
                if set_by_arg:
                    raise SystemExit("Expected only one job folder")
                job_input = rest[0]
            break
        elif arg.startswith("-"):
            print_usage(command)
            raise SystemExit(f"Unknown option: {arg}")
        else:
            if set_by_arg:
                raise SystemExit("Expected only one job folder")
            job_input = arg
            set_by_arg = True
            index += 1

    if not job_input:
        print_usage(command)
        raise SystemExit("Job input folder is required. Pass PATH or --training-code PATH.")
    path = absolute_path(job_input)
    if not path.is_dir():
        raise SystemExit(f"Job input must be an existing folder: {path}")
    return path


def ensure_prompt_dir() -> tuple[Path, Path]:
    prompt_dir = absolute_path(os.environ.get("PROMPT_DIR", str(SCRIPT_DIR / "prompts")))
    prompt_path = prompt_dir / PROMPT_FILE_NAME
    if not prompt_dir.is_dir():
        raise SystemExit(f"Prompt directory does not exist: {prompt_dir}")
    if not prompt_path.is_file():
        raise SystemExit(f"Prompt file does not exist: {prompt_path}")
    return prompt_dir, prompt_path


def emit(message: str = "", *, logs: Iterable[Path] = (), prefix: str | None = None, stderr: bool = False) -> None:
    line = f"[{prefix}] {message}" if prefix else message
    stream = sys.stderr if stderr else sys.stdout
    with OUTPUT_LOCK:
        print(line, file=stream, flush=True)
        for log in logs:
            log.parent.mkdir(parents=True, exist_ok=True)
            with log.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")


def stream_command(
    command: list[str], *, logs: Iterable[Path] = (), prefix: str | None = None, env: dict[str, str] | None = None
) -> int:
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
    except OSError as exc:
        program = command[0] if command else "<empty command>"
        emit(f"Failed to start command {program}: {type(exc).__name__}: {exc}", logs=logs, prefix=prefix, stderr=True)
        return 127
    if process.stdout is None:
        raise RuntimeError("subprocess stdout pipe was not created")
    for line in process.stdout:
        emit(line.rstrip("\n"), logs=logs, prefix=prefix)
    return process.wait()


def command_stdout_to_file(
    command: list[str],
    output_path: Path,
    *,
    logs: Iterable[Path] = (),
    prefix: str | None = None,
) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output_path.open("w", encoding="utf-8", errors="replace") as stdout:
            process = subprocess.Popen(
                command,
                stdout=stdout,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if process.stderr is None:
                raise RuntimeError("subprocess stderr pipe was not created")
            for line in process.stderr:
                emit(line.rstrip("\n"), logs=logs, prefix=prefix, stderr=True)
            return process.wait()
    except OSError as exc:
        program = command[0] if command else "<empty command>"
        emit(f"Failed to start command {program}: {type(exc).__name__}: {exc}", logs=logs, prefix=prefix, stderr=True)
        return 127


def add_openai_passthrough_env(args: list[str]) -> None:
    if os.environ.get("OPENAI_API_KEY"):
        args.extend(["-e", "OPENAI_API_KEY"])
    if os.environ.get("BENCHMARK_AGENT"):
        args.extend(["-e", f"BENCHMARK_AGENT={os.environ['BENCHMARK_AGENT']}"])
    if os.environ.get("CODEX_MODEL"):
        args.extend(["-e", f"CODEX_MODEL={os.environ['CODEX_MODEL']}"])


def docker_env(name: str, value: str | int | bool | None = None) -> list[str]:
    if value is None:
        return ["-e", name]
    if isinstance(value, bool):
        rendered = "true" if value else "false"
    else:
        rendered = str(value)
    return ["-e", f"{name}={rendered}"]


def add_codex_auth_mounts(
    args: list[str],
    *,
    host_codex_home: Path,
    container_codex_home: str,
    logs: Iterable[Path] = (),
    prefix: str | None = None,
) -> None:
    auth = host_codex_home / "auth.json"
    codex_config = host_codex_home / "config.toml"
    if auth.is_file():
        args.extend(["-v", f"{auth}:{container_codex_home}/auth.json:ro"])
        emit(f"Mounting Codex auth: {auth} -> {container_codex_home}/auth.json", logs=logs, prefix=prefix)
    else:
        emit(f"Codex auth not mounted; missing {auth}", logs=logs, prefix=prefix, stderr=True)
    if codex_config.is_file():
        args.extend(["-v", f"{codex_config}:{container_codex_home}/config.toml:ro"])
        emit(f"Mounting Codex config: {codex_config} -> {container_codex_home}/config.toml", logs=logs, prefix=prefix)
    else:
        emit(f"Codex config not mounted; missing {codex_config}", logs=logs, prefix=prefix, stderr=True)


@dataclass(frozen=True)
class ImageConfig:
    image_name: str
    baseline_image_name: str
    report_image_name: str

    @classmethod
    def from_env(cls) -> "ImageConfig":
        agent = os.environ.get("BENCHMARK_AGENT", "codex")
        image = os.environ.get("IMAGE_NAME", f"nvflare-agent-benchmark:{agent}-skills")
        return cls(
            image_name=image,
            baseline_image_name=os.environ.get("BASELINE_IMAGE_NAME", f"nvflare-agent-benchmark:{agent}-baseline"),
            report_image_name=os.environ.get("REPORT_IMAGE_NAME", image),
        )


@dataclass(frozen=True)
class CaseConfig:
    mode: str
    use_preinstalled_skills: bool
    process_eval: bool
    nvflare_skill_eval: str
    job_input_dir: Path
    result_dir: Path
    prompt_dir: Path
    prompt_path: Path
    images: ImageConfig
    progress_interval_seconds: str
    host_codex_home: Path
    mount_host_codex_auth: bool

    @property
    def run_image(self) -> str:
        return self.images.image_name if self.use_preinstalled_skills else self.images.baseline_image_name

    @property
    def nvflare_image_kind(self) -> str:
        return (
            "local_wheel_with_preinstalled_skills"
            if self.use_preinstalled_skills
            else "local_wheel_without_packaged_skills"
        )


def case_config(
    *,
    mode: str,
    use_preinstalled_skills: bool,
    process_eval: bool,
    nvflare_skill_eval: str,
    job_input_dir: Path,
    result_dir: Path,
    images: ImageConfig,
) -> CaseConfig:
    prompt_dir, prompt_path = ensure_prompt_dir()
    return CaseConfig(
        mode=mode,
        use_preinstalled_skills=use_preinstalled_skills,
        process_eval=process_eval,
        nvflare_skill_eval=nvflare_skill_eval,
        job_input_dir=job_input_dir,
        result_dir=result_dir,
        prompt_dir=prompt_dir,
        prompt_path=prompt_path,
        images=images,
        progress_interval_seconds=os.environ.get("PROGRESS_INTERVAL_SECONDS", "60"),
        host_codex_home=absolute_path(os.environ.get("HOST_CODEX_HOME", str(Path.home() / ".codex"))),
        mount_host_codex_auth=env_bool("MOUNT_HOST_CODEX_AUTH", "true"),
    )


def docker_args_for_case(config: CaseConfig, logs: Iterable[Path] = (), prefix: str | None = None) -> list[str]:
    args = [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{config.job_input_dir}:/workspace/input:ro",
        "-v",
        f"{config.result_dir}:/workspace/results",
        "-v",
        f"{config.prompt_dir}:/workspace/prompts:ro",
        *docker_env("CODEX_HOME", "/workspace/.codex"),
        *docker_env("JOB_INPUT_DIR", "/workspace/input"),
        *docker_env("TRAINING_CODE", "/workspace/input"),
        *docker_env("MODE", config.mode),
        *docker_env("USE_PREINSTALLED_SKILLS", config.use_preinstalled_skills),
        *docker_env("PROCESS_EVAL", config.process_eval),
        *docker_env("NVFLARE_SKILL_EVAL", config.nvflare_skill_eval),
        *docker_env("NVFLARE_IMAGE_KIND", config.nvflare_image_kind),
        *docker_env("PROGRESS_INTERVAL_SECONDS", config.progress_interval_seconds),
        *docker_env("RESULT_DIR", "/workspace/results"),
        *docker_env("RECORDS_DIR", "/workspace/results/process_eval_runs"),
        *docker_env("PROCESS_EVAL_RECORDS", "/workspace/results/process_eval_runs"),
        *docker_env("NVFLARE_AGENT_RECORD", f"/workspace/results/process_eval_runs/{config.mode}_agent_record.json"),
        *docker_env("NVFLARE_PROCESS_EVAL_MODE", config.mode),
        *docker_env("NVFLARE_SKILL_EVAL_RECORDS", "/workspace/results/process_eval_runs"),
    ]
    add_openai_passthrough_env(args)
    if config.mount_host_codex_auth:
        add_codex_auth_mounts(
            args,
            host_codex_home=config.host_codex_home,
            container_codex_home="/workspace/.codex",
            logs=logs,
            prefix=prefix,
        )
    args.extend([config.run_image, "/workspace/venv/bin/python", "-m", "harness.container.agent_run"])
    return args


def write_runtime_image(config: CaseConfig) -> None:
    config.result_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        config.result_dir / "runtime_image.json",
        {
            "mode": config.mode,
            "use_preinstalled_skills": config.use_preinstalled_skills,
            "process_eval": config.process_eval,
            "nvflare_skill_eval": config.nvflare_skill_eval,
            "nvflare_skill_eval_state": "on" if config.nvflare_skill_eval == "on" else "off",
            "agent": os.environ.get("BENCHMARK_AGENT", "codex"),
            "agent_model": os.environ.get("CODEX_MODEL", "unspecified_default"),
            "runtime_image": config.run_image,
            "report_image": config.images.report_image_name,
            "nvflare_image_kind": config.nvflare_image_kind,
            "container_python": "/workspace/venv/bin/python",
            "container_virtual_env": "/workspace/venv",
        },
    )
