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

"""Run-mode definitions shared by wrappers and reports."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from typing import Iterable


@dataclass(frozen=True)
class ModeSpec:
    label: str
    mode: str
    skills_enabled: bool
    process_eval_enabled: bool
    nvflare_skill_eval: str

    @property
    def nvflare_skill_eval_state(self) -> str:
        return "on" if self.nvflare_skill_eval == "on" else "off"


PROCESS_EVAL_RUNS: tuple[ModeSpec, ...] = (
    ModeSpec("No skills", "without_skills", False, False, ""),
    ModeSpec("With skills, skill eval off", "with_skills_eval_off", True, False, ""),
    ModeSpec("With skills, skill eval on", "with_skills_eval_on", True, True, "on"),
)

PAIR_RUNS: tuple[ModeSpec, ...] = (
    ModeSpec("No skills", "without_skills", False, False, ""),
    ModeSpec("With skills, skill eval off", "with_skills_eval_off", True, False, ""),
)

KNOWN_RUNS: tuple[ModeSpec, ...] = PROCESS_EVAL_RUNS
KNOWN_RUN_BY_MODE: dict[str, ModeSpec] = {item.mode: item for item in KNOWN_RUNS}


def mode_records(runs: Iterable[ModeSpec]) -> list[dict[str, object]]:
    return [asdict(item) | {"nvflare_skill_eval_state": item.nvflare_skill_eval_state} for item in runs]


def mode_names(runs: Iterable[ModeSpec]) -> list[str]:
    return [item.mode for item in runs]


def mode_spec(mode: str) -> ModeSpec:
    try:
        return KNOWN_RUN_BY_MODE[mode]
    except KeyError as exc:
        valid_modes = ", ".join(KNOWN_RUN_BY_MODE)
        raise ValueError(f"Unknown mode {mode}; expected one of: {valid_modes}") from exc


def mode_shell_rows(runs: Iterable[ModeSpec]) -> list[str]:
    rows = []
    for item in runs:
        rows.append(
            "|".join(
                [
                    item.mode,
                    "true" if item.skills_enabled else "false",
                    "true" if item.process_eval_enabled else "false",
                    item.nvflare_skill_eval,
                ]
            )
        )
    return rows


def select_mode(
    runs: Iterable[ModeSpec],
    *,
    skills_enabled: bool | None = None,
    process_eval_enabled: bool | None = None,
    nvflare_skill_eval_state: str | None = None,
) -> str:
    for item in runs:
        if skills_enabled is not None and item.skills_enabled != skills_enabled:
            continue
        if process_eval_enabled is not None and item.process_eval_enabled != process_eval_enabled:
            continue
        if nvflare_skill_eval_state is not None and item.nvflare_skill_eval_state != nvflare_skill_eval_state:
            continue
        return item.mode
    raise RuntimeError("no benchmark mode matches the requested role")


PROCESS_EVAL_MODE_NAMES = mode_names(PROCESS_EVAL_RUNS)
PAIR_MODE_NAMES = mode_names(PAIR_RUNS)
NO_SKILLS_MODE = select_mode(PROCESS_EVAL_RUNS, skills_enabled=False)
SKILLS_EVAL_OFF_MODE = select_mode(PROCESS_EVAL_RUNS, skills_enabled=True, nvflare_skill_eval_state="off")
SKILLS_EVAL_ON_MODE = select_mode(PROCESS_EVAL_RUNS, skills_enabled=True, nvflare_skill_eval_state="on")
PAIR_WITHOUT_MODE = select_mode(PAIR_RUNS, skills_enabled=False)
PAIR_WITH_MODE = select_mode(PAIR_RUNS, skills_enabled=True)


def process_eval_runs() -> list[dict[str, object]]:
    return mode_records(PROCESS_EVAL_RUNS)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("process-eval-json", "process-eval-shell", "pair-json", "pair-shell"))
    args = parser.parse_args()

    if args.command == "process-eval-json":
        print(json.dumps(mode_records(PROCESS_EVAL_RUNS), indent=2, sort_keys=True))
    elif args.command == "pair-json":
        print(json.dumps(mode_records(PAIR_RUNS), indent=2, sort_keys=True))
    else:
        runs = PAIR_RUNS if args.command == "pair-shell" else PROCESS_EVAL_RUNS
        for row in mode_shell_rows(runs):
            print(row)


if __name__ == "__main__":
    main()
