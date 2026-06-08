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

import sys
from pathlib import Path

BENCHMARK_ROOT = Path(__file__).resolve().parents[2] / "agent_benchmark"
sys.path.insert(0, str(BENCHMARK_ROOT))


def test_codex_event_normalizer_returns_agent_event():
    from harness.agents.base import normalize_agent_event

    event = normalize_agent_event("codex", '{"type": "turn", "message": "ok"}')

    assert event["type"] == "turn"
    assert event["message"] == "ok"
    assert event["harness_timestamp"]


def test_host_docker_args_use_migrated_container_entrypoint(tmp_path):
    from harness.host.common import CaseConfig, ImageConfig, docker_args_for_case

    job_input = tmp_path / "job"
    prompt_dir = tmp_path / "prompts"
    result_dir = tmp_path / "results"
    codex_home = tmp_path / ".codex"
    job_input.mkdir()
    prompt_dir.mkdir()
    prompt_path = prompt_dir / "benchmark_prompt.txt"
    prompt_path.write_text("convert this job\n", encoding="utf-8")

    config = CaseConfig(
        mode="with_skills_eval_off",
        use_preinstalled_skills=True,
        process_eval=False,
        nvflare_skill_eval="",
        job_input_dir=job_input,
        result_dir=result_dir,
        prompt_dir=prompt_dir,
        prompt_path=prompt_path,
        images=ImageConfig(
            image_name="nvflare-agent-benchmark:codex-skills",
            baseline_image_name="nvflare-agent-benchmark:codex-baseline",
            report_image_name="nvflare-agent-benchmark:codex-skills",
        ),
        progress_interval_seconds="0",
        host_codex_home=codex_home,
        mount_host_codex_auth=False,
    )

    args = docker_args_for_case(config)

    assert "-m" in args
    module_index = args.index("-m") + 1
    assert args[module_index] == "harness.container.agent_run"
