# NVFLARE Agent Benchmark Harness

This directory runs agent CLIs inside clean Linux containers for the same
training-code conversion task. The migrated harness currently preserves the
Codex behavior from the original `codex_docker` harness; Claude and future agent
adapters are scaffolded but not implemented. Both skills and no-skills runtimes
install NVFLARE from locally built wheels from the same checkout. The skills
image uses a wheel that packages agent skills; the no-skills baseline uses a
matching local wheel built without packaged skills.

It does not write to your host `~/.codex/skills`.

## Build

```bash
cd path/to/NVFlare/tests/agent_benchmark
./bin/build.sh
```

The build installs a pinned Codex CLI package with npm in the pinned Node runtime
image, copies `uv` into `/usr/local/bin/uv` from the pinned `UV_IMAGE` Docker
image, creates one default
virtual environment at `/workspace/venv`, builds two NVFLARE wheels, installs
each wheel variant into that image's default venv, and builds two runtime images:

- `nvflare-agent-benchmark:codex-skills`: installs the local wheel built with
  `NVFLARE_PACKAGE_AGENT_SKILLS=1 uv build --wheel` into `/workspace/venv` and
  preinstalls Codex skills into `/workspace/.codex/skills`.
- `nvflare-agent-benchmark:codex-baseline`: installs the local wheel built with
  `NVFLARE_PACKAGE_AGENT_SKILLS=0 uv build --wheel` into `/workspace/venv`; this
  wheel has `no_skills` in its file name and skips skill installation.

The image does not bake in job-specific dependencies. Dependency installation
is measured agent behavior, not harness setup.
Build-time skill installation is expected to read skill definitions from the
installed local NVFLARE wheel. The Dockerfile records that expectation in image
metadata and writes a build-time skill-install metadata file, but it does not
prove network isolation by itself. For a hermeticity audit, run `docker build`
with controlled network/egress policy and confirm the skill-install step still
passes.

By default, `build.sh` looks for an NVFlare checkout next to this repository
(`../NVFlare`) and then under common `$HOME` locations. Override it explicitly
when needed:

```bash
NVFLARE_REPO=/path/to/NVFlare ./bin/build.sh
```

The NVFlare checkout is used only to build or select the skills and no-skills
wheels. `build.sh` is a thin wrapper around the Python build module, which
creates a temporary minimal Docker build context containing only the Dockerfile,
harness modules, and staged wheel files under `dist/`; an `NVFLARE_REPO` inside
`tests/agent_benchmark/` is rejected so the source checkout is not sent as
Docker build context.
By default the wheels are built directly into the temporary context with
`NVFLARE_PACKAGE_AGENT_SKILLS=<0|1> uv build --wheel --out-dir`. Host `uv` is
required for wheel builds; the harness does not fall back to non-uv build
commands. Existing wheels from `NVFLARE_REPO/dist` are copied only when wheel
building is skipped. Build-failure fallback is disabled by default; set
`ALLOW_EXISTING_WHEEL_FALLBACK=true` only when intentionally accepting the newest
matching existing wheel. Each staged wheel writes `nvflare_wheel_metadata.json`
with the selected filename, SHA-256, variant, package flag, build flags, and git
commit; host source paths are not copied into the image metadata.

The default build toolchain pins the Codex npm package and image tags:

- `CODEX_CLI_VERSION=0.137.0`
- `NODE_IMAGE=node:22.16.0-bookworm-slim`
- `UV_IMAGE=ghcr.io/astral-sh/uv:0.11.19`

Override these only when intentionally changing the benchmark image toolchain:

```bash
CODEX_CLI_VERSION=<version> ./bin/build.sh
NODE_IMAGE=node:<version>-bookworm-slim ./bin/build.sh
UV_IMAGE=ghcr.io/astral-sh/uv:<version> ./bin/build.sh
DOCKER_BUILD_NO_CACHE=true ./bin/build.sh
```

After rebuilding, verify the same login-shell mode used by Codex shell tools:

```bash
docker run --rm nvflare-agent-benchmark:codex-skills /bin/bash -lc 'echo "$PATH"; command -v nvflare; nvflare --version; nvflare --format json agent skills list --agent codex'
docker run --rm nvflare-agent-benchmark:codex-baseline /bin/bash -lc 'echo "$PATH"; command -v nvflare; nvflare --version; python -c "import nvflare; print(nvflare.__version__)"'
```

Debian apt packages are not exact-version pinned in the Dockerfile. The policy is
to track rebuild comparability through the pinned Node base image/build args and the
recorded image metadata (`image_build_metadata.json`), then update those inputs
deliberately when the benchmark toolchain changes.

The benchmark image intentionally does not install compiler tooling such as
`build-essential`. The harness guarantees Python, pip, uv, Codex, and the local
NVFLARE wheel; job dependency installation remains agent behavior.

The benchmark prompt is not baked into either Docker image. Runtime wrappers
mount the local `prompts/` directory so prompt edits do not require a rebuild.

## Interactive Run

```bash
cd path/to/NVFlare/tests/agent_benchmark
${EDITOR:-vi} prompts/benchmark_prompt.txt
./bin/run.sh interactive /path/to/job-folder
```

Inside the container:

```bash
python --version
python -m pip --version
pip --version
uv --version
nvflare --version
python -c "import nvflare"
/bin/bash -lc 'echo "$PATH"; command -v python; command -v nvflare; nvflare --version; python -c "import nvflare; print(nvflare.__version__)"'
/bin/bash -lc 'nvflare --format json agent skills list --agent codex'
cd /workspace/input
codex
```

## Paired Benchmark: Skills vs No Skills

Run the same Codex conversion task twice:

- `without_skills`: Codex has no NVFLARE skills installed.
- `with_skills_eval_off`: Codex uses NVFLARE skills preinstalled in the image before the benchmark starts, with `NVFLARE_SKILL_EVAL` off.

Use `process-eval` for the three-way comparison that also includes `with_skills_eval_on`.

```bash
cd path/to/NVFlare/tests/agent_benchmark
${EDITOR:-vi} prompts/benchmark_prompt.txt
./bin/run.sh pair /path/to/job-folder
```

Defaults:

- Container job folder mount: `/workspace/input`
- Prompt directory: `prompts/`, mounted into the container at `/workspace/prompts`
- Prompt file: `prompts/benchmark_prompt.txt`
- Container Codex home: `/workspace/.codex`
- Result root: `${AGENT_BENCHMARK_RESULTS_ROOT:-./results}/<timestamp>`
- Skills runtime/report image: `nvflare-agent-benchmark:codex-skills`
- Baseline runtime image: `nvflare-agent-benchmark:codex-baseline`

Run against a different job folder:

```bash
./bin/run.sh pair /path/to/job-folder
```

The explicit flag is also supported:

```bash
./bin/run.sh pair --training-code /path/to/job-folder
```

Write generated timestamped results under another parent directory:

```bash
./bin/run.sh process-eval --results-root /path/to/results /path/to/job-folder
```

Write one comparison to an exact output directory:

```bash
./bin/run.sh process-eval --output-dir /path/to/exact-run-dir /path/to/job-folder
```

To use different prompt text, edit or replace `prompts/benchmark_prompt.txt`.
The job folder is required as either a positional argument, `--training-code`,
or `JOB_INPUT_DIR`. `TRAINING_CODE` remains a backward-compatible alias only.

Override the model:

```bash
CODEX_MODEL=gpt-5.3-codex ./bin/run.sh pair /path/to/job-folder
```

`BENCHMARK_AGENT` defaults to `codex` and is recorded in run metadata. Set it
only when intentionally changing the benchmarked agent surface:

```bash
BENCHMARK_AGENT=codex CODEX_MODEL=gpt-5.3-codex ./bin/run.sh process-eval /path/to/job-folder
```

Each run writes outputs under its own result directory:

```text
${AGENT_BENCHMARK_RESULTS_ROOT:-./results}/<timestamp>/without_skills/
${AGENT_BENCHMARK_RESULTS_ROOT:-./results}/<timestamp>/with_skills_eval_off/
```

Important files:

- `run_summary.json`: runtime, token count, quality, correction count, command failures, Codex exit code, report command exit codes, and report-inclusive final container exit code.
- `timing.json`: setup, skill availability enable/disable, input copy, prompt prep, agent runtime, post-processing, and performance-report phase times.
- `agent_activity.json`: parsed agent event counts, command counts, command
  prefixes, event timeline fields, and hints for skill/reference/eval/validation
  access.
- `agent_events.jsonl`: normalized agent JSONL events enriched by the harness
  with `timestamp` and `harness_timestamp` fields as each event is received.
- `agent_usage.json`: parsed token usage from agent events.
- `agent_last_message.txt`: final agent message.
- `codex_activity.json`, `codex_events.jsonl`, `codex_usage.json`, and
  `codex_last_message.txt`: compatibility aliases for old Codex reports.
- `workspace_delta_manifest.json`: bounded final source-like file paths, dedicated final structure-file paths, changed/generated source-like files captured from the agent workspace, plus bounded runtime artifacts such as exported NVFLARE job config files.
- `workspace_delta/`: retained changed/generated files for post-run implementation review.
- `prompt.txt`: verbatim copy of the runtime-mounted prompt file used as measured agent input.
- `prompt_metadata.json`: prompt hash/byte metadata; `verbatim_copy` must be `true` for valid comparable runs.
  The runner uses `tests/agent_benchmark/prompts/benchmark_prompt.txt` as the only benchmark prompt.
  Mode names, process-record paths, and skill/case report filters are supplied by the harness, not by prompt text.
- `progress.jsonl`: benchmark progress heartbeat events printed while Codex is running.
- `runtime_image.json`: runtime image, report image, image kind, the harness process flag, NVFLARE skill-eval flag, agent, agent model, container venv/Python details, pinned Codex/Node/uv image metadata, and local NVFLARE wheel metadata used for the run.
- `image_build_metadata.json`: pinned Codex npm package, Node runtime image, uv source image, resolved tool versions, default virtual environment, apt package policy, and local-wheel skill-install expectation recorded during Docker build.
- `nvflare_wheel_metadata.json`: selected local NVFLARE wheel filename, SHA-256, variant, and build flags.
- `skills_state.json`: whether preinstalled skills were exposed or hidden for the run.
  In no-skills baseline runs, the runtime image installs the local no-skills wheel.
  The harness also clears `$CODEX_HOME/skills` defensively before Codex starts.
- `skills_build_install.json`: build-time skill install record, present only for skills-enabled runs.
- `skills_list.json`: installed skill list or baseline disabled marker.
- `process_eval_runs/<mode>_agent_record.json`: mode-specific process record synthesized by the harness from NVFLARE evaluator records when available, otherwise from agent process outcome and runtime metadata.
- `process_eval_runs/<mode>_record.json`: harness-normalized run record.
  It records timing, token, image, skill-exposure, evaluator-state metadata, and skill/case identity.
  `agent_record_source` distinguishes official evaluator records from harness outcome-proxy records.
- `early_failure.json`: present when the in-container harness fails before the normal Codex/report lifecycle can complete. The same failure is normalized into `run_summary.json` and `process_eval_runs/<mode>_record.json`.
- `late_harness_failure.json`: present when the in-container harness fails after a normalized run record already exists. The existing run evidence is preserved and annotated with `harness_error`.
- `skill_performance.json`: JSON output of `nvflare agent skills performance` for that run.
- `skill_performance.txt`: human-readable output of `nvflare agent skills performance` for that run.
- `skill_benchmark.json`: JSON output of `nvflare agent skills benchmark`.
- `skill_benchmark.md`: benchmark draft rendered by `nvflare agent skills benchmark`.
- `skill_report_filter.json`: skill/case filter used for NVFLARE reports. If unset in the environment, it is derived from the agent's process record.
- `skill_report_status.json`: in-container NVFLARE skill report exit codes and skip metadata.
- `agent_report_exit_codes.json`: normalized in-container skill report command exit codes. The same statuses are copied into `run_summary.json` and the final process record; nonzero values make the measured container exit nonzero when Codex itself succeeded.
- `host_report_exit_codes.json`: baseline host-wrapper skill report command exit codes, present when host-side reports are run for a no-skills case.
- `pair_summary.json`: side-by-side comparison.

The paired runner also writes combined NVFLARE reports at the timestamped result
root:

- `console_output.log`: host-side screen output from the paired runner, including progress heartbeat lines.
- `process_eval_runs/`: copies of both final process records.
- `skill_report_filter.json`: combined report skill/case filter derived from agent or evaluator records.
- `skill_performance.json` and `skill_performance.txt`: combined performance across `without_skill` and `with_skill`.
- `skill_benchmark.json` and `skill_benchmark.md`: combined benchmark draft.
- `host_report_status.json`: host-side skill report and report-generator exit codes, grouped by command family.
- `report_generator_status.json`: host-side metrics/benchmark-insights report generator exit codes only.
- `metrics_summary.json`: normalized raw metrics plus deduped per-run metrics, per-case metadata, instruction-following rows, explicit instruction issue counts when measurable, best-effort behavior-status analysis, event counts, phase timing, and token-spend analysis.
- `metrics_report.html`: browser-friendly summary analysis, instruction-following details, and deduped metric bars.
- `comprehensive_report.json`: combined console log plus JSON/JSONL/text/Markdown artifact contents.
- `comprehensive_report.md`: readable run summary, summary analysis, instruction compliance, deduped metrics table, and artifact index.
  The ablation runner also writes `benchmark_insights.md`, an insight-focused Markdown report with embedded metric bars, evaluator-metric availability, structure comparison, plain-language comparisons, activity interpretation, and quality caveats.
  Standalone plot files such as `metrics_plots.svg`, `metrics_plots.png`, and
  `metrics_report.pdf` are not generated by default; run
  `generate_metrics_report.py --plot-files ...` only when those extra artifacts are needed.

The default progress heartbeat interval is 60 seconds. Override it with:

```bash
PROGRESS_INTERVAL_SECONDS=120 ./bin/run.sh pair /path/to/job-folder
```

The NVFLARE performance and benchmark commands summarize process records
written by the agent or evaluator. The selected skill is discovered from those
records; the wrapper does not pin a skill name.

## Harness Structure

`run.sh` and `build.sh` are thin public shell entrypoints. They dispatch to
Python modules for one-case runs, pair runs, skill-eval ablations, interactive
containers, and Docker image builds. Benchmark data semantics live under
`harness/`:

- `harness/artifacts.py`: workspace baselines, generated-file capture, bounded artifact collection.
- `harness/case_metadata.py`: shared benchmark case metadata extraction for algorithm, client count, round count, job name, and model.
- `harness/events.py`: Codex JSONL usage and activity parsing.
- `harness/container/agent_run.py`: Docker-internal Codex lifecycle runner.
- `harness/host/build.py`: host-side NVFLARE wheel staging and Docker image build orchestration.
- `harness/host/common.py`: host-side argument, Docker, path, and logging helpers.
- `harness/host/reports.py`: host-side NVFLARE skill report generation.
- `harness/host/runner.py`: host-side benchmark orchestration CLI.
- `harness/records.py`: process-record synthesis, normalization, and run-summary CLI.
- `harness/reports/reporting.py`: report filter discovery, evaluator-backed detection, and report status JSON.
- `harness/timing.py`: timing finalization for records and summaries.
- `harness/reports/summaries.py`: pair and skill-eval summary JSON.
- `harness/modes.py`: shared mode definitions.
- `harness/quality_signals.py`: README/final-message validation metric signals used for analysis, not evaluator pass/fail.

The Docker build context is generated under a temporary directory from the
Dockerfile, staged wheels, `build_context.dockerignore`, and an explicit
allowlist of container runtime harness modules. Host-only modules such as
`host_build.py`, `host_common.py`, `host_runner.py`, and `host_reports.py` are
not copied into runtime images.

## Skill-Evaluation Ablation

To compare a no-skills baseline against skills-enabled runs with evaluator off
and on, run the three-case ablation:

```bash
./bin/run.sh process-eval /path/to/job-folder
```

The behavior switch for evaluator-on/off is `NVFLARE_SKILL_EVAL`. The
`PROCESS_EVAL` value is retained as a harness metadata flag in result records.
It runs:

- `without_skills`: no skills; evaluator off because there is no skill to evaluate
- `with_skills_eval_off`: skills enabled; evaluator off
- `with_skills_eval_on`: skills enabled; evaluator on

The three cases always run sequentially so runtime and token comparisons are
not distorted by parallel Docker/Codex resource contention.

The job input must be an existing folder containing the scientist's scripts,
data, README, and related files:

```bash
./bin/run.sh process-eval /path/to/job-folder
./bin/run.sh process-eval --training-code /path/to/job-folder
```

The output `process_eval_ablation_summary.json` separates:

- NVFLARE skill-eval overhead with skills
- skills overhead when NVFLARE skill eval is off
- skills plus evaluator overhead against the no-skills baseline

The ablation runner also writes `console_output.log`, `metrics_summary.json`,
`metrics_report.html`, `benchmark_insights.md`, `comprehensive_report.json`, and
`comprehensive_report.md` at its result root. `benchmark_insights.md` includes an
embedded bar chart, so no separate SVG/PNG/PDF plot report is needed.
It also writes per-case console logs such as `without_skills.console.log`.
Those reports include an evaluation-mode table and a matrix showing whether
the no-skills baseline plus skills evaluator off/on cases are present.

`with-skills` is a single-run shortcut for the eval-off skills case:

```bash
./bin/run.sh with-skills /path/to/job-folder
```

Use the explicit eval-on shortcut to enable NVFLARE skill-eval behavior for a
skills-enabled single run:

```bash
./bin/run.sh with-skills-eval-on /path/to/job-folder
```

To run one benchmark directly, choose a known `MODE`. The harness derives skill
exposure, process metadata, and NVFLARE skill-eval state from that mode and
rejects contradictory environment overrides:

```bash
MODE=with_skills_eval_off ./bin/run.sh one /path/to/job-folder
MODE=with_skills_eval_on ./bin/run.sh one /path/to/job-folder
MODE=without_skills ./bin/run.sh one /path/to/job-folder
```

## Authentication

Default authentication reuses the host Codex login by mounting:

- `~/.codex/auth.json`
- `~/.codex/config.toml`

Those files are mounted read-only. Disable this behavior with:

```bash
MOUNT_HOST_CODEX_AUTH=false ./bin/run.sh pair /path/to/job-folder
```

The wrappers default to `$HOME/.codex` and also expand a literal `~` in
`HOST_CODEX_HOME`, so macOS paths such as `HOST_CODEX_HOME="~/.codex"` resolve
to `/Users/<you>/.codex`. The run logs print whether each auth file was actually
mounted.

You can also pass an API key explicitly:

```bash
OPENAI_API_KEY="$OPENAI_API_KEY" ./bin/run.sh pair /path/to/job-folder
```

## Output Format

Benchmark summaries remain JSON. NVFLARE skill performance is written both as
JSON and as the human-readable output from `nvflare agent skills performance`.
The benchmark draft is written as Markdown by `nvflare agent skills benchmark`.
Free-form agent artifacts such as `prompt.txt`, `agent_stderr.txt`, and
`agent_last_message.txt` remain text files. Codex compatibility aliases are
written for old report readers.

## Slowdown Analysis

Do not optimize the skills from runtime or token numbers alone. First compare:

- `phase_seconds.agent_runtime`: actual Codex execution time, excluding setup before Codex starts.
- `phase_seconds.setup_before_agent`: Docker/setup time before Codex starts.
- `activity.command_count` and `activity.command_prefix_counts`: whether the skills run used more shell commands.
- `activity.hint_counts.skill_md`, `skill_references`, `skill_evals`, and `benchmark_md`: whether the agent spent extra work reading skill docs or evaluation files.
- `activity.hint_counts.python_job_py`, `py_compile`, and `simulation`: whether extra time went into useful validation.

The harness copies the mounted prompt file and does not append mode, path,
skill, or evaluator instructions to the measured prompt. Evaluator overhead should come only from the controlled
runtime/skill environment, not from prompt differences. Wrapper-side parsing and
NVFLARE reporting commands are measured separately in `phase_seconds.post_process`
and `phase_seconds.skill_reports`; these should be small compared with
`agent_runtime`. Skill installation is not part of benchmark runtime; skills are
installed during Docker image build. The baseline run uses the local no-skills
wheel and clears `$CODEX_HOME/skills` before Codex starts.

Instruction missing/failure counts are only authoritative when the evaluator or
skill emits explicit metrics such as `missing_instruction_count`. If those
metrics are absent, the report marks the count as `n/a` / `unable_to_measure`.
The required fail/missing/issue columns remain visible as best-effort
post-analysis from behavior statuses, but they should not be treated as exact
measurement.

## Notes on Token Count

The benchmark parses token totals from `codex exec --json` events. If the CLI output format does not include token usage, `token_count` will be `null`. Runtime is always measured by the wrapper script.
