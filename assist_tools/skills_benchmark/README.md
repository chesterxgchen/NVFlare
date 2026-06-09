# NVFLARE Agent Benchmark Harness

This harness runs agent CLIs in Docker and compares the same unstructured
NVFLARE job-conversion task with and without packaged NVFLARE agent skills.

Current runnable scope:

- Agents: Codex and Claude. Claude requires an explicit `CLAUDE_MODEL` or
  `BENCHMARK_AGENT_MODEL`.
- Modes: `without_skills` and `with_skills`.
- Job input: a folder containing scripts, data, docs, and any local
  requirements files.
- Prompt input: a local prompt file for direct runs, or a scenario prompt file/template.
- Scenario input: optional YAML compiled into `scenario.json` and
  `run_plan.json`.
- Results: written under `assist_tools/skills_benchmark/results/` by default.

There is no runtime evaluator mode. The harness measures what the agent does
and reports normalized evidence from the run.

## Quick Start

From the NVFLARE checkout:

```bash
cd assist_tools/skills_benchmark
./bin/build.sh
./bin/run.sh pair --prompt /path/to/prompt.txt /path/to/job-folder
```

The paired run creates a timestamped result directory:

```text
results/<timestamp>/
|-- scenario.json
|-- run_plan.json
|-- scenario_summary.json
|-- reports/
|   |-- scenario_report.json
|   `-- scenario_report.md
|-- records/
|   `-- agent=.../model=.../workflow=.../job=.../repeat=01/mode=.../
```

Read `reports/scenario_report.md` first. It summarizes scenario status,
aggregate timing, quality-gate results, and the selected winner policy.

## Prerequisites

Install or configure these on the host:

- Docker.
- Python 3.
- `uv`, unless using existing local NVFLARE wheels.
- Codex authentication through `~/.codex/auth.json` and
  `~/.codex/config.toml`, or `OPENAI_API_KEY`.

By default, the harness mounts Codex auth/config files read-only into the
container. To use an API key instead:

```bash
OPENAI_API_KEY="$OPENAI_API_KEY" \
  ./bin/run.sh pair --prompt /path/to/prompt.txt /path/to/job-folder
```

To disable host Codex auth mounting:

```bash
MOUNT_HOST_CODEX_AUTH=false \
  ./bin/run.sh pair --prompt /path/to/prompt.txt /path/to/job-folder
```

## Build Images

Build the two Docker images:

```bash
cd assist_tools/skills_benchmark
./bin/build.sh
```

The build creates:

- `nvflare-agent-benchmark:codex-baseline`
- `nvflare-agent-benchmark:codex-skills`

Select another supported agent at build time:

```bash
BENCHMARK_AGENT=claude ./bin/build.sh
```

Both images install NVFLARE from local wheels built from the checkout. The
baseline image builds with packaged agent skills disabled. The skills image
builds with packaged agent skills enabled.

If the checkout is not auto-detected:

```bash
NVFLARE_REPO=/path/to/NVFlare ./bin/build.sh
```

Useful build overrides:

```bash
BUILD_NVFLARE_WHEEL=false ./bin/build.sh
ALLOW_EXISTING_WHEEL_FALLBACK=true ./bin/build.sh
DOCKER_BUILD_NO_CACHE=true ./bin/build.sh
CODEX_CLI_VERSION=0.137.0 ./bin/build.sh
CLAUDE_CLI_VERSION=latest ./bin/build.sh
NODE_IMAGE=node:22.16.0-bookworm-slim ./bin/build.sh
UV_IMAGE=ghcr.io/astral-sh/uv:0.11.19 ./bin/build.sh
```

Build only one image when iterating:

```bash
BUILD_BASELINE_IMAGE=false ./bin/build.sh
BUILD_SKILLS_IMAGE=false ./bin/build.sh
```

Verify the images exist:

```bash
docker image ls 'nvflare-agent-benchmark'
```

Verify NVFLARE and packaged skills in the skills image:

```bash
docker run --rm nvflare-agent-benchmark:codex-skills \
  /bin/bash -lc 'nvflare --version; nvflare --format json agent skills list --agent codex'
```

The images do not install job-specific training dependencies. Installing
requirements from the job folder is part of the measured agent behavior.

## Prompt Inputs

The prompt is not committed to git and is not baked into Docker images. Pass it
at run time for direct `pair`, `one`, and `interactive` runs:

```bash
./bin/run.sh pair --prompt ./prompt.txt /path/to/job-folder
```

Inside the container:

- The job folder is mounted read-only at `/workspace/input`.
- The prompt file is mounted read-only at
  `/workspace/prompts/benchmark_prompt.txt`.
- The result directory is mounted at `/workspace/results`.

The harness copies the prompt verbatim. It does not append mode names, workflow
instructions, record paths, or skill instructions. The prompt should describe
the conversion task and ask the agent to report final artifacts, validation
steps, and any validation metric requested by the job documentation.

Scenario YAML may also use prompt templates:

```yaml
prompt:
  path: prompt_template.txt
  variables:
    job_name: ames
```

Only explicitly declared scalar variables are substituted. Missing variables,
unused variables, attribute/index access, and format conversions fail scenario
validation. Template variables do not authorize hidden mode, workflow, metric,
record-path, or skill-hint injection. Compared mode legs receive identical
rendered prompt bytes, and rendered prompts are materialized under the result
root, not in the scenario source directory.

Example prompt:

```text
Convert the training job in /workspace/input into an exportable NVFLARE job.
Use the workflow requested by the job documentation when it is clear.
Install job dependencies from requirements files when needed.
Run cheap validation before full simulation, then report final artifact paths
and validation metrics.
```

## Run A Pair

Run both modes sequentially:

```bash
./bin/run.sh pair --prompt ./prompt.txt /path/to/job-folder
```

Equivalent explicit job-folder option:

```bash
./bin/run.sh pair --prompt ./prompt.txt --training-code /path/to/job-folder
```

Set the parent directory for timestamped results:

```bash
./bin/run.sh pair \
  --prompt ./prompt.txt \
  --results-root /path/to/results \
  /path/to/job-folder
```

Write a comparison to an exact directory:

```bash
./bin/run.sh pair \
  --prompt ./prompt.txt \
  --output-dir /path/to/exact-result-dir \
  /path/to/job-folder
```

Select a Codex model:

```bash
CODEX_MODEL=<model-name> \
  ./bin/run.sh pair --prompt ./prompt.txt /path/to/job-folder
```

Select Claude:

```bash
BENCHMARK_AGENT=claude CLAUDE_MODEL=<model-name> \
  ./bin/run.sh pair --prompt ./prompt.txt /path/to/job-folder
```

`BENCHMARK_AGENT` defaults to `codex`. Known but unimplemented agents such as
Hermes and OpenClaw fail during build/run preflight.

`pair` is a shortcut over the scenario/run-plan execution path. It writes the
same canonical scenario records as `scenario`.

## Run A Scenario

Scenario YAML files describe agents, models, workflows, jobs, comparison type,
and repeat count. The harness compiles them into `scenario.json` and
`run_plan.json` before Docker execution:

```bash
./bin/run.sh scenario /path/to/scenario.yaml --output-dir /path/to/result-root
```

Runnable starting points are in `examples/` (`mode_ablation.yaml`,
`model_comparison.yaml`). Edit the `prompt` and `jobs[].path` values, then:

```bash
./bin/run.sh scenario examples/mode_ablation.yaml --output-dir /path/to/result-root
```

The scenario command writes:

```text
result-root/
|-- scenario.json
|-- run_plan.json
|-- scenario_summary.json
|-- reports/
|   |-- scenario_report.json
|   `-- scenario_report.md
`-- records/
    `-- agent=<agent>/model=<model>/workflow=<workflow>/job=<job>/repeat=<NN>/mode=<mode>/
```

Each mode directory contains direct canonical artifacts such as
`record_summary.json`, `agent_events.jsonl`, `agent_usage.json`,
`agent_activity.json`, `agent_last_message.txt`, `agent_stderr.txt`,
`agent_record.json`, and `benchmark_record.json`.

## Replay Captured Results

Use `replay` to regenerate parser artifacts, repeat summaries, scenario
summaries, and scenario reports from an existing result root without invoking a
live agent or Docker:

```bash
./bin/run.sh replay /path/to/result-root
```

Replay requires a `run_plan.json` in the result root and captured
`agent_events.jsonl` files under the canonical records tree.

## Run One Mode

Use the shortcuts:

```bash
./bin/run.sh without-skills --prompt ./prompt.txt /path/to/job-folder
./bin/run.sh with-skills --prompt ./prompt.txt /path/to/job-folder
```

Or use `one` with `MODE`:

```bash
MODE=without_skills ./bin/run.sh one --prompt ./prompt.txt /path/to/job-folder
MODE=with_skills ./bin/run.sh one --prompt ./prompt.txt /path/to/job-folder
```

For a single run, `--output-dir` maps to the exact mode result directory:

```bash
MODE=with_skills \
  ./bin/run.sh one \
  --prompt ./prompt.txt \
  --output-dir /path/to/exact-mode-result \
  /path/to/job-folder
```

The harness derives skill exposure from `MODE` and rejects contradictory
`USE_PREINSTALLED_SKILLS` overrides.

## Interactive Container

Use `interactive` to inspect the runtime image, auth mounts, or job input:

```bash
./bin/run.sh interactive --prompt ./prompt.txt /path/to/job-folder
```

Useful checks inside the container:

```bash
python --version
uv --version
nvflare --version
nvflare --format json agent skills list --agent codex
ls -la /workspace/input
ls -la /workspace/prompts
```

## Result Layout

Each scenario mode directory contains the normalized run artifacts:

```text
records/agent=<agent>/model=<model>/workflow=<workflow>/job=<job>/repeat=01/mode=with_skills/
|-- agent_activity.json
|-- agent_events.jsonl
|-- agent_record.json
|-- agent_last_message.txt
|-- agent_stderr.txt
|-- agent_usage.json
|-- benchmark_record.json
|-- container_exit_code.json
|-- prompt.txt
|-- prompt_metadata.json
|-- records/
|   |-- with_skills_agent_record.json
|   `-- with_skills_record.json
|-- record_summary.json
|-- run_summary.json
|-- timing.json
|-- workspace_delta/
`-- workspace_delta_manifest.json
```

`without_skills` has the same shape with `without_skills` record names.

The paired result root contains canonical scenario files:

```text
results/<timestamp>/
|-- console_output.log
|-- host_report_status.json
|-- scenario.json
|-- run_plan.json
|-- scenario_summary.json
|-- reports/
|   |-- scenario_report.json
|   `-- scenario_report.md
`-- records/
```

For Codex compatibility, the harness also writes aliases such as
`codex_events.jsonl`, `codex_usage.json`, and `codex_last_message.txt`.

## Reading Results

Start with these files:

- `reports/scenario_report.md`: human-readable scenario status, aggregate
  results, quality-gate status, and winner policy.
- `scenario_summary.json`: machine-readable scenario, comparison, and aggregate
  summaries.
- `records/.../mode=<mode>/record_summary.json`: normalized per-run metrics,
  exit codes, prompt hash, and quality signals.
- `records/.../mode=<mode>/agent_last_message.txt`: final agent response.
- `records/.../mode=<mode>/agent_stderr.txt`: agent stderr.
- `records/.../mode=<mode>/workspace_delta/`: generated files retained for
  review.
- `console_output.log`: complete host-side console log for paired runs.

When a case fails, look for:

- `records/.../mode=<mode>/early_failure.json`
- `records/.../mode=<mode>/late_harness_failure.json`
- `records/.../mode=<mode>/container_exit_code.json`
- `records/.../mode=<mode>/agent_stderr.txt`
- `records/.../mode=<mode>/agent_last_message.txt`

## Environment Reference

| Variable | Purpose |
| --- | --- |
| `AGENT_BENCHMARK_RESULTS_ROOT` | Parent directory for timestamped results. Defaults to `./results`. |
| `CODEX_DOCKER_RESULTS_ROOT` | Compatibility alias used only when `AGENT_BENCHMARK_RESULTS_ROOT` is unset. |
| `CODEX_MODEL` | Codex model name passed to `codex exec`. |
| `CLAUDE_MODEL` | Claude model name passed to Claude Code. Required for Claude runs unless `BENCHMARK_AGENT_MODEL` is set. |
| `BENCHMARK_AGENT_MODEL` | Agent-neutral model override used by scenario and direct runs. |
| `BENCHMARK_AGENT` | Agent name. Supported values are `codex` and `claude`; unsupported values fail early. |
| `BENCHMARK_JOB_SCALE` | Job scale used by `pair` compatibility scenarios. Defaults to `small`. |
| `OPENAI_API_KEY` | Optional API key passed through to the container. |
| `ANTHROPIC_API_KEY` | Optional Anthropic API key passed through to the container. |
| `ANTHROPIC_AUTH_TOKEN` | Optional Anthropic auth token passed through to the container. |
| `HOST_CODEX_HOME` | Host Codex config directory. Defaults to `~/.codex`. |
| `MOUNT_HOST_CODEX_AUTH` | Mount host Codex auth/config files. Defaults to `true`. |
| `HOST_CLAUDE_HOME` | Host Claude config directory. Defaults to `~/.claude`. |
| `MOUNT_HOST_CLAUDE_AUTH` | Mount host Claude auth/config files. Defaults to `true`. |
| `NVFLARE_REPO` | Checkout used for local wheel builds. |
| `IMAGE_NAME` | Override skills runtime image. |
| `BASELINE_IMAGE_NAME` | Override baseline runtime image. |
| `REPORT_IMAGE_NAME` | Override report image. Defaults to the skills image. |
| `PROGRESS_INTERVAL_SECONDS` | Agent progress heartbeat interval. Defaults to `60`. |
| `MODE` | Single-run mode: `with_skills` or `without_skills`. |
| `JOB_INPUT_DIR` | Job folder fallback when no CLI path is provided. |
| `TRAINING_CODE` | Compatibility alias for `JOB_INPUT_DIR`. |
| `RESULT_ROOT` | Exact pair output directory fallback when `--output-dir` is not provided. |
| `RESULT_DIR` | Exact single-run output directory fallback when `--output-dir` is not provided. |
| `BUILD_NVFLARE_WHEEL` | Build local wheels during `build.sh`. Defaults to `true`. |
| `ALLOW_EXISTING_WHEEL_FALLBACK` | Use existing local matching wheels if build fails. Defaults to `false`. |
| `BUILD_SKILLS_IMAGE` | Build the skills image. Defaults to `true`. |
| `BUILD_BASELINE_IMAGE` | Build the baseline image. Defaults to `true`. |
| `DOCKER_BUILD_NO_CACHE` | Pass `--no-cache` to `docker build`. Defaults to `false`. |
| `CODEX_CLI_VERSION` | Codex CLI npm package version installed in the image. |
| `CLAUDE_CLI_VERSION` | Claude Code npm package version installed in the image. |
| `NODE_IMAGE` | Base Node image build arg. |
| `UV_IMAGE` | Base uv image build arg. |

## Troubleshooting

Missing Docker images:

```text
Benchmark Docker image(s) are missing locally
```

Run:

```bash
./bin/build.sh
docker image ls 'nvflare-agent-benchmark'
```

Prompt missing:

```text
Prompt file is required
```

Create a local prompt file and pass `--prompt /path/to/prompt.txt`. The harness
does not use a repository prompt by default.

Unsupported model:

```text
The '<model>' model is not supported
```

Set `CODEX_MODEL` to a model available to the account used by Codex.

Auth missing:

```text
Codex auth not mounted
Codex config not mounted
```

Check `HOST_CODEX_HOME`, `~/.codex/auth.json`, and `~/.codex/config.toml`, or
pass `OPENAI_API_KEY`. Use `interactive` to inspect the container environment.

No report generated:

Check these files in the result root:

- `host_report_status.json`
- `console_output.log`

No validation metric in reports:

The report extracts metrics from agent evidence. If the agent final message or
record does not expose the requested scalar metric, the report shows `NA`
instead of inventing a value.

Slow skills run:

Compare `phase_seconds.agent_elapsed_seconds`, `activity.command_count`,
`activity.command_prefix_counts`, and `activity.hint_counts` in each
`run_summary.json`. Skill installation happens at image-build time, not during
the measured agent run.

Job dependency failure:

Inspect `records/.../mode=<mode>/agent_last_message.txt`,
`records/.../mode=<mode>/agent_stderr.txt`, and
`records/.../mode=<mode>/workspace_delta/`. The prompt should instruct the
agent to install job dependencies from available requirements files when needed.

## Harness Modules

- `bin/build.sh`: thin wrapper around `harness.host.build`.
- `bin/run.sh`: thin wrapper around `harness.host.runner`.
- `docker/Dockerfile`: runtime image with Codex and NVFLARE wheels.
- `harness/scenarios.py`: scenario validation, run-plan expansion, repeat
  aggregation, and scenario reports.
- `harness/host/`: Docker orchestration, path handling, image selection, and
  scenario execution.
- `harness/container/`: in-container agent execution and artifact capture.
- `harness/artifacts.py`, `events.py`, `records.py`, `timing.py`, and
  `quality_signals.py`: normalized measurement semantics.
- `harness/reports/`: scenario report helpers and structure rendering.

## Current Limits

- Codex and Claude adapters are implemented. Hermes and OpenClaw are registered
  as known-pending adapters.
- The harness does not require or validate a structured job schema.
- The harness does not infer a framework or workflow from the job folder. The
  prompt and job documentation define the requested task.
