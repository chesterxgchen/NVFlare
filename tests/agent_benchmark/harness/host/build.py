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

"""Host-side Docker image build orchestration."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .common import SCRIPT_DIR, benchmark_agent_adapter_from_env, emit

FLARE_TEST_DIR = SCRIPT_DIR.parent
DEFAULT_UV_IMAGE = "ghcr.io/astral-sh/uv:0.11.19"
DEFAULT_NODE_IMAGE = "node:22.16.0-bookworm-slim"


def env_flag(name: str, default: str) -> bool:
    value = os.environ.get(name, default)
    if value not in {"true", "false"}:
        raise SystemExit(f"{name} must be true or false; got {value}")
    return value == "true"


def canonical_dir(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_dir():
        raise SystemExit(f"Directory does not exist: {value}")
    return path.resolve()


def is_nvflare_repo(path: Path) -> bool:
    return (path / "pyproject.toml").is_file() and (path / "nvflare").is_dir()


def assert_nvflare_repo_not_in_harness_source(path: Path) -> None:
    try:
        path.relative_to(SCRIPT_DIR)
    except ValueError:
        return
    raise SystemExit(
        "NVFLARE_REPO must not be inside tests/agent_benchmark. "
        "Only built wheel artifacts are staged into the Docker build context."
    )


def resolve_nvflare_repo() -> Path:
    explicit = os.environ.get("NVFLARE_REPO")
    candidates = [
        FLARE_TEST_DIR.parent / "NVFlare",
        SCRIPT_DIR.parents[1],
        SCRIPT_DIR.parent.parent / "NVFlare",
        Path.home() / "projects" / "NVFlare",
        Path.home() / "NVFlare",
    ]
    if explicit:
        repo = canonical_dir(explicit)
        if not is_nvflare_repo(repo):
            raise SystemExit(f"NVFLARE_REPO does not look like an NVFlare checkout: {repo}")
        assert_nvflare_repo_not_in_harness_source(repo)
        return repo

    for candidate in candidates:
        if candidate.is_dir():
            repo = candidate.resolve()
            if is_nvflare_repo(repo):
                assert_nvflare_repo_not_in_harness_source(repo)
                return repo

    raise SystemExit("Could not find an NVFlare checkout. Set NVFLARE_REPO=/path/to/NVFlare.")


def latest_nvflare_wheel(variant: str, search_dir: Path) -> Path | None:
    wheels = [*search_dir.glob("nvflare-*.whl"), *search_dir.glob("nvflare_nightly-*.whl")]
    matches: list[Path] = []
    for wheel in wheels:
        has_no_skills = "no_skills" in wheel.name
        if variant == "skills" and not has_no_skills:
            matches.append(wheel)
        elif variant == "no_skills" and has_no_skills:
            matches.append(wheel)
        elif variant not in {"skills", "no_skills"}:
            raise SystemExit(f"Unknown wheel variant: {variant}")
    if not matches:
        return None
    return max(matches, key=lambda item: item.stat().st_mtime)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_commit(repo: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    commit = result.stdout.strip()
    return commit or None


def stage_existing_wheel(repo: Path, variant: str, label: str, out_dir: Path) -> Path:
    existing = latest_nvflare_wheel(variant, repo / "dist")
    if existing is None:
        raise SystemExit(f"No existing NVFLARE {label} wheel found under {repo / 'dist'}.")
    target = out_dir / existing.name
    shutil.copy2(existing, target)
    emit(f"Using existing {label} wheel: {existing.name}")
    return target


def clean_wheels(out_dir: Path) -> None:
    for pattern in ("nvflare-*.whl", "nvflare_nightly-*.whl"):
        for wheel in out_dir.glob(pattern):
            wheel.unlink()


def build_nvflare_wheel(
    *,
    repo: Path,
    package_skills: str,
    label: str,
    variant: str,
    out_dir: Path,
    build_wheel: bool,
    allow_existing_fallback: bool,
) -> Path:
    clean_wheels(out_dir)
    if not build_wheel:
        emit(f"Skipping {label} wheel build because BUILD_NVFLARE_WHEEL=false.")
        return stage_existing_wheel(repo, variant, label, out_dir)

    uv = shutil.which("uv")
    if uv is None:
        raise SystemExit(
            "Host uv is required. Install uv or set BUILD_NVFLARE_WHEEL=false to use existing local wheels."
        )

    emit(f"=== Building NVFlare {label} wheel ===")
    env = {**os.environ, "NVFLARE_PACKAGE_AGENT_SKILLS": package_skills}
    status = subprocess.call([uv, "build", "--wheel", "--out-dir", str(out_dir)], cwd=repo, env=env)
    if status != 0:
        if allow_existing_fallback:
            emit(f"{label} wheel build failed; using newest existing matching local wheel.", stderr=True)
            return stage_existing_wheel(repo, variant, label, out_dir)
        raise SystemExit(status)

    wheel = latest_nvflare_wheel(variant, out_dir)
    if wheel is None:
        expected = (
            "with 'no_skills' in its file name" if variant == "no_skills" else "without 'no_skills' in its file name"
        )
        raise SystemExit(f"No NVFLARE {label} wheel found under {out_dir}. Expected a wheel {expected}.")
    return wheel


def write_wheel_metadata(
    *,
    repo: Path,
    variant: str,
    package_skills: str,
    wheel: Path,
    out_dir: Path,
    build_wheel: bool,
    allow_existing_fallback: bool,
) -> None:
    payload = {
        "allow_existing_wheel_fallback": str(allow_existing_fallback).lower(),
        "build_nvflare_wheel": str(build_wheel).lower(),
        "filename": wheel.name,
        "git_commit": git_commit(repo),
        "nvflare_package_agent_skills": package_skills,
        "sha256": file_sha256(wheel),
        "variant": variant,
    }
    (out_dir / "nvflare_wheel_metadata.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def copy_harness(src: Path, dst: Path) -> None:
    def ignore(_dir: str, names: list[str]) -> set[str]:
        return {name for name in names if name == "__pycache__" or name.endswith(".pyc")}

    shutil.copytree(src, dst, ignore=ignore)


def prepare_build_context() -> Path:
    context = Path(tempfile.mkdtemp(prefix="nvflare-agent-build-context.", dir=os.environ.get("TMPDIR") or None))
    (context / "dist" / "skills").mkdir(parents=True)
    (context / "dist" / "no_skills").mkdir(parents=True)
    shutil.copy2(SCRIPT_DIR / "docker" / "Dockerfile", context / "Dockerfile")
    copy_harness(SCRIPT_DIR / "harness", context / "harness")
    shutil.copy2(SCRIPT_DIR / "docker" / "build_context.dockerignore", context / ".dockerignore")
    return context


def docker_build(
    *,
    image: str,
    target: str,
    context: Path,
    uv_image: str,
    node_image: str,
    agent_build_args: dict[str, str],
    no_cache: bool,
) -> None:
    cache_args = ["--no-cache"] if no_cache else []
    rendered_build_args = []
    for key, value in sorted(agent_build_args.items()):
        rendered_build_args.extend(["--build-arg", f"{key}={value}"])
    status = subprocess.call(
        [
            "docker",
            "build",
            *cache_args,
            "--target",
            target,
            "--build-arg",
            f"UV_IMAGE={uv_image}",
            "--build-arg",
            f"NODE_IMAGE={node_image}",
            *rendered_build_args,
            "-t",
            image,
            str(context),
        ]
    )
    if status != 0:
        raise SystemExit(status)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build NVFLARE agent benchmark Docker images.")
    parser.parse_args(argv)

    adapter = benchmark_agent_adapter_from_env()
    targets = adapter.image_targets(os.environ)
    image_name = targets.skills
    baseline_image_name = targets.baseline
    report_image_name = targets.report
    build_skills_image = env_flag("BUILD_SKILLS_IMAGE", "true")
    build_baseline_image = env_flag("BUILD_BASELINE_IMAGE", "true")
    build_wheel = env_flag("BUILD_NVFLARE_WHEEL", "true")
    allow_existing_fallback = env_flag("ALLOW_EXISTING_WHEEL_FALLBACK", "false")
    docker_build_no_cache = env_flag("DOCKER_BUILD_NO_CACHE", "false")
    uv_image = os.environ.get("UV_IMAGE", DEFAULT_UV_IMAGE)
    node_image = os.environ.get("NODE_IMAGE", DEFAULT_NODE_IMAGE)
    agent_build_args = adapter.build_args_from_env(os.environ)

    context = prepare_build_context()
    try:
        emit("=== Preparing minimal Docker build context ===")
        if build_skills_image or build_baseline_image:
            repo = resolve_nvflare_repo()
            emit(f"Using NVFlare repo: {repo}")

            if build_skills_image:
                skills_wheel = build_nvflare_wheel(
                    repo=repo,
                    package_skills="1",
                    label="skills",
                    variant="skills",
                    out_dir=context / "dist" / "skills",
                    build_wheel=build_wheel,
                    allow_existing_fallback=allow_existing_fallback,
                )
                emit(f"Using skills wheel: {skills_wheel.name}")
                write_wheel_metadata(
                    repo=repo,
                    variant="skills",
                    package_skills="1",
                    wheel=skills_wheel,
                    out_dir=context / "dist" / "skills",
                    build_wheel=build_wheel,
                    allow_existing_fallback=allow_existing_fallback,
                )

            if build_baseline_image:
                no_skills_wheel = build_nvflare_wheel(
                    repo=repo,
                    package_skills="0",
                    label="no-skills",
                    variant="no_skills",
                    out_dir=context / "dist" / "no_skills",
                    build_wheel=build_wheel,
                    allow_existing_fallback=allow_existing_fallback,
                )
                emit(f"Using no-skills wheel: {no_skills_wheel.name}")
                write_wheel_metadata(
                    repo=repo,
                    variant="no_skills",
                    package_skills="0",
                    wheel=no_skills_wheel,
                    out_dir=context / "dist" / "no_skills",
                    build_wheel=build_wheel,
                    allow_existing_fallback=allow_existing_fallback,
                )

        emit(f"Docker build context: {context}")
        emit(f"UV image: {uv_image}")
        emit(f"Node runtime image: {node_image}")
        for key, value in sorted(agent_build_args.items()):
            emit(f"Agent build arg: {key}={value}")
        emit(f"Docker build no-cache: {str(docker_build_no_cache).lower()}")
        if build_skills_image:
            emit(f"=== Building Docker skills image: {image_name} ===")
            docker_build(
                image=image_name,
                target="skills",
                context=context,
                uv_image=uv_image,
                node_image=node_image,
                agent_build_args=agent_build_args,
                no_cache=docker_build_no_cache,
            )
        if build_baseline_image:
            emit(f"=== Building Docker baseline image: {baseline_image_name} ===")
            docker_build(
                image=baseline_image_name,
                target="baseline",
                context=context,
                uv_image=uv_image,
                node_image=node_image,
                agent_build_args=agent_build_args,
                no_cache=docker_build_no_cache,
            )

        emit(f"Skills image: {image_name}")
        emit(f"Baseline image: {baseline_image_name}")
        emit(f"Report image: {report_image_name}")
        return 0
    finally:
        shutil.rmtree(context, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
