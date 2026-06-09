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

import json
import sys
from pathlib import Path


def test_codex_event_normalizer_returns_agent_event():
    from harness.agents.registry import load_agent_adapter

    event = load_agent_adapter("codex").normalize_event('{"type": "turn", "message": "ok"}')

    assert event["type"] == "turn"
    assert event["message"] == "ok"
    assert event["harness_timestamp"]


def test_unsupported_agent_event_normalizer_fails_fast():
    from harness.agents.registry import load_agent_adapter

    try:
        load_agent_adapter("claude")
    except ValueError as exc:
        assert "BENCHMARK_AGENT='claude'" in str(exc)
        assert "known but not implemented" in str(exc)
    else:
        raise AssertionError("unsupported benchmark agent should fail before event parsing")


def test_codex_agent_config_loads_parser_and_classifier_ids():
    from harness.agents.config import AgentConfig

    config_path = Path(__file__).resolve().parents[2] / "agent_benchmark" / "harness" / "agents" / "codex.yaml"

    config = AgentConfig.load(config_path)

    assert config.name == "codex"
    assert config.events.parser == "codex_jsonl"
    assert config.usage.parser == "codex_cumulative_usage"
    assert config.activity.parser == "codex_jsonl_activity"
    assert config.exit_classifier == "codex_cli"
    assert "{prompt_text}" not in json.dumps(config.raw)


def test_claude_agent_config_uses_config_dir_and_valid_final_message_source():
    from harness.agents.config import AgentConfig

    config_path = Path(__file__).resolve().parents[2] / "agent_benchmark" / "harness" / "agents" / "claude.yaml"

    config = AgentConfig.load(config_path)

    assert config.agent_home_env == "CLAUDE_CONFIG_DIR"
    assert config.final_message["source_type"] == "stdout_tail"


def test_agent_config_rejects_unknown_parser_id(tmp_path):
    from harness.agents.config import AgentConfig

    source_path = Path(__file__).resolve().parents[2] / "agent_benchmark" / "harness" / "agents" / "codex.yaml"
    config_path = tmp_path / "bad_parser.yaml"
    config_path.write_text(source_path.read_text(encoding="utf-8").replace("codex_jsonl", "missing_parser", 1))

    try:
        AgentConfig.load(config_path)
    except ValueError as exc:
        assert "Unknown agent event parser: missing_parser" in str(exc)
    else:
        raise AssertionError("unknown adapter event parser should fail during config load")


def test_agent_config_rejects_unknown_exit_classifier(tmp_path):
    from harness.agents.config import AgentConfig

    source_path = Path(__file__).resolve().parents[2] / "agent_benchmark" / "harness" / "agents" / "codex.yaml"
    config_path = tmp_path / "bad_exit.yaml"
    config_path.write_text(source_path.read_text(encoding="utf-8").replace("classifier: codex_cli", "classifier: bad"))

    try:
        AgentConfig.load(config_path)
    except ValueError as exc:
        assert "Unknown agent exit classifier: bad" in str(exc)
    else:
        raise AssertionError("unknown adapter exit classifier should fail during config load")


def test_agent_config_rejects_unknown_final_message_source_type(tmp_path):
    from harness.agents.config import AgentConfig

    source_path = Path(__file__).resolve().parents[2] / "agent_benchmark" / "harness" / "agents" / "codex.yaml"
    config_path = tmp_path / "bad_final_source.yaml"
    config_path.write_text(source_path.read_text(encoding="utf-8").replace("source_type: file", "source_type: bad"))

    try:
        AgentConfig.load(config_path)
    except ValueError as exc:
        assert "Unknown final message source_type: bad" in str(exc)
    else:
        raise AssertionError("unknown final message source type should fail during config load")


def test_agent_config_rejects_unknown_final_message_parser(tmp_path):
    from harness.agents.config import AgentConfig

    source_path = Path(__file__).resolve().parents[2] / "agent_benchmark" / "harness" / "agents" / "claude.yaml"
    config_path = tmp_path / "bad_final_parser.yaml"
    config_path.write_text(
        source_path.read_text(encoding="utf-8").replace(
            "parser: generic_stdout_last_message", "parser: missing_final_parser"
        )
    )

    try:
        AgentConfig.load(config_path)
    except ValueError as exc:
        assert "Unknown final message parser: missing_final_parser" in str(exc)
    else:
        raise AssertionError("unknown final message parser should fail during config load")


def test_agent_adapter_cache_can_be_cleared_for_tests():
    from harness.agents.registry import clear_agent_adapter_cache, load_agent_adapter

    first = load_agent_adapter("codex")
    clear_agent_adapter_cache()
    second = load_agent_adapter("codex")

    assert first is not second


def test_codex_adapter_build_args_use_default_and_env_override(monkeypatch):
    from harness.agents.registry import load_agent_adapter

    adapter = load_agent_adapter("codex")
    monkeypatch.delenv("CODEX_CLI_VERSION", raising=False)
    assert adapter.build_args_from_env({})["CODEX_CLI_VERSION"] == "0.137.0"
    assert adapter.build_args_from_env({"CODEX_CLI_VERSION": "0.200.0"})["CODEX_CLI_VERSION"] == "0.200.0"


def test_agent_config_rejects_prompt_text_placeholder(tmp_path):
    from harness.agents.config import AgentConfig

    config_path = tmp_path / "unsafe.yaml"
    config_path.write_text(
        json.dumps(
            {
                "name": "unsafe",
                "display_name": "Unsafe Agent",
                "default_model": "default",
                "agent_home_env": "UNSAFE_HOME",
                "container_home": "/workspace/.unsafe",
                "launch": {"argv": ["unsafe", "run", "{prompt_text}"]},
            }
        ),
        encoding="utf-8",
    )

    try:
        AgentConfig.load(config_path)
    except ValueError as exc:
        assert "must not use {prompt_text}" in str(exc)
    else:
        raise AssertionError("agent adapter config must reject prompt_text injection paths")


def test_codex_adapter_launch_spec_uses_prompt_file_without_prompt_text(tmp_path):
    from harness.agents.base import AgentLaunchContext
    from harness.agents.registry import load_agent_adapter

    result_dir = tmp_path / "results"
    workspace_dir = tmp_path / "workspace"
    prompt_file = tmp_path / "prompt.txt"
    result_dir.mkdir()
    workspace_dir.mkdir()
    prompt_file.write_text("Convert this job. Do not leak prompt text into argv.\n", encoding="utf-8")
    config = AgentLaunchContext(
        model="test-model",
        model_was_explicit=True,
        result_dir=result_dir,
        workspace_dir=workspace_dir,
        prompt_file=prompt_file,
        events_dest=result_dir / "agent_events.jsonl",
        stderr_dest=result_dir / "agent_stderr.txt",
        final_message_dest=result_dir / "agent_last_message.txt",
    )

    spec = load_agent_adapter("codex").launch_spec(config)

    rendered_argv = " ".join(spec.argv)
    assert spec.prompt_file == prompt_file
    assert spec.prompt_input_mode == "stdin"
    assert spec.final_message_dest == result_dir / "agent_last_message.txt"
    assert "{prompt_text}" not in rendered_argv
    assert "Convert this job" not in rendered_argv
    assert spec.argv[-1] == "-"
    assert "--dangerously-bypass-approvals-and-sandbox" in spec.sandbox_flags
    assert spec.bypass_reason


def test_codex_adapter_runtime_env_sets_generic_agent_model_and_home(tmp_path):
    from types import SimpleNamespace

    from harness.agents.registry import load_agent_adapter

    agent_home = tmp_path / ".codex"
    env = load_agent_adapter("codex").runtime_env(
        SimpleNamespace(
            agent_model="test-model",
            agent_home=agent_home,
            model_was_explicit=True,
        )
    )

    assert env["BENCHMARK_AGENT"] == "codex"
    assert env["BENCHMARK_AGENT_MODEL"] == "test-model"
    assert env["CODEX_HOME"] == "/workspace/.codex"


def test_container_config_uses_generic_agent_model_and_home(monkeypatch):
    from harness.container.agent_run import AgentRunConfig

    monkeypatch.delenv("CODEX_MODEL", raising=False)
    monkeypatch.delenv("CODEX_HOME", raising=False)
    monkeypatch.setenv("BENCHMARK_AGENT", "codex")
    monkeypatch.setenv("BENCHMARK_AGENT_MODEL", "generic-model")
    monkeypatch.setenv("BENCHMARK_AGENT_HOME", "/workspace/agent-home")

    config = AgentRunConfig.from_env()

    assert config.agent_model == "generic-model"
    assert config.agent_home == Path("/workspace/agent-home")
    assert not hasattr(config, "codex_home")


def test_container_config_requires_benchmark_agent(monkeypatch):
    from harness.container.agent_run import AgentRunConfig

    monkeypatch.delenv("BENCHMARK_AGENT", raising=False)

    try:
        AgentRunConfig.from_env()
    except SystemExit as exc:
        assert "BENCHMARK_AGENT is required" in str(exc)
    else:
        raise AssertionError("in-container config should require explicit BENCHMARK_AGENT")


def test_agent_subprocess_env_hides_harness_controls_and_adapter_model_env(monkeypatch):
    from harness.agents.registry import load_agent_adapter
    from harness.container.agent_run import agent_subprocess_env

    adapter = load_agent_adapter("codex")
    monkeypatch.setenv("MODE", "with_skills")
    monkeypatch.setenv("JOB_INPUT_DIR", "/workspace/input")
    monkeypatch.setenv("BENCHMARK_AGENT", "codex")
    monkeypatch.setenv("BENCHMARK_AGENT_MODEL", "generic-model")
    monkeypatch.setenv("CODEX_MODEL", "legacy-model")
    monkeypatch.setenv("OPENAI_API_KEY", "kept-for-agent-auth")

    env = agent_subprocess_env({"CODEX_HOME": "/workspace/.codex"}, adapter)

    assert "MODE" not in env
    assert "JOB_INPUT_DIR" not in env
    assert "BENCHMARK_AGENT" not in env
    assert "BENCHMARK_AGENT_MODEL" not in env
    assert "CODEX_MODEL" not in env
    assert env["OPENAI_API_KEY"] == "kept-for-agent-auth"
    assert env["CODEX_HOME"] == "/workspace/.codex"


def test_run_agent_enforces_launch_timeout(tmp_path, monkeypatch):
    from harness.agents.base import AgentLaunchSpec, FinalMessageSource
    from harness.container import agent_run
    from harness.container.agent_run import AGENT_TIMEOUT_EXIT_CODE, AgentRunConfig, ProgressWriter, run_agent

    class TimeoutAdapter:
        def launch_spec(self, config):
            return AgentLaunchSpec(
                argv=[sys.executable, "-c", "import time; time.sleep(5)"],
                cwd=config.workspace_dir,
                prompt_file=config.prompt_file,
                prompt_input_mode="stdin",
                stdout_events_dest=config.events_dest,
                stderr_dest=config.stderr_dest,
                final_message_dest=config.final_message_dest,
                launch_timeout=1,
            )

        def normalize_event(self, raw_line):
            return None

        def final_message_source(self, result_dir):
            return FinalMessageSource(source_type="not_available")

        def model_env_names(self):
            return ()

    result_dir = tmp_path / "results"
    run_root = tmp_path / "run"
    workspace = run_root / "workspace"
    result_dir.mkdir()
    workspace.mkdir(parents=True)
    prompt = result_dir / "prompt.txt"
    prompt.write_text("prompt\n", encoding="utf-8")
    config = AgentRunConfig(
        mode="with_skills",
        use_preinstalled_skills=True,
        job_input_dir=tmp_path / "job",
        result_dir=result_dir,
        records_dir=result_dir / "records",
        run_root=run_root,
        prompt_source=prompt,
        progress_interval_seconds=0,
        nvflare_image_kind="test-skills",
        agent="test",
        agent_model="test-model",
        agent_home=tmp_path / ".agent",
        agent_model_was_explicit=False,
    )
    monkeypatch.setattr(agent_run, "load_agent_adapter", lambda _agent: TimeoutAdapter())

    _start, _end, exit_code = run_agent(config, ProgressWriter(config.mode, 0, config.progress_log_path))

    assert exit_code == AGENT_TIMEOUT_EXIT_CODE
    assert "timed out after 1 seconds" in config.agent_stderr_path.read_text(encoding="utf-8")


def test_materialize_final_message_from_stdout_tail(tmp_path):
    from collections import deque

    from harness.agents.base import FinalMessageSource
    from harness.container.agent_run import AgentRunConfig, materialize_final_message

    class StdoutAdapter:
        def final_message_source(self, result_dir):
            return FinalMessageSource(source_type="stdout_tail", tail_bytes=12, parser="generic_stdout_last_message")

    result_dir = tmp_path / "results"
    result_dir.mkdir()
    config = AgentRunConfig(
        mode="with_skills",
        use_preinstalled_skills=True,
        job_input_dir=tmp_path / "job",
        result_dir=result_dir,
        records_dir=result_dir / "records",
        run_root=tmp_path / "run",
        prompt_source=tmp_path / "prompt.txt",
        progress_interval_seconds=0,
        nvflare_image_kind="test-skills",
        agent="test",
        agent_model="test-model",
        agent_home=tmp_path / ".agent",
        agent_model_was_explicit=False,
    )

    materialize_final_message(config, StdoutAdapter(), deque(["first line\n", "final message\n"]))

    assert config.agent_last_message_path.read_text(encoding="utf-8") == "nal message\n"
    metadata = json.loads((result_dir / "final_message_source.json").read_text(encoding="utf-8"))
    assert metadata["source_type"] == "stdout_tail"
    assert metadata["status"] == "materialized"


def test_agent_availability_probe_records_missing_cli(tmp_path, monkeypatch):
    from harness.container import agent_run
    from harness.container.agent_run import AgentRunConfig, run_agent_availability_probe

    class MissingProbeAdapter:
        def availability_probe(self):
            return ["/definitely/missing/agent-cli"]

        def runtime_env(self, config):
            return {}

        def model_env_names(self):
            return ()

    result_dir = tmp_path / "results"
    result_dir.mkdir()
    config = AgentRunConfig(
        mode="with_skills",
        use_preinstalled_skills=True,
        job_input_dir=tmp_path / "job",
        result_dir=result_dir,
        records_dir=result_dir / "records",
        run_root=tmp_path / "run",
        prompt_source=tmp_path / "prompt.txt",
        progress_interval_seconds=0,
        nvflare_image_kind="test-skills",
        agent="test",
        agent_model="test-model",
        agent_home=tmp_path / ".agent",
        agent_model_was_explicit=False,
    )
    monkeypatch.setattr(agent_run, "load_agent_adapter", lambda _agent: MissingProbeAdapter())

    try:
        run_agent_availability_probe(config)
    except RuntimeError as exc:
        assert "Agent availability probe failed to start" in str(exc)
    else:
        raise AssertionError("missing agent CLI should fail availability probe")

    probe = json.loads((result_dir / "agent_availability_probe.json").read_text(encoding="utf-8"))
    assert probe["status"] == "failed"
    assert probe["exit_code"] == 127


def test_host_image_config_rejects_unsupported_agent(monkeypatch):
    from harness.host.common import ImageConfig

    monkeypatch.setenv("BENCHMARK_AGENT", "claude")

    try:
        ImageConfig.from_env()
    except SystemExit as exc:
        assert "BENCHMARK_AGENT='claude'" in str(exc)
        assert "known but not implemented" in str(exc)
    else:
        raise AssertionError("unsupported benchmark agent should fail before image selection")


def test_host_docker_args_use_migrated_container_entrypoint(tmp_path):
    from harness.agents.registry import load_agent_adapter
    from harness.host.common import CONTAINER_PROMPT_PATH, CaseConfig, ImageConfig, docker_args_for_case

    job_input = tmp_path / "job"
    prompt_dir = tmp_path / "prompts"
    result_dir = tmp_path / "results"
    agent_home = tmp_path / ".codex"
    job_input.mkdir()
    prompt_dir.mkdir()
    prompt_path = prompt_dir / "benchmark_prompt.txt"
    prompt_path.write_text("convert this job\n", encoding="utf-8")

    config = CaseConfig(
        mode="with_skills",
        use_preinstalled_skills=True,
        job_input_dir=job_input,
        result_dir=result_dir,
        prompt_path=prompt_path,
        images=ImageConfig(
            image_name="nvflare-agent-benchmark:codex-skills",
            baseline_image_name="nvflare-agent-benchmark:codex-baseline",
            report_image_name="nvflare-agent-benchmark:codex-skills",
        ),
        progress_interval_seconds="0",
        agent="codex",
        agent_model="unspecified_default",
        model_was_explicit=False,
        adapter=load_agent_adapter("codex"),
        host_agent_home=agent_home,
        mount_host_agent_auth=False,
    )

    args = docker_args_for_case(config)

    assert "-m" in args
    module_index = args.index("-m") + 1
    assert args[module_index] == "harness.container.agent_run"
    assert f"{prompt_path}:{CONTAINER_PROMPT_PATH}:ro" in args
    assert f"PROMPT_SOURCE={CONTAINER_PROMPT_PATH}" in args
    assert "RECORDS_DIR=/workspace/results/records" in args


def test_host_cli_accepts_results_root(tmp_path):
    from harness.host.common import parse_host_cli_options

    job_input = tmp_path / "job"
    prompt = tmp_path / "prompt.txt"
    results_root = tmp_path / "bench-results"
    job_input.mkdir()
    prompt.write_text("convert this job\n", encoding="utf-8")

    options = parse_host_cli_options(
        ["--prompt", str(prompt), "--results-root", str(results_root), "--training-code", str(job_input)],
        "pair",
    )

    assert options.job_input == job_input
    assert options.prompt_path == prompt
    assert options.results_root == results_root
    assert options.result_root is None
    assert options.result_dir is None


def test_host_cli_output_dir_maps_to_exact_result_location(tmp_path):
    from harness.host.common import parse_host_cli_options

    job_input = tmp_path / "job"
    prompt = tmp_path / "prompt.txt"
    output_dir = tmp_path / "exact-output"
    job_input.mkdir()
    prompt.write_text("convert this job\n", encoding="utf-8")

    comparison_options = parse_host_cli_options(
        ["--prompt", str(prompt), "--output-dir", str(output_dir), str(job_input)],
        "pair",
    )
    single_options = parse_host_cli_options(
        ["--prompt", str(prompt), "--output-dir", str(output_dir), str(job_input)],
        "run-one",
    )

    assert comparison_options.result_root == output_dir
    assert comparison_options.result_dir is None
    assert single_options.result_dir == output_dir
    assert single_options.result_root is None


def test_host_cli_requires_prompt_path(tmp_path):
    from harness.host.common import parse_host_cli_options

    job_input = tmp_path / "job"
    job_input.mkdir()

    try:
        parse_host_cli_options([str(job_input)], "pair")
    except SystemExit as exc:
        assert "Prompt file is required" in str(exc)
    else:
        raise AssertionError("parse_host_cli_options should require --prompt")


def test_container_config_rejects_unknown_mode(monkeypatch):
    from harness.container.agent_run import AgentRunConfig

    monkeypatch.setenv("MODE", "with_skill_typo")

    try:
        AgentRunConfig.from_env()
    except SystemExit as exc:
        assert "Unknown MODE with_skill_typo" in str(exc)
        assert "without_skills" in str(exc)
        assert "with_skills" in str(exc)
    else:
        raise AssertionError("unknown MODE should fail before skill defaulting")


def test_container_config_rejects_mode_skill_flag_conflict(monkeypatch):
    from harness.container.agent_run import AgentRunConfig

    monkeypatch.setenv("MODE", "without_skills")
    monkeypatch.setenv("USE_PREINSTALLED_SKILLS", "true")

    try:
        AgentRunConfig.from_env()
    except SystemExit as exc:
        assert "conflicts with MODE=without_skills" in str(exc)
        assert "expected false" in str(exc)
    else:
        raise AssertionError("MODE and USE_PREINSTALLED_SKILLS disagreement should fail fast")


def test_setup_skill_availability_allows_missing_optional_metadata(tmp_path):
    from harness.container.agent_run import AgentRunConfig, setup_skill_availability

    codex_home = tmp_path / ".codex"
    result_dir = tmp_path / "results"
    skill_dir = codex_home / "skills" / "nvflare-convert-pytorch"
    skill_dir.mkdir(parents=True)
    result_dir.mkdir()

    config = AgentRunConfig(
        mode="with_skills",
        use_preinstalled_skills=True,
        job_input_dir=tmp_path / "job",
        result_dir=result_dir,
        records_dir=result_dir / "records",
        run_root=tmp_path / "run",
        prompt_source=tmp_path / "prompt.txt",
        progress_interval_seconds=0,
        nvflare_image_kind="test-skills",
        agent="codex",
        agent_model="test-model",
        agent_home=codex_home,
        agent_model_was_explicit=True,
    )

    setup_skill_availability(config)

    state = json.loads((result_dir / "skills_state.json").read_text(encoding="utf-8"))
    missing = json.loads((result_dir / "skills_metadata_missing.json").read_text(encoding="utf-8"))
    assert state["status"] == "prepared"
    assert state["skills_enabled"] is True
    assert sorted(Path(item).name for item in missing["missing"]) == [
        "nvflare_skills_build_install.json",
        "nvflare_skills_list.json",
    ]
    assert not (result_dir / "skills_build_install.json").exists()


def test_skill_exposure_carries_launch_args_and_environment(tmp_path):
    from harness.agents.base import SkillExposureSpec
    from harness.container.skills import apply_skill_exposure

    skill_root = tmp_path / "skills"
    (skill_root / "nvflare-convert-pytorch").mkdir(parents=True)
    result_dir = tmp_path / "results"
    result_dir.mkdir()

    result = apply_skill_exposure(
        spec=SkillExposureSpec(
            mechanism_type="launch_flag",
            skill_root=skill_root,
            launch_args=["--add-dir", str(skill_root)],
            environment={"AGENT_SKILLS_DIR": str(skill_root)},
        ),
        skills_enabled=True,
        result_dir=result_dir,
        nvflare_image_kind="test-skills",
    )

    state = json.loads((result_dir / "skills_state.json").read_text(encoding="utf-8"))
    assert state["status"] == "prepared"
    assert result.status == "prepared"
    assert result.launch_args == ["--add-dir", str(skill_root)]
    assert result.environment == {"AGENT_SKILLS_DIR": str(skill_root)}


def test_skill_exposure_rejects_skill_root_outside_container_home(tmp_path):
    from harness.agents.base import SkillExposureSpec
    from harness.container.skills import apply_skill_exposure

    result_dir = tmp_path / "results"
    result_dir.mkdir()
    outside = tmp_path / "outside"

    try:
        apply_skill_exposure(
            spec=SkillExposureSpec(
                mechanism_type="preinstalled_home",
                container_home=tmp_path / "agent_home",
                skill_root=outside,
            ),
            skills_enabled=False,
            result_dir=result_dir,
            nvflare_image_kind="test-baseline",
        )
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("out-of-scope skill_root should fail before removal")

    state = json.loads((result_dir / "skills_state.json").read_text(encoding="utf-8"))
    assert state["reason"] == "skill_root_outside_container_home"
    assert state["skill_root"] == str(outside)


def test_copy_optional_metadata_files_strips_nvflare_prefix(tmp_path):
    from harness.container.agent_run import copy_optional_metadata_files

    source_dir = tmp_path / "source"
    result_dir = tmp_path / "results"
    source_dir.mkdir()
    result_dir.mkdir()
    (source_dir / "nvflare_skills_list.json").write_text('{"installed": []}\n', encoding="utf-8")

    payload = copy_optional_metadata_files(
        source_dir,
        result_dir,
        ("nvflare_skills_list.json", "nvflare_skills_build_install.json"),
    )

    assert (result_dir / "skills_list.json").read_text(encoding="utf-8") == '{"installed": []}\n'
    assert payload["copied"] == [
        {
            "source": str(source_dir / "nvflare_skills_list.json"),
            "target": str(result_dir / "skills_list.json"),
        }
    ]
    assert payload["missing"] == [str(source_dir / "nvflare_skills_build_install.json")]


def test_login_shell_runtime_probe_uses_configured_venv_path(monkeypatch):
    from harness.container import agent_run

    class Result:
        returncode = 0
        stdout = "\n".join(
            [
                "PATH=/custom/venv/bin:/usr/bin",
                "python=/custom/venv/bin/python",
                "nvflare=/custom/venv/bin/nvflare",
                "nvflare_version=NVFlare 9.9",
                "nvflare_import_version=9.9",
            ]
        )

    monkeypatch.setenv("BENCHMARK_CONTAINER_VENV_DIR", "/custom/venv")
    monkeypatch.setattr(agent_run.subprocess, "run", lambda *args, **kwargs: Result())

    probe = agent_run.login_shell_runtime_probe()

    assert probe["ok"] is True
    assert probe["expected_python"] == "/custom/venv/bin/python"
    assert probe["expected_nvflare"] == "/custom/venv/bin/nvflare"


def test_finalize_timing_uses_named_lifecycle_epochs(tmp_path):
    from harness.common import write_json
    from harness.timing import LifecycleEpochs, finalize_timing

    summary_path = tmp_path / "run_summary.json"
    record_path = tmp_path / "record.json"
    activity_path = tmp_path / "agent_activity.json"
    timing_path = tmp_path / "timing.json"
    write_json(summary_path, {"process_metrics": {}})
    write_json(record_path, {"process_metrics": {}})
    write_json(activity_path, {"event_count": 3, "command_count": 2})

    finalize_timing(
        summary_path,
        record_path,
        timing_path,
        activity_path,
        LifecycleEpochs(
            script_start=10,
            skill_availability_start=11,
            skill_availability_end=13,
            input_copy_start=13,
            input_copy_end=17,
            prompt_prep_start=18,
            prompt_prep_end=20,
            agent_start=21,
            agent_end=31,
            post_process_start=31,
            post_process_end=35,
            report_outcome_start=36,
            report_outcome_end=37,
            script_end=40,
        ),
    )

    timing = json.loads(timing_path.read_text(encoding="utf-8"))
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert timing["phase_seconds"] == {
        "container_elapsed_seconds": 30,
        "setup_elapsed_seconds": 11,
        "skill_exposure_elapsed_seconds": 2,
        "input_copy_elapsed_seconds": 4,
        "prompt_prepare_elapsed_seconds": 2,
        "agent_elapsed_seconds": 10,
        "post_process_elapsed_seconds": 4,
        "report_elapsed_seconds": 1,
    }
    assert summary["activity"]["event_count"] == 3
    assert summary["activity"]["command_count"] == 2
    assert record["process_metrics"]["phase_seconds"]["agent_elapsed_seconds"] == 10


def test_write_failure_record_outputs_early_failure_artifacts(tmp_path):
    from harness.container.agent_run import write_failure_record

    result_dir = tmp_path / "results"
    records_dir = result_dir / "records"

    exit_code = write_failure_record(
        result_dir=result_dir,
        records_dir=records_dir,
        mode="with_skills",
        exit_code=2,
        error_type="RuntimeError",
        message="prompt missing",
        phase="input_validation",
        agent="codex",
        agent_model="test-model",
        skills_enabled=True,
    )

    record = json.loads((records_dir / "with_skills_record.json").read_text(encoding="utf-8"))
    early = json.loads((result_dir / "early_failure.json").read_text(encoding="utf-8"))
    summary = json.loads((result_dir / "run_summary.json").read_text(encoding="utf-8"))
    assert exit_code == 2
    assert record["harness_failure"] is True
    assert record["harness_error"]["phase"] == "input_validation"
    assert record["final_container_exit_code"] == 2
    assert early["record_path"] == str(records_dir / "with_skills_record.json")
    assert summary["harness_failure"] is True
    assert summary["final_container_exit_code"] == 2


def test_write_failure_record_defaults_to_unknown_agent(tmp_path):
    from harness.container.agent_run import write_failure_record

    result_dir = tmp_path / "results"
    records_dir = result_dir / "records"

    write_failure_record(
        result_dir=result_dir,
        records_dir=records_dir,
        mode="with_skills",
        exit_code=2,
        error_type="RuntimeError",
        message="config failed",
        phase="config",
    )

    record = json.loads((records_dir / "with_skills_record.json").read_text(encoding="utf-8"))
    assert record["agent"] == "unknown"
    assert record["process_metrics"]["agent_elapsed_seconds"] == 0


def test_merge_harness_failure_preserves_existing_record(tmp_path):
    from harness.common import write_json
    from harness.container.agent_run import AgentRunConfig, merge_harness_failure

    result_dir = tmp_path / "results"
    records_dir = result_dir / "records"
    records_dir.mkdir(parents=True)
    final_record = records_dir / "with_skills_record.json"
    write_json(
        final_record,
        {
            "mode": "with_skills",
            "agent_process_passed": True,
            "agent_process_exit_code": 0,
            "process_metrics": {"elapsed_seconds": 12},
        },
    )
    config = AgentRunConfig(
        mode="with_skills",
        use_preinstalled_skills=True,
        job_input_dir=tmp_path / "job",
        result_dir=result_dir,
        records_dir=records_dir,
        run_root=tmp_path / "run",
        prompt_source=tmp_path / "prompt.txt",
        progress_interval_seconds=0,
        nvflare_image_kind="test-skills",
        agent="codex",
        agent_model="test-model",
        agent_home=tmp_path / ".codex",
        agent_model_was_explicit=True,
    )

    exit_code = merge_harness_failure(config, RuntimeError("post process failed"), 1, "post_process")

    record = json.loads(final_record.read_text(encoding="utf-8"))
    late = json.loads((result_dir / "late_harness_failure.json").read_text(encoding="utf-8"))
    summary = json.loads((result_dir / "run_summary.json").read_text(encoding="utf-8"))
    assert exit_code == 1
    assert record["agent_process_passed"] is True
    assert record["process_metrics"]["elapsed_seconds"] == 12
    assert record["harness_error"]["phase"] == "post_process"
    assert record["harness_errors"][0]["message"] == "post process failed"
    assert late["preserved_existing_record"] is True
    assert summary["harness_failure"] is True
    assert summary["harness_errors"][0]["phase"] == "post_process"


def test_pair_result_root_cleanup_removes_legacy_eval_artifacts(tmp_path):
    from harness.host.runner import clean_pair_result_root

    result_root = tmp_path / "result"
    result_root.mkdir()
    for name in ("with_skills_eval_on", "with_skills_eval_off", "process_eval_runs", "without_skills", "with_skills"):
        path = result_root / name
        path.mkdir()
        path.joinpath("old.txt").write_text("stale\n", encoding="utf-8")
    result_root.joinpath("comprehensive_report.md").write_text("Benchmark Metrics Comparison\n", encoding="utf-8")
    result_root.joinpath("metrics_summary.json").write_text("{}\n", encoding="utf-8")
    result_root.joinpath("user_note.txt").write_text("keep\n", encoding="utf-8")

    clean_pair_result_root(result_root)

    assert not result_root.joinpath("with_skills_eval_on").exists()
    assert not result_root.joinpath("with_skills_eval_off").exists()
    assert not result_root.joinpath("process_eval_runs").exists()
    assert not result_root.joinpath("without_skills").exists()
    assert not result_root.joinpath("with_skills").exists()
    assert not result_root.joinpath("comprehensive_report.md").exists()
    assert not result_root.joinpath("metrics_summary.json").exists()
    assert result_root.joinpath("user_note.txt").read_text(encoding="utf-8") == "keep\n"


def test_benchmark_insights_explains_docker_image_failures(tmp_path):
    from harness.modes import NO_SKILLS_MODE
    from harness.reports.benchmark_insights import collect_benchmark_runs, failure_root_cause, human_readable_status

    mode_dir = tmp_path / NO_SKILLS_MODE
    mode_dir.mkdir()
    (mode_dir / "container_exit_code.json").write_text(json.dumps({"exit_code": 1}) + "\n", encoding="utf-8")
    (tmp_path / "console_output.log").write_text(
        "[without_skills] Unable to find image 'nvflare-agent-benchmark:codex-baseline' locally\n"
        "[without_skills] docker: Error response from daemon: pull access denied for nvflare-agent-benchmark\n",
        encoding="utf-8",
    )

    run = collect_benchmark_runs(tmp_path)[NO_SKILLS_MODE]

    assert run["available"] is True
    assert "Docker image unavailable" in failure_root_cause(run)
    assert "container exit 1" in human_readable_status(run)


def test_benchmark_insights_scopes_shared_console_evidence_by_mode(tmp_path):
    from harness.modes import NO_SKILLS_MODE, WITH_SKILLS_MODE
    from harness.reports.benchmark_insights import collect_benchmark_runs, dependency_reference_notes

    for mode in (NO_SKILLS_MODE, WITH_SKILLS_MODE):
        records_dir = tmp_path / mode / "records"
        records_dir.mkdir(parents=True)
        (records_dir / f"{mode}_record.json").write_text(
            json.dumps(
                {
                    "source_input_delta": {"final_files": [{"path": "requirements-train.txt"}]},
                    "workspace_delta": {
                        "workspace_added_files": (
                            [{"path": "requirements-federated.txt"}] if mode == NO_SKILLS_MODE else []
                        )
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
    (tmp_path / "console_output.log").write_text(
        "[without_skills] python3 -m pip install -r requirements-federated.txt failed\n"
        "[with_skills] completed without dependency install errors\n",
        encoding="utf-8",
    )

    runs = collect_benchmark_runs(tmp_path)

    assert dependency_reference_notes(runs[NO_SKILLS_MODE]) == [
        "`requirements-federated.txt` provenance: agent-generated file.",
    ]
    assert dependency_reference_notes(runs[WITH_SKILLS_MODE]) == []


def test_status_summary_is_human_readable_for_failures():
    from harness.modes import NO_SKILLS_MODE
    from harness.reports.benchmark_insights import status_summary

    runs = {
        NO_SKILLS_MODE: {
            "available": True,
            "container_exit": {"exit_code": 1},
            "console_text": "docker: Error response from daemon: pull access denied for nvflare-agent-benchmark",
            "run": {},
            "status": "missing",
            "validation_metric": {},
        }
    }

    summary = status_summary(runs, [NO_SKILLS_MODE])

    assert "No skills baseline: failed" in summary
    assert "container exit 1" in summary
    assert "Docker image unavailable" in summary
    assert "exit=1" not in summary


def test_failure_analysis_extracts_unsupported_model_message():
    from harness.reports.benchmark_insights import failure_evidence, failure_root_cause

    run = {
        "available": True,
        "agent_events_text": "The 'gpt-5.3-codex' model is not supported when using Codex with a ChatGPT account.",
        "container_exit": {"exit_code": 1},
        "run": {"agent_exit_code": 1},
        "status": "missing",
        "validation_metric": {},
    }

    assert failure_root_cause(run) == (
        "Agent model selection failed: The 'gpt-5.3-codex' model is not supported when using Codex with a ChatGPT account."
    )
    assert failure_evidence(run) == (
        "The 'gpt-5.3-codex' model is not supported when using Codex with a ChatGPT account."
    )


def test_failure_root_cause_prefers_agent_exit_classifier():
    from harness.reports.benchmark_insights import failure_root_cause

    run = {
        "available": True,
        "agent_events_text": "unstructured error text",
        "record": {"agent_exit_summary": {"failure_category": "agent_auth_failure"}},
        "run": {"agent_exit_code": 1},
    }

    assert failure_root_cause(run) == "Agent failure category: agent_auth_failure"


def test_failure_analysis_identifies_agent_generated_requirements_file():
    from harness.reports.benchmark_insights import dependency_reference_notes

    run = {
        "agent_last_message": "Install with python3 -m pip install -r requirements-federated.txt.",
        "record": {
            "source_input_delta": {
                "final_files": [
                    {"path": "requirements-train.txt"},
                ]
            },
            "workspace_delta": {
                "workspace_added_files": [
                    {"path": "requirements-federated.txt"},
                ]
            },
        },
    }

    assert dependency_reference_notes(run) == [
        "`requirements-federated.txt` provenance: agent-generated file.",
    ]


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


def test_readme_metric_alignment_uses_aggregated_validation_metric_scalar():
    from harness.quality_signals import metric_signal

    signal = metric_signal(
        None,
        "AUROC is the main metric.\n",
        """
Round 2 validation AUROC by site:
- `site-1`: `0.7659574468`
- `site-2`: `0.7554566645`
- `site-3`: `0.7373779931`
- aggregated best validation metric: `0.7529307015`
""",
    )

    metric = signal["reported_validation_metric"]
    assert signal["status"] == "pass"
    assert signal["aligned_with_readme"] is True
    assert signal["metric_value_available"] is True
    assert signal["metric_scalar_available"] is True
    assert metric["name"] == "AUROC"
    assert metric["value"] == 0.7529307015
    assert metric["value_scope"] == "fl_summary_metric"
    assert metric["site_value_count"] == 3
    assert metric["summary_value_label"] == "aggregated best validation metric"


def test_readme_metric_alignment_uses_named_aggregated_metric_scalar():
    from harness.quality_signals import metric_signal

    signal = metric_signal(
        None,
        "AUROC is the main metric.\n",
        """
Validation:
- Local training AUROC: 0.7531
- Best aggregated validation AUROC: 0.7623334631865992
- Final site metrics: site-1 valid AUROC 0.767293, site-2 valid AUROC 0.757374
""",
    )

    metric = signal["reported_validation_metric"]
    assert signal["status"] == "pass"
    assert signal["metric_scalar_available"] is True
    assert metric["name"] == "AUROC"
    assert metric["value"] == 0.7623334631865992
    assert metric["value_scope"] == "fl_summary_metric"
    assert metric["summary_value_label"] == "Best aggregated validation AUROC"


def test_job_guidance_metric_alignment_uses_non_readme_docs(tmp_path):
    from harness.quality_signals import metric_signal
    from harness.records import discover_job_guidance

    job = tmp_path / "job"
    docs = job / "docs"
    docs.mkdir(parents=True)
    docs.joinpath("metrics.md").write_text("Target validation metric: accuracy.\n", encoding="utf-8")

    sources, guidance_text = discover_job_guidance(job)
    signal = metric_signal(
        sources,
        guidance_text,
        "Server best validation metric at round 3: 0.8123 accuracy",
    )

    assert signal["expected_primary_metric"] == "accuracy"
    assert signal["aligned_with_job_guidance"] is True
    assert signal["sources"][0]["path"].endswith("metrics.md")
    assert signal["reported_validation_metric"]["name"] == "accuracy"


def test_job_guidance_metric_alignment_includes_prompt(tmp_path):
    from harness.quality_signals import metric_signal
    from harness.records import discover_job_guidance

    job = tmp_path / "job"
    job.mkdir()
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("Convert this job. Primary validation metric: AUROC.\n", encoding="utf-8")

    sources, guidance_text = discover_job_guidance(job, prompt)
    signal = metric_signal(
        sources,
        guidance_text,
        "Aggregated best validation metric: 0.7529 AUROC",
    )

    assert signal["expected_primary_metric"] == "AUROC"
    assert signal["aligned_with_job_guidance"] is True
    assert signal["sources"][0]["source_type"] == "prompt"


def test_job_guidance_metric_alignment_uses_source_priority(tmp_path):
    from harness.quality_signals import metric_signal
    from harness.records import discover_job_guidance

    job = tmp_path / "job"
    job.mkdir()
    job.joinpath("README.md").write_text("AUROC is the main metric.\n", encoding="utf-8")
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("Convert this job. Primary validation metric: accuracy.\n", encoding="utf-8")

    sources, guidance_text = discover_job_guidance(job, prompt)
    signal = metric_signal(
        sources,
        guidance_text,
        "Server best validation metric at round 3: 0.8123 accuracy",
    )

    assert signal["expected_primary_metric"] == "accuracy"
    assert signal["source"] == str(prompt)
    assert signal["matched_source"] == {"path": str(prompt), "source_type": "prompt"}
    assert signal["aligned_with_job_guidance"] is True


def test_job_guidance_metric_alignment_reports_matched_doc_source(tmp_path):
    from harness.quality_signals import metric_signal
    from harness.records import discover_job_guidance

    job = tmp_path / "job"
    job.mkdir()
    readme = job / "README.md"
    readme.write_text("AUROC is the main metric.\n", encoding="utf-8")
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("Convert this job with NVFLARE.\n", encoding="utf-8")

    sources, guidance_text = discover_job_guidance(job, prompt)
    signal = metric_signal(
        sources,
        guidance_text,
        "Aggregated best validation metric: 0.7529 AUROC",
    )

    assert signal["expected_primary_metric"] == "AUROC"
    assert signal["source"] == str(readme)
    assert signal["matched_source"] == {"path": str(readme), "source_type": "job_documentation"}
    assert signal["sources"][0]["source_type"] == "prompt"
    assert signal["aligned_with_job_guidance"] is True


def test_metric_mismatch_reports_actual_metric_without_marking_missing():
    from harness.modes import NO_SKILLS_MODE
    from harness.quality_signals import metric_signal
    from harness.reports.benchmark_insights import (
        benchmark_outcome,
        human_readable_status,
        missing_result_metrics_section,
        outcome_metrics_table,
    )

    signal = metric_signal(
        None,
        "AUROC is the main metric.\n",
        "Best validation accuracy: 0.8123",
    )
    run = {
        "available": True,
        "label": "No skills baseline",
        "container_exit": {"exit_code": 0},
        "run": {"final_container_exit_code": 0},
        "record": {"quality_signals": {"job_guidance_primary_validation_metric": signal}},
        "validation_metric": signal["reported_validation_metric"],
    }
    runs = {NO_SKILLS_MODE: run}

    assert signal["mismatch"] is True
    assert signal["reported_validation_metric"]["name"] == "accuracy"
    assert "completed with metric mismatch" in human_readable_status(run)
    assert benchmark_outcome(run).startswith("warn:")
    assert "accuracy 0.8123" in missing_result_metrics_section(runs, [NO_SKILLS_MODE])
    assert "no parseable validation metric" not in missing_result_metrics_section(runs, [NO_SKILLS_MODE])
    assert "| Metrics (accuracy) | accuracy 0.8123 |" in outcome_metrics_table(runs, [NO_SKILLS_MODE])


def test_missing_target_metric_section_reports_observed_alternate_metrics():
    from harness.modes import NO_SKILLS_MODE
    from harness.reports.benchmark_insights import (
        additional_or_observed_metric_values_display,
        missing_result_metrics_section,
        outcome_details_table,
    )

    run = {
        "available": True,
        "label": "No skills baseline",
        "container_exit": {"exit_code": 0},
        "run": {"final_container_exit_code": 0},
        "record": {
            "quality_signals": {
                "job_guidance_primary_validation_metric": {
                    "status": "missing",
                    "expected_primary_metric": "AUROC",
                    "evidence": "Job guidance declares AUROC as the primary metric, but the final response did not report it.",
                    "reported_validation_metric": {
                        "name": None,
                        "value": None,
                        "reported_values": [],
                        "reported_value_entries": [],
                    },
                }
            }
        },
        "validation_metric": {"name": None, "value": None, "reported_values": [], "reported_value_entries": []},
        "agent_last_message": "Validation accuracy: 0.8123\nValidation loss: 0.421",
    }

    section = missing_result_metrics_section({NO_SKILLS_MODE: run}, [NO_SKILLS_MODE])

    assert "accuracy 0.8123" in section
    assert "loss 0.4210" in section
    assert "no parseable validation metric" not in section
    assert additional_or_observed_metric_values_display(run, "AUROC") == "accuracy 0.8123; loss 0.4210"
    assert "Additional/other validation metric values" in outcome_details_table({NO_SKILLS_MODE: run}, [NO_SKILLS_MODE])


def test_failure_analysis_reports_recovered_job_failure_and_metric_gap():
    from harness.modes import NO_SKILLS_MODE
    from harness.reports.benchmark_insights import (
        additional_or_observed_metric_values_display,
        failure_analysis_section,
        outcome_details_table,
    )

    failed_output = (
        "TypeError: SmilesCNN.__init__() missing 4 required positional arguments: "
        "'vocab_size', 'embed_dim', 'num_filters', and 'dropout'\n"
        "RuntimeError: Simulator run failed with exit code 2.\n"
    )
    success_output = (
        "Finished FedAvg.\n"
        "site-1: round=0 train_loss=0.6275 valid_auroc=0.7049\n"
        "site-2: round=0 train_loss=0.6259 valid_auroc=0.7342\n"
        "Result workspace: /tmp/nvflare/ames-smoke\n"
    )
    events = [
        {
            "item": {
                "type": "command_execution",
                "id": "item_1",
                "command": "python3 fedavg_job.py --n-clients 2",
                "status": "failed",
                "exit_code": 1,
                "aggregated_output": failed_output,
            }
        },
        {
            "item": {
                "type": "command_execution",
                "id": "item_2",
                "command": "python3 fedavg_job.py --n-clients 2",
                "status": "completed",
                "exit_code": 0,
                "aggregated_output": success_output,
            }
        },
    ]
    run = {
        "available": True,
        "label": "No skills baseline",
        "container_exit": {"exit_code": 0},
        "run": {"final_container_exit_code": 0},
        "record": {
            "quality_signals": {
                "job_guidance_primary_validation_metric": {
                    "status": "missing",
                    "expected_primary_metric": "AUROC",
                    "evidence": "Job guidance declares AUROC as the primary metric, but the final response did not report it.",
                    "reported_validation_metric": {
                        "name": None,
                        "value": None,
                        "reported_values": [],
                        "reported_value_entries": [],
                    },
                }
            }
        },
        "validation_metric": {"name": None, "value": None, "reported_values": [], "reported_value_entries": []},
        "agent_events_text": "\n".join(json.dumps(event) for event in events),
    }

    section = failure_analysis_section({NO_SKILLS_MODE: run}, [NO_SKILLS_MODE])

    assert "Command evidence" in section
    assert "recovered by a later successful similar command" in section
    assert "SmilesCNN.__init__() missing 4 required positional arguments" in section
    assert "Recovery evidence" in section
    assert "a later simulator/job command exited 0" in section
    assert "valid_auroc=0.7049" in section
    assert "Metric reporting gap" in section
    assert "aggregate `AUROC` scalar" in section
    assert additional_or_observed_metric_values_display(run, "AUROC") == (
        "Final site metrics=NA; log/per-site evidence: site-1: round=0 train_loss=0.6275 valid_auroc=0.7049; "
        "site-2: round=0 train_loss=0.6259 valid_auroc=0.7342"
    )
    details = outcome_details_table({NO_SKILLS_MODE: run}, [NO_SKILLS_MODE])
    assert "Reported validation metric | AUROC NA" in details
    assert "log/per-site evidence" in details


def test_readme_metric_alignment_uses_server_best_validation_metric_scalar():
    from harness.quality_signals import metric_signal

    signal = metric_signal(
        None,
        "Primary validation metric: AUROC.\n",
        """
Final round metrics:
- `site-1`: valid AUROC `0.7696`, test AUROC `0.7331`
- `site-2`: valid AUROC `0.7148`, test AUROC `0.7771`
- `site-3`: valid AUROC `0.7708`, test AUROC `0.7352`
- Server best validation metric at round 2: `0.7517306189541327`
""",
    )

    metric = signal["reported_validation_metric"]
    assert signal["status"] == "pass"
    assert signal["aligned_with_readme"] is True
    assert metric["name"] == "AUROC"
    assert metric["value"] == 0.7517306189541327
    assert metric["value_scope"] == "fl_summary_metric"
    assert metric["site_value_count"] == 6
    assert metric["summary_value_label"] == "Server best validation metric at round 2"


def test_readme_metric_alignment_passes_for_site_level_values_without_scalar():
    from harness.quality_signals import metric_signal

    signal = metric_signal(
        None,
        "Primary validation metric: AUROC.\n",
        """
Final round metrics:
- `site-1`: valid AUROC `0.7696`
- `site-2`: valid AUROC `0.7148`
- `site-3`: valid AUROC `0.7708`
""",
    )

    metric = signal["reported_validation_metric"]
    assert signal["status"] == "pass"
    assert signal["aligned_with_readme"] is True
    assert signal["metric_value_available"] is True
    assert signal["metric_scalar_available"] is False
    assert signal["mismatch"] is False
    assert metric["name"] == "AUROC"
    assert metric["value"] is None
    assert metric["value_scope"] == "site_values_only"


def test_metrics_chart_names_metric_once_in_panel_title():
    from harness.modes import NO_SKILLS_MODE, WITH_SKILLS_MODE
    from harness.reports.benchmark_insights import embedded_bar_chart, outcome_metrics_table

    def run(label: str, value: float) -> dict:
        return {
            "label": label,
            "available": True,
            "status": "0",
            "run": {"elapsed_seconds": 1, "token_count": 1, "agent_exit_code": 0, "final_container_exit_code": 0},
            "activity": {"command_count": 1},
            "record": {},
            "workspace_delta": {},
            "validation_metric": {"name": "AUROC", "value": value},
        }

    chart = embedded_bar_chart(
        {
            NO_SKILLS_MODE: run("No skills baseline", 0.7562),
            WITH_SKILLS_MODE: run("With skills", 0.7529),
        }
    )
    table = outcome_metrics_table(
        {
            NO_SKILLS_MODE: run("No skills baseline", 0.7562),
            WITH_SKILLS_MODE: run("With skills", 0.7529),
        },
        [NO_SKILLS_MODE, WITH_SKILLS_MODE],
    )

    assert "Metrics (AUROC)" in chart
    assert "FL scalar result" not in chart
    assert "AUROC 0." not in chart
    assert chart.count("AUROC") == 1
    assert ">0.7529<" in chart
    assert "| Metrics (AUROC) | AUROC 0.7562 | AUROC 0.7529 |" in table
    assert "FL scalar result" not in table


def test_metrics_chart_uses_labeled_aggregated_metric_from_legacy_record():
    from harness.modes import NO_SKILLS_MODE, WITH_SKILLS_MODE
    from harness.reports.benchmark_insights import embedded_bar_chart, outcome_metrics_table

    def run(label: str, metric: dict) -> dict:
        return {
            "label": label,
            "available": True,
            "run": {"final_container_exit_code": 0},
            "activity": {},
            "validation_metric": metric,
        }

    runs = {
        NO_SKILLS_MODE: run("No skills baseline", {"name": "AUROC", "value": None, "reported_value_entries": []}),
        WITH_SKILLS_MODE: run(
            "With skills",
            {
                "name": "AUROC",
                "value": None,
                "reported_value_entries": [
                    {"value": 0.7531},
                    {"label": "Best aggregated validation AUROC", "value": 0.7623334631865992},
                    {"label": "Final site metrics", "value": 0.767293},
                ],
            },
        ),
    }

    chart = embedded_bar_chart(runs)
    table = outcome_metrics_table(runs, [NO_SKILLS_MODE, WITH_SKILLS_MODE])

    assert ">0.7623<" in chart
    assert "| Metrics (AUROC) | AUROC NA | AUROC 0.7623 |" in table


def test_metrics_chart_marks_mixed_metric_names_non_comparable():
    from harness.modes import NO_SKILLS_MODE, WITH_SKILLS_MODE
    from harness.reports.benchmark_insights import embedded_bar_chart, outcome_metrics_table

    def run(label: str, metric_name: str, value: float) -> dict:
        return {
            "label": label,
            "available": True,
            "run": {"final_container_exit_code": 0},
            "activity": {},
            "validation_metric": {"name": metric_name, "value": value},
        }

    runs = {
        NO_SKILLS_MODE: run("No skills baseline", "accuracy", 0.8123),
        WITH_SKILLS_MODE: run("With skills", "AUROC", 0.7529),
    }

    chart = embedded_bar_chart(runs)
    table = outcome_metrics_table(runs, [NO_SKILLS_MODE, WITH_SKILLS_MODE])

    assert "Metrics (mixed validation metrics)" in chart
    assert "Not comparable" in chart
    assert "No skills baseline: accuracy" in chart
    assert "With skills: AUROC" in chart
    assert "| Metrics (mixed validation metrics) | accuracy 0.8123 | AUROC 0.7529 |" in table


def test_structure_tree_renderer_uses_tree_format():
    from harness.reports.benchmark_insights import tree_from_paths

    tree = tree_from_paths(
        [
            "client.py",
            "runtime_job_config/ames_fedavg/ames_fedavg/app/config/config_fed_client.json",
            "runtime_job_config/ames_fedavg/ames_fedavg/app/custom/model.py",
        ]
    )

    assert tree.startswith(".\n")
    assert "|-- client.py" in tree
    assert "`-- runtime_job_config" in tree
    assert "        `-- ames_fedavg" in tree
    assert "- runtime_job_config/ames_fedavg" not in tree


def test_pair_summary_prints_compact_status_line(tmp_path, capsys):
    from harness.modes import NO_SKILLS_MODE, WITH_SKILLS_MODE
    from harness.reports.summaries import write_pair_summary

    for mode, elapsed in ((NO_SKILLS_MODE, 12.3), (WITH_SKILLS_MODE, 34.5)):
        mode_dir = tmp_path / mode
        mode_dir.mkdir()
        (mode_dir / "run_summary.json").write_text(
            json.dumps({"elapsed_seconds": elapsed, "all_metrics": {}}) + "\n",
            encoding="utf-8",
        )

    write_pair_summary(tmp_path, {NO_SKILLS_MODE: 0, WITH_SKILLS_MODE: 1})

    output = capsys.readouterr().out.strip()
    assert output.startswith("Pair summary written:")
    assert "without_skills: exit=0, elapsed=12.3s" in output
    assert "with_skills: exit=1, elapsed=34.5s" in output
    assert not output.startswith("{")


def test_run_summary_uses_agent_keys_without_codex_aliases(tmp_path):
    from harness.records import write_json, write_run_summary

    final_record = tmp_path / "record.json"
    summary_path = tmp_path / "run_summary.json"
    write_json(
        final_record,
        {
            "mode": "with_skills",
            "agent_process_passed": True,
            "agent_process_exit_code": 0,
            "codex_process_passed": True,
            "codex_process_exit_code": 0,
            "agent_usage": {"total_tokens": 10},
            "codex_usage": {"total_tokens": 10},
            "process_metrics": {
                "agent_exit_code": 0,
                "codex_exit_code": 0,
                "elapsed_seconds": 1,
            },
        },
    )

    write_run_summary(final_record, summary_path, print_summary=False)

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["agent_process_passed"] is True
    assert summary["agent_process_exit_code"] == 0
    assert summary["agent_exit_code"] == 0
    assert summary["agent_usage"] == {"total_tokens": 10}
    assert "codex_process_passed" not in summary
    assert "codex_process_exit_code" not in summary
    assert "codex_exit_code" not in summary
    assert "codex_usage" not in summary
    assert not any(key.startswith("codex_") for key in summary["all_metrics"])


def test_run_summary_ignores_codex_usage_fallback_and_reports_prompt_hash(tmp_path):
    from harness.records import write_json, write_run_summary

    final_record = tmp_path / "record.json"
    summary_path = tmp_path / "run_summary.json"
    write_json(
        final_record,
        {
            "mode": "with_skills",
            "codex_usage": {"total_tokens": 10},
            "process_metrics": {
                "elapsed_seconds": 3,
                "agent_elapsed_seconds": 2,
            },
        },
    )
    write_json(
        tmp_path / "prompt_metadata.json",
        {
            "prompt_sha256": "abc123",
            "template_path": "/workspace/prompts/prompt.txt",
        },
    )

    write_run_summary(final_record, summary_path, print_summary=False)

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["agent_usage"] == {}
    assert summary["agent_elapsed_seconds"] == 2
    assert summary["elapsed_seconds"] == 3
    assert summary["prompt_hash"] == "abc123"
    assert summary["prompt_source"] == "/workspace/prompts/prompt.txt"


def test_report_generators_write_two_mode_outputs(tmp_path, monkeypatch):
    from harness.modes import NO_SKILLS_MODE, WITH_SKILLS_MODE
    from harness.reports.benchmark_insights import main as insights_main
    from harness.reports.metrics_report import write_reports

    for mode, value in ((NO_SKILLS_MODE, 0.7562), (WITH_SKILLS_MODE, 0.7529)):
        mode_dir = tmp_path / mode
        records_dir = mode_dir / "records"
        records_dir.mkdir(parents=True)
        (mode_dir / "container_exit_code.json").write_text(json.dumps({"exit_code": 0}) + "\n", encoding="utf-8")
        (mode_dir / "run_summary.json").write_text(
            json.dumps(
                {
                    "mode": mode,
                    "elapsed_seconds": 10,
                    "token_count": 100,
                    "agent_exit_code": 0,
                    "final_container_exit_code": 0,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (records_dir / f"{mode}_record.json").write_text(
            json.dumps(
                {
                    "mode": mode,
                    "reported_validation_metric": {"name": "AUROC", "value": value},
                    "process_metrics": {"elapsed_seconds": 10, "token_count": 100},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (mode_dir / "agent_activity.json").write_text(json.dumps({"command_count": 3}) + "\n", encoding="utf-8")
        (mode_dir / "agent_usage.json").write_text(json.dumps({"total_tokens": 100}) + "\n", encoding="utf-8")

    write_reports(tmp_path, "Synthetic Metrics")
    monkeypatch.setattr(sys, "argv", ["benchmark_insights", str(tmp_path)])
    insights_main()

    assert (tmp_path / "metrics_report.json").is_file()
    metrics_markdown = (tmp_path / "metrics_report.md").read_text(encoding="utf-8")
    insights_markdown = (tmp_path / "benchmark_insights.md").read_text(encoding="utf-8")
    assert "<svg" in metrics_markdown
    assert "<svg" in insights_markdown
    assert "Metrics (AUROC)" in metrics_markdown
    assert "Metrics (AUROC)" in insights_markdown
    assert "Benchmark Metrics Comparison" not in insights_markdown
    assert "with_skills_eval" not in insights_markdown
    assert "Evaluator" not in insights_markdown
