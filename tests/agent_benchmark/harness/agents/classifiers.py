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

"""Exit and failure classifier registries for benchmark agent adapters."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def generic_cli_exit(exit_code: int, stderr_path: Path) -> dict[str, Any]:
    stderr_text = ""
    try:
        stderr_text = stderr_path.read_text(encoding="utf-8", errors="replace")[:4000]
    except OSError:
        pass
    return {
        "classifier": "generic_cli",
        "exit_code": exit_code,
        "passed": exit_code == 0,
        "failure_category": "agent_cli_failure" if exit_code else None,
        "stderr_excerpt": stderr_text,
    }


def codex_cli_exit(exit_code: int, stderr_path: Path) -> dict[str, Any]:
    summary = generic_cli_exit(exit_code, stderr_path)
    summary["classifier"] = "codex_cli"
    stderr_lower = str(summary.get("stderr_excerpt") or "").lower()
    if "model" in stderr_lower and ("not supported" in stderr_lower or "unsupported" in stderr_lower):
        summary["failure_category"] = "agent_model_unsupported"
    elif "auth" in stderr_lower or "api key" in stderr_lower or "login" in stderr_lower:
        summary["failure_category"] = "agent_auth_failure"
    elif exit_code == 127:
        summary["failure_category"] = "agent_cli_missing"
    return summary


EXIT_CLASSIFIERS = {
    "generic_cli": generic_cli_exit,
    "codex_cli": codex_cli_exit,
}


def validate_exit_classifier(classifier_id: str) -> None:
    if classifier_id not in EXIT_CLASSIFIERS:
        raise ValueError(f"Unknown agent exit classifier: {classifier_id}")


def classify_exit(exit_code: int, stderr_path: Path, classifier_id: str) -> dict[str, Any]:
    validate_exit_classifier(classifier_id)
    classifier = EXIT_CLASSIFIERS[classifier_id]
    return classifier(exit_code, stderr_path)
