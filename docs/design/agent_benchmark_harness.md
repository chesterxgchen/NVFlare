# Agent Benchmark Harness Architecture

This document defines the intended architecture for the NVFLARE agent benchmark
harness. The harness measures how agent-accessible NVFLARE skills affect applied
conversion and diagnosis tasks. It is benchmark infrastructure, not product API.

The benchmark input is intentionally loose: a job is a folder containing scripts,
data, configuration, and human documentation. The harness must not require a job
schema or perform the agent's conversion work. The harness supplies a prompt and
execution environment, then measures the agent's behavior and produced
artifacts.

The architecture supports multiple agents through adapters. Codex is the
supported adapter until another agent has a defined CLI, auth, event, usage, and
final-message contract. Unsupported agents fail during preflight.

## System Boundary

The benchmark system has five external inputs:

- a job folder;
- a prompt file or rendered prompt;
- a scenario definition or direct run arguments;
- an agent and model selection;
- a skill-exposure mode.

It produces one result tree containing normalized agent artifacts, records,
workspace-delta manifests, metrics, and reports.

The harness compares skill exposure, not evaluator behavior. The only benchmark
modes are:

```text
without_skills
with_skills
```

There is no evaluator axis, no `eval=on` mode, and no runtime skill evaluator in
the benchmark architecture. Correctness and quality are derived from measured
agent output, generated artifacts, validation evidence, source immutability, and
failure analysis.

## Architecture Overview

```text
CLI / Scenario
    |
    v
Host runner and scenario expander
    |
    | builds/selects images, validates inputs, mounts job/prompt/results
    v
Docker runtime
    |
    v
Container lifecycle coordinator
    |
    | prepares prompt, skill exposure, environment, progress, timing
    v
Agent adapter
    |
    | invokes agent CLI and normalizes agent-specific events
    v
Artifact, record, and report pipeline
```

The host side owns Docker orchestration and run planning. The container side owns
the ordered lifecycle of one benchmark run. Agent adapters own only
agent-specific invocation and parsing. Measurement semantics live in shared
artifact, record, event, timing, quality-signal, and report modules.

## Repository Layout

The benchmark harness lives under `tests/agent_benchmark/`:

```text
tests/agent_benchmark/
|-- README.md
|-- bin/
|   |-- build.sh
|   `-- run.sh
|-- docker/
|   |-- Dockerfile
|   `-- build_context.dockerignore
|-- harness/
|   |-- __init__.py
|   |-- common.py
|   |-- modes.py
|   |-- artifacts.py
|   |-- events.py
|   |-- quality_signals.py
|   |-- case_metadata.py
|   |-- scenarios.py
|   |-- timing.py
|   |-- records.py
|   |-- record_identity.py
|   |-- host/
|   |   |-- build.py
|   |   |-- common.py
|   |   `-- runner.py
|   |-- container/
|   |   |-- agent_run.py
|   |   |-- progress.py
|   |   `-- skills.py
|   |-- agents/
|   |   |-- base.py
|   |   |-- codex.py
|   |   `-- claude.py
|   `-- reports/
|       |-- benchmark_insights.py
|       |-- metrics_report.py
|       |-- summaries.py
|       `-- structure_tree.py
|-- scenarios/
|   |-- ci_smoke.yaml
|   |-- codex_models.yaml
|   |-- multi_agent.yaml
|   |-- workflows.yaml
|   `-- jobs.yaml
`-- fixtures/
    |-- jobs/
    |-- events/
    |-- records/
    `-- README.md
```

This location keeps the harness close to test infrastructure while keeping it
outside `nvflare/` product packages. Unit tests for the harness live under
`tests/unit_test/agent_benchmark/`. Integration tests that validate Docker
execution live under `tests/integration_test/agent_benchmark/`.

`docs/design/agent_benchmark_harness.md` is the architecture document. The
harness-local README explains how to build and run the tool.

## Component Ownership

### CLI Wrappers

`bin/build.sh` and `bin/run.sh` are thin entry points. They translate shell usage
into Python module invocations and do not own benchmark semantics.

### Host Runner

`harness/host/` owns host-side orchestration:

- direct CLI argument parsing;
- scenario file loading and run-plan expansion;
- preflight validation;
- Docker image selection and build invocation;
- explicit Docker context and mount construction;
- result-root creation;
- sequential execution of run-plan entries;
- host-side report orchestration.

The host runner does not parse agent event streams, infer task success from raw
logs, derive skill identity from workflow names, or mutate job input folders.

### Scenario Engine

`harness/scenarios.py` owns scenario parsing, validation, and expansion. A
scenario expands into a concrete `run_plan.json` before the first Docker run
starts. The run plan is the source of truth for execution order and comparison
grouping.

Preflight validation covers:

- supported agent names;
- unambiguous agent/model selection;
- valid comparison type and mode names;
- job paths that exist and are directories;
- prompt path existence or renderability;
- Docker image availability or build inputs;
- explicit Docker context allowlisting;
- estimated run count and result-tree size.

Execution is sequential by default. Parallelism is a separate scenario field and
must be explicit because concurrent agent runs affect timing, resource
contention, and result interpretation.

### Docker Build And Runtime

The Docker layer provides isolated, repeatable execution. The local NVFLARE
checkout is build input only. Runtime images receive NVFLARE through built
wheels and explicit metadata, not by copying the working tree into the image.

Image identity is resolved from `(agent, variant)`:

```text
nvflare-agent-benchmark:<agent>-baseline
nvflare-agent-benchmark:<agent>-skills
```

The builder creates two NVFLARE wheels per source checkout:

```text
skills wheel     NVFLARE_PACKAGE_AGENT_SKILLS=1
baseline wheel   NVFLARE_PACKAGE_AGENT_SKILLS=0
```

Those wheels are reused across agent images. Agent-specific Docker stages own
agent CLI installation, auth-home defaults, and native dependencies.

### Container Lifecycle Coordinator

`harness/container/agent_run.py` owns the lifecycle of one run inside the
container:

- validate mounted input, prompt, and result directories;
- prepare the container-local workspace;
- expose or hide packaged NVFLARE skills according to mode;
- copy prompt metadata into the record directory;
- establish workspace baselines for delta capture;
- invoke the selected agent adapter;
- preserve agent stdout, stderr, events, and final message;
- synthesize fallback records on failure;
- run artifact capture and report commands;
- write final run status.

The lifecycle coordinator does not own agent-specific command construction or
raw event parsing. It also does not own report meaning, quality-gate policy,
skill identity trust decisions, or timing semantics beyond calling the timing
module at defined lifecycle boundaries.

### Agent Adapters

An agent adapter owns the agent-specific mechanics required to run and parse one
agent surface:

```python
class AgentAdapter:
    name: str

    def model_from_env(self, env: Mapping[str, str]) -> str: ...
    def auth_mounts(self, host_config) -> list[DockerMount]: ...
    def runtime_env(self, config) -> dict[str, str]: ...
    def command(self, config) -> list[str]: ...
    def parse_usage(self, events_path: Path) -> dict: ...
    def parse_activity(self, events_path: Path) -> dict: ...
    def final_message_path(self, result_dir: Path) -> Path: ...
    def metadata(self) -> dict: ...
```

Adapters may expose observations such as model name, CLI version, raw usage,
raw activity, and agent-reported skill identity. They must not decide benchmark
meaning. Timing boundaries, workspace artifacts, process records, report
filters, source immutability policy, pass/fail normalization, and failure-root
classification belong to the coordinator, record layer, and report layer.

Event normalization is agent-specific but emits an agent-neutral event schema:

```python
normalize_agent_event(agent: str, raw_line: str) -> dict | None
```

`harness/events.py` owns neutral event helpers and common counters.
`harness/agents/<agent>.py` owns raw event normalization, usage parsing,
activity parsing, final-message discovery, and CLI metadata for that agent.

### Codex Adapter

The Codex adapter defines:

- CLI command: `codex exec --json ...`;
- model environment variable: `CODEX_MODEL`;
- auth/config mounts: `CODEX_HOME`, host `.codex/auth.json`, and
  `.codex/config.toml`;
- JSONL event normalization;
- cumulative token usage parsing;
- final message path for `--output-last-message`.

### Non-Codex Adapters

A non-Codex adapter is supported only when these contracts are known:

- installation and version pinning;
- auth and config mount locations;
- model selection;
- structured event availability;
- final assistant response source;
- token usage source;
- tool-call and shell-command representation;
- exit-code semantics.

If an agent does not expose Codex-like structured events, its adapter still
emits the neutral event contract with lower-fidelity activity fields and parser
warnings in `agent_usage.json` or `agent_activity.json`.

### Artifact Layer

`harness/artifacts.py` owns bounded artifact capture:

- workspace baseline manifests;
- post-run workspace delta manifests;
- source-input immutability checks;
- generated-file structure summaries;
- safe references to large or sensitive artifacts.

The artifact layer records what changed. It does not decide whether a change is
scientifically correct or whether the agent chose the right workflow.

### Record Layer

`harness/records.py` owns normalized records. Records combine:

- run identity;
- agent identity;
- mode and skill exposure;
- Docker image and wheel metadata;
- timing;
- token and activity counters;
- final agent message references;
- process metrics;
- validation metrics extracted from generated output;
- quality-signal observations;
- failure-root classification.

Records are generated from observed artifacts. They do not depend on a runtime
evaluator record, evaluator pass/fail, or evaluator score.

### Report Layer

`harness/reports/` owns report generation. Reports consume normalized records,
run summaries, scenario metadata, and artifact manifests. They do not parse raw
agent logs when a normalized source exists.

Reports show:

- scenario and comparison identity;
- agent, model, mode, image, and wheel variant;
- human-readable run status;
- failure analysis and likely root cause for failed runs;
- scalar validation metrics when extractable;
- source immutability and structure checks;
- token, command, timing, and cost-related measurements;
- comparison summaries across modes, agents, models, workflows, jobs, and
  repeats.

Metric sections should be named by metric family, for example
`Metrics (AUROC)` or `Metrics (valid_loss)`. Plot legends should identify the
compared run leg rather than repeating the metric name in every bar label.

## Mode Model

Modes describe skill exposure only:

```text
without_skills
with_skills
```

Agent selection is orthogonal:

```text
agent = codex | claude | ...
mode = without_skills | with_skills
job = /path/to/job-folder
```

This supports comparisons such as:

```text
codex / without_skills
codex / with_skills
claude / without_skills
claude / with_skills
```

The architecture has no `with_skills_eval_on`, `with_skills_eval_off`,
`PROCESS_EVAL`, `NVFLARE_SKILL_EVAL`, or skill-evaluator mode.

## Scenario Model

A scenario defines a matrix across these axes:

| Axis | Meaning |
| --- | --- |
| `agent` | Agent surface such as `codex` or `claude` |
| `agent_model` | Model name within the selected agent |
| `workflow` | Requested NVFLARE workflow such as FedAvg or SCAFFOLD |
| `comparison` | Explicit comparison object |
| `job` | Unstructured input job folder |
| `job_scale` | Scenario-provided scale annotation: `small`, `medium`, `large` |
| `repeat_count` | Number of complete comparison repeats |

Important boundaries:

- `agent` and `agent_model` are separate axes.
- `workflow` is separate from the job folder.
- `workflow` does not imply framework or skill package.
- `job` remains an unstructured folder.
- `job_scale` controls timeout and resource policy; it is not inferred by
  default.
- `comparison` is explicit and must not be overloaded by shorthand names.

Comparison examples:

```yaml
comparison:
  type: mode_ablation
  modes: [without_skills, with_skills]
```

```yaml
comparison:
  type: agent_comparison
  mode: with_skills
  agents: [codex, claude]
```

```yaml
comparison:
  type: model_comparison
  agent: codex
  mode: with_skills
  models: ["<codex-model-a>", "<codex-model-b>"]
```

```yaml
comparison:
  type: one
  mode: with_skills
```

Expansion rules:

- `mode_ablation` and `one` create one comparison group per
  `(agent, model, workflow, job, repeat)` combination.
- `agent_comparison` varies the agent axis. Each compared agent resolves to one
  model. Ambiguous model selection is a validation error.
- `model_comparison` varies the model axis for one explicit agent.
- Workflows, jobs, and repeats expand outside the compared axis.

## Prompt Model

The prompt is an explicit benchmark input. A direct run may pass a prompt file.
A scenario may render a prompt from templates, workflow instructions, and job
metadata. Either way, the rendered prompt is copied into each record directory as
`prompt.txt` with hash metadata.

The runtime prompt is rendered from:

- base task instructions;
- job metadata summary;
- workflow instruction;
- mode instruction;
- agent-neutral output expectations.

Example render variables:

```text
JOB_INPUT_DIR=/workspace/input
WORKFLOW_NAME=SCAFFOLD
EXPECTED_MODE=with_skills
```

The harness must not rely on prompt text for mode names, record paths, report
filters, or evaluator behavior. Those are harness-supplied configuration values.

## Skill Identity

The harness does not infer skill identity from workflow names, framework names,
or job folders. Skill identity is an observed output, not scenario input.

Accepted evidence sources include:

- structured agent records;
- structured benchmark records;
- explicit structured metadata written by the agent or validation workflow.

Reports should include:

```text
observed_skill_name
skill_name_source = agent_record | benchmark_record | structured_metadata | unknown
```

If no trustworthy skill identity is discovered, reports use `unknown`. The
report layer decides whether the evidence is trustworthy enough to describe as
observed skill identity; it does not infer identity from workflow or job names.

## Result Directory Layout

The result path encodes the axes needed for aggregation and debugging:

```text
results/
`-- <scenario_name>/
    |-- scenario.json
    |-- run_plan.json
    |-- scenario_summary.json
    |-- reports/
    |   |-- scenario_report.md
    |   `-- scenario_report.json
    `-- records/
        `-- agent=<agent>/
            `-- model=<model_slug>/
                `-- workflow=<workflow_slug>/
                    `-- job=<job_slug>/
                        `-- repeat=<NN>/
                            |-- repeat_summary.json
                            `-- mode=<mode>/
                                |-- record_summary.json
                                |-- agent_events.jsonl
                                |-- agent_usage.json
                                |-- agent_activity.json
                                |-- agent_last_message.txt
                                |-- agent_stderr.txt
                                |-- agent_record.json
                                |-- benchmark_record.json
                                `-- workspace_delta_manifest.json
```

Slugs are filesystem-safe and stable: lowercase, replace every non-alphanumeric
sequence with `_`, trim leading/trailing `_`, truncate the visible part to 48
characters, and append an 8-character stable hash when truncation or collision
handling is needed. Empty slugs become `item_<hash>`.

`scenario.json` stores the resolved scenario, including job paths, prompt
hashes, wheel metadata, image tags, and agent versions. `run_plan.json` stores
expanded record entries in execution order. Reports aggregate by reading
scenario metadata and normalized records, not by guessing from directory names
alone.

## Summary Schema

Every record summary includes:

```text
scenario_name
comparison_type
agent
agent_model
workflow
observed_skill_name
skill_name_source
job_slug
job_path
job_scale
repeat_index
mode
skills_enabled
runtime_image
wheel_variant
elapsed_seconds
token_count
command_count
agent_exit_code
final_container_exit_code
agent_process_passed
failure_root_cause
validation_metric
validation_metric_status
structure_quality_signal
artifact_paths
```

Every comparison summary includes:

```text
comparison_type
group_axes
compared_records[]
per_repeat_results[]
aggregate_results{}
winner_policy
quality_gate
```

`winner_policy` describes how the report selected or refused to select a winner,
for example `median_elapsed_seconds_then_tokens_with_quality_gate` or
`no_single_cost_winner`.

`quality_gate` describes the minimum correctness criteria applied before a cost
winner is considered meaningful. The harness must not invent correctness from
cost metrics.

## Repeat Aggregation

Repeats are first-class. Each repeat is a complete execution of the selected
comparison.

Per-repeat summaries include:

```text
repeat_summary.json
mode_summaries[]
comparison_type
agent
model
workflow
job
repeat_index
```

Scenario-level summaries aggregate across repeats:

```text
scenario_summary.json
scenario_name
expanded_case_count
repeat_count
comparison_groups[]
aggregate_metrics{}
```

Default statistics are median, mean, min, max, standard deviation when
`repeat_count >= 2`, pass/fail counts, failure-root counts, and validation
metric distributions when available. Headline comparisons should prefer medians
over single-run values.

## CI And Test Boundaries

CI exercises harness health, not the full benchmark matrix. A CI scenario uses:

- one supported agent;
- one model;
- one small synthetic job folder;
- one workflow;
- one explicit comparison object;
- one repeat.

CI verifies that Docker build/run works, records are produced, reports render,
skill exposure modes behave correctly, and parser assumptions remain valid.

Unit tests cover pure behavior:

- scenario expansion and slugging;
- event normalization;
- token parsing;
- record normalization;
- metric extraction;
- structure-tree rendering;
- repeat aggregation;
- report rendering helpers.

Adapter contract tests validate that sample agent outputs map into the neutral
event and usage contracts. Integration smoke tests run a tiny synthetic job and
verify normalized records and reports. Long agent runs are opt-in.

## Reporting Language

Reports use agent-neutral labels:

- `Agent events`;
- `Agent runtime`;
- `Agent usage`;
- `Agent final message`;
- `Agent status`;
- `Agent failure analysis`.

Reports always show agent name, model, CLI version when known, runtime image,
wheel variant, skill exposure mode, workflow, job metadata, and prompt hash.

Report code derives mode order and compared records from `scenario.json` and
comparison summaries. It must not hard-code a fixed three-mode ablation order or
evaluator-specific sections.
