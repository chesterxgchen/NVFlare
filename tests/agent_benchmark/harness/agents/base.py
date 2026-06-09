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

"""Agent adapter contracts for the benchmark harness."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Protocol

SUPPORTED_BENCHMARK_AGENTS = ("codex",)


class DockerMount(Protocol):
    """Structural type for host-side Docker mount descriptors."""


class AgentAdapter(Protocol):
    """Host-side contract for invoking an agent inside the benchmark harness."""

    name: str

    def model_from_env(self, env: Mapping[str, str]) -> str:
        raise NotImplementedError

    def auth_mounts(self, host_config) -> list[DockerMount]:
        raise NotImplementedError

    def runtime_env(self, config) -> dict[str, str]:
        raise NotImplementedError

    def command(self, config) -> list[str]:
        raise NotImplementedError

    def parse_usage(self, events_path: Path) -> dict:
        raise NotImplementedError

    def parse_activity(self, events_path: Path) -> dict:
        raise NotImplementedError

    def final_message_path(self, result_dir: Path) -> Path:
        raise NotImplementedError

    def metadata(self) -> dict:
        raise NotImplementedError


def normalize_agent_event(agent: str, raw_line: str) -> dict | None:
    """Normalize one raw structured event line for the selected agent."""

    validate_benchmark_agent(agent)
    if agent == "codex":
        from .codex import normalize_codex_event

        return normalize_codex_event(raw_line)
    raise AssertionError(f"unreachable unsupported benchmark agent: {agent}")


def validate_benchmark_agent(agent: str) -> str:
    """Return a supported benchmark agent name or raise a clear error."""

    if agent in SUPPORTED_BENCHMARK_AGENTS:
        return agent
    supported = ", ".join(SUPPORTED_BENCHMARK_AGENTS)
    raise ValueError(
        f"Unsupported BENCHMARK_AGENT={agent!r}. Supported benchmark agents: {supported}. "
        "Non-Codex adapters are not implemented yet."
    )
