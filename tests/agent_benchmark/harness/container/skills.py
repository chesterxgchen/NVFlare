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

"""Container-side skill visibility setup for benchmark runs."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Callable

from ..agents.base import SkillExposureResult, SkillExposureSpec
from ..common import write_json


def discover_bundled_skills_root() -> str | None:
    try:
        from nvflare.tool.agent import skill_manager

        source = skill_manager.find_skill_source()
        root = getattr(source, "root", None)
        return str(root) if root else None
    except Exception:
        return None


def copy_optional_metadata_files(source_dir: Path, result_dir: Path, names: tuple[str, ...]) -> dict[str, Any]:
    copied = []
    missing = []
    for name in names:
        source = source_dir / name
        if source.is_file():
            target_name = name.removeprefix("nvflare_")
            shutil.copy2(source, result_dir / target_name)
            copied.append({"source": str(source), "target": str(result_dir / target_name)})
        else:
            missing.append(str(source))
    payload = {"copied": copied, "missing": missing}
    if missing:
        write_json(result_dir / "skills_metadata_missing.json", payload)
    return payload


def copy_metadata_paths(paths: list[Path], result_dir: Path) -> list[dict[str, str]]:
    copied = []
    missing = []
    for source in paths:
        if source.is_file():
            target_name = source.name.removeprefix("nvflare_")
            target = result_dir / target_name
            shutil.copy2(source, target)
            copied.append({"source": str(source), "target": str(target)})
        else:
            missing.append(str(source))
    if missing:
        write_json(result_dir / "skills_metadata_missing.json", {"copied": copied, "missing": missing})
    return copied


def remove_directory_contents(root: Path) -> list[str]:
    disabled = []
    root.mkdir(parents=True, exist_ok=True)
    for child in list(root.iterdir()):
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink(missing_ok=True)
        disabled.append(str(child))
    return disabled


def apply_skill_exposure(
    *,
    spec: SkillExposureSpec,
    skills_enabled: bool,
    result_dir: Path,
    nvflare_image_kind: str,
    bundled_skills_root: Callable[[], str | None] = discover_bundled_skills_root,
) -> SkillExposureResult:
    if spec.mechanism_type == "none":
        result = SkillExposureResult(status="skipped", mechanism_type=spec.mechanism_type)
        write_json(
            result_dir / "skills_state.json",
            {
                "status": result.status,
                "skills_enabled": skills_enabled,
                "mechanism_type": spec.mechanism_type,
                "source": nvflare_image_kind,
            },
        )
        return result

    if skills_enabled:
        if spec.skill_root and (
            not spec.skill_root.is_dir() or not any(path.is_dir() for path in spec.skill_root.iterdir())
        ):
            write_json(
                result_dir / "skills_state.json",
                {
                    "status": "error",
                    "reason": f"preinstalled skills are missing from {spec.skill_root}",
                    "mechanism_type": spec.mechanism_type,
                },
            )
            raise SystemExit(2)
        metadata_files = copy_metadata_paths(spec.metadata_files, result_dir)
        write_json(
            result_dir / "skills_state.json",
            {
                "status": "enabled",
                "source": nvflare_image_kind,
                "skills_enabled": True,
                "mechanism_type": spec.mechanism_type,
            },
        )
        return SkillExposureResult(
            status="enabled",
            mechanism_type=spec.mechanism_type,
            installed_paths=[str(spec.skill_root)] if spec.skill_root else [],
            metadata_files=metadata_files,
        )

    disabled_paths = remove_directory_contents(spec.skill_root) if spec.skill_root else []
    bundled_root = bundled_skills_root() if spec.disable_packaged_source else None
    removed_packaged_source = False
    if bundled_root:
        path = Path(bundled_root)
        if path.is_dir():
            shutil.rmtree(path)
            removed_packaged_source = True
            disabled_paths.append(str(path))

    write_json(
        result_dir / "skills_state.json",
        {
            "status": "disabled",
            "source": nvflare_image_kind,
            "skills_enabled": False,
            "image_kind": nvflare_image_kind,
            "mechanism_type": spec.mechanism_type,
            "disabled_paths": disabled_paths,
            "packaged_skill_source_removed_during_agent": removed_packaged_source,
            "packaged_skill_source_path": bundled_root,
            "reporting_note": (
                "Wrapper-side reports run from the skills image so benchmark contracts are available "
                "outside the measured agent container."
            ),
        },
    )
    write_json(
        result_dir / "skills_list.json",
        {"status": "skipped", "installed": [], "reason": "skills intentionally removed for baseline run"},
    )
    return SkillExposureResult(
        status="disabled",
        mechanism_type=spec.mechanism_type,
        disabled_paths=disabled_paths,
    )
