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


def test_host_cli_accepts_results_root(tmp_path):
    from harness.host.common import parse_host_cli_options

    job_input = tmp_path / "job"
    results_root = tmp_path / "bench-results"
    job_input.mkdir()

    options = parse_host_cli_options(
        ["--results-root", str(results_root), "--training-code", str(job_input)],
        "process-eval",
    )

    assert options.job_input == job_input
    assert options.results_root == results_root
    assert options.result_root is None
    assert options.result_dir is None


def test_host_cli_output_dir_maps_to_exact_result_location(tmp_path):
    from harness.host.common import parse_host_cli_options

    job_input = tmp_path / "job"
    output_dir = tmp_path / "exact-output"
    job_input.mkdir()

    comparison_options = parse_host_cli_options(["--output-dir", str(output_dir), str(job_input)], "process-eval")
    single_options = parse_host_cli_options(["--output-dir", str(output_dir), str(job_input)], "run-one")

    assert comparison_options.result_root == output_dir
    assert comparison_options.result_dir is None
    assert single_options.result_dir == output_dir
    assert single_options.result_root is None


def test_benchmark_prompt_requires_installing_source_requirements():
    prompt = (BENCHMARK_ROOT / "prompts" / "benchmark_prompt.txt").read_text(encoding="utf-8")

    assert "requirements-train.txt" in prompt
    assert "install the applicable job dependencies" in prompt
    assert "before treating dependency or import failures as blockers" in prompt


def test_shared_lifecycle_requires_dependency_preflight_before_missing_dependency_blocker():
    lifecycle = (Path(__file__).resolve().parents[3] / "skills" / "_shared" / "nvflare-job-lifecycle.md").read_text(
        encoding="utf-8"
    )

    assert "all generated NVFLARE jobs" in lifecycle
    assert "recipe-, framework-, and algorithm-independent" in lifecycle
    assert "requirements-train.txt" in lifecycle
    assert "python -m pip install -r <requirements-file>" in lifecycle
    assert "dependency or import failures" in lifecycle
    assert "Report missing dependencies as blockers only when" in lifecycle
