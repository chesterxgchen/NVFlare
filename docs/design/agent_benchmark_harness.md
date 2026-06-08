# Agent Benchmark Harness Architecture Proposal

This document is the design source of truth for the agent benchmark harness. It
contains both the current implementation shape and the future generalized
architecture. The current implementation is intentionally Codex-only; Claude and
future agents are deferred until their CLI, auth, event, usage, and final-message
contracts are known.

It covers the applied repository migration and the remaining generalization
work:

- Move the current `codex_docker` harness into the NVFLARE repository as a
  benchmark tool. The initial repository migration has been applied for the
  Codex harness.
- Generalize the harness from Codex-only to Codex, Claude, and future agents.

The benchmark target remains intentionally loose: a job input is a folder with
scripts, data, and a README. The harness must not require a job schema or try to
do the agent's conversion work.

## Current Shape

The current harness has the right high-level boundary:

- `run.sh` and `build.sh` are thin shell wrappers.
- `harness/host/` owns host-side Docker orchestration, image build, and
  host-side report generation. Compatibility modules such as
  `harness/host_runner.py` may remain temporarily for migrated entry points.
- `harness/container/agent_run.py` owns in-container lifecycle ordering and
  failure handling.
- `harness/modes.py` defines the benchmark modes.
- `harness/artifacts.py`, `records.py`, `events.py`, `timing.py`, and
  `quality_signals.py` own measurement semantics.
- `harness/reports/benchmark_insights.py` and
  `harness/reports/metrics_report.py` own report generation.

The weak point is naming and agent coupling. Many artifact names and parser
functions are Codex-specific even when the underlying concept is agent-neutral:
events, final message, token usage, activity, model, and exit status.

The current Codex-only state is not a defect. The architectural risk is allowing
configuration such as `BENCHMARK_AGENT=claude` to appear runnable before the
adapter, Docker stage, auth mounts, command runner, and parser exist. Until a
non-Codex adapter is implemented, the harness should fail fast for any agent
other than `codex`.

## Target NVFLARE Layout

Recommended destination inside NVFLARE:

```text
tests/agent_benchmark/
|-- README.md
|-- bin/
|   |-- build.sh
|   `-- run.sh
|-- docker/
|   |-- Dockerfile
|   `-- build_context.dockerignore
|-- prompts/
|   `-- benchmark_prompt.txt
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
|   |   |-- reports.py
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
|       |-- reporting.py
|       |-- summaries.py
|       `-- structure_tree.py
|-- scenarios/
|   |-- ci_smoke.yaml
|   |-- codex_models.yaml
|   |-- multi_agent.yaml
|   |-- workflows.yaml
|   `-- jobs.yaml
|-- prompt_templates/
|   |-- base_conversion.md
|   `-- workflow_instruction.md
`-- fixtures/
    |-- jobs/
    |-- events/
    |-- records/
    `-- README.md
```

`docs/design/agent_benchmark_harness.md` is the architecture document. Do not
duplicate the same design text under `tests/agent_benchmark/ARCHITECTURE.md`;
the harness-local README should describe how to build and run the current tool.

Why this location:

- It is benchmark/test infrastructure, not NVFLARE product code.
- The NVFLARE repository already organizes test-adjacent tools under `tests/`;
  it does not currently have a top-level `tools/` convention.
- It depends on Docker, local wheels, external agent CLIs, and long-running
  execution, so it should stay out of unit-test packages and product packages.
- It should be runnable directly by developers without pretending every run is a
  CI test.
- Avoid putting the harness under `nvflare/` unless a small subset becomes a
  product API.

Avoid putting the benchmark implementation under
`tests/integration_test/agent_benchmark/`. That path should be for integration
tests that validate the tool, not for the tool itself.

Tests for the tool should live separately:

```text
tests/unit_test/agent_benchmark/
tests/integration_test/agent_benchmark/
```

Use `tests/unit_test/agent_benchmark/` for benchmark-harness tests even though
NVFLARE has `tests/unit_test/tool/agent/`. The latter should mirror product code
under `nvflare/tool/agent/`; this benchmark harness is not product code. If a
small product API is later extracted into `nvflare/tool/agent/`, unit tests for
that API can live under `tests/unit_test/tool/agent/`.

CI should pick one or more small scenarios from
`tests/agent_benchmark/scenarios/` instead of owning the scenario definitions.

The `fixtures/` directory is owned by the benchmark harness. It should contain
only small synthetic job folders, sample agent event streams, and sample records
used by unit, adapter, and smoke tests. It should not accumulate real benchmark
datasets or ad-hoc run outputs.

## Current Migration State

The initial migration has already been applied. The current tool lives under
`tests/agent_benchmark/`, keeps `run.sh` and `build.sh` as thin entry points,
uses explicit `harness/host/`, `harness/container/`, `harness/agents/`, and
`harness/reports/` subpackages, builds local NVFLARE wheels into Docker images,
and writes agent-neutral artifacts such as `agent_events.jsonl` while preserving
Codex compatibility aliases.

The migration deliberately preserved the legacy Codex public behavior: the same
`one`, `pair`, and `process-eval` entry points; the same unstructured job-folder
contract; and the same skills/no-skills wheel comparison. Future work should not
revisit those migration goals unless behavior compatibility must intentionally
change.

Remaining architecture work is generalization, not migration:

- make Codex-only support explicit with a fast-fail guard for unsupported agents;
- separate agent command execution from the in-container lifecycle coordinator;
- add scenario parsing, run-plan expansion, repeats, and comparison summaries;
- move reports and summary schemas from Codex-named fields to agent-neutral
  source-of-truth fields while keeping Codex aliases for old results;
- generalize Docker stages only when adding a real non-Codex adapter;
- add Claude only after the Codex adapter path reproduces current results.

## Agent Abstraction

The harness should define an agent adapter contract. The host runner should not
know how Codex or Claude is invoked.

Proposed adapter responsibilities:

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

Event normalization should be a small stateless function selected by adapter
name, not a large host-side adapter object imported into the container:

```python
normalize_agent_event(agent: str, raw_line: str) -> dict | None
```

The container runner can import only the selected agent's normalizer and parser
helpers. Host-only adapter objects can own Docker mounts, image naming, and
scenario expansion.

Shared module ownership:

- `harness/common.py`: shared JSON loading, numeric flattening, text/bool
  conversion, slug helpers, and other utilities used by both host and container
  code.
- `harness/events.py`: agent-neutral event schema, JSONL streaming helpers,
  timestamp parsing, parser warning structures, and common activity counters.
- `harness/agents/<agent>.py`: agent-specific raw event normalization, usage
  parsing, activity parsing, final-message discovery, and CLI metadata.

The adapter emits a common measurement contract:

```text
agent_events.jsonl
agent_usage.json
agent_activity.json
agent_last_message.txt
agent_stderr.txt
run_summary.json
records/<mode>_agent_record.json
records/<mode>_record.json
```

Codex-specific compatibility files can be written for old reports:

```text
codex_events.jsonl
codex_usage.json
codex_activity.json
codex_last_message.txt
codex_stderr.txt
```

The neutral files should become the source of truth for new code.

Use `records/` as the target directory name for agent/evaluator/process records.
The current runnable Codex copy may continue writing its existing record path
while the architecture changes are staged, but new scenario/run-plan code should
standardize on `records/` instead of carrying a process-eval-specific directory
name forward.

## Container Lifecycle Ownership

`harness/container/agent_run.py` should remain the in-container lifecycle
coordinator, not the owner of benchmark measurement semantics. Its job is to
read runtime configuration, validate mounted inputs, order the lifecycle phases,
preserve failure records, and call the lower-level modules that own specific
semantics.

Current ownership boundaries are:

- `harness/container/agent_run.py`: lifecycle ordering, container-local
  environment setup, skill exposure setup, prompt copy metadata, agent execution
  handoff, failure fallback records, report command orchestration, and final
  status wiring.
- `harness/artifacts.py`: workspace baseline and bounded delta capture.
- `harness/events.py`: event-derived usage and activity parsing.
- `harness/records.py`: evaluator-record selection, process-record synthesis,
  runtime-field normalization, instruction compliance, quality signals, and
  run-summary payloads.
- `harness/reports/reporting.py`: report filter discovery and evaluator-backed
  record detection.
- `harness/timing.py`: timing payload finalization.

Do not split `agent_run.py` broadly by apparent topic if that only moves
orchestration code around. The useful extraction is narrower: separate
agent-specific process execution from lifecycle orchestration. The lifecycle
runner should call a generic function such as:

```python
agent_start, agent_end, agent_exit = run_agent(config, progress)
```

The selected agent implementation should own command construction, model
selection, final-message output path, raw event stream handling, and stderr
capture. For Codex, this means moving the current `codex exec --json ...`
launch logic out of `agent_run.py` into an agent execution module or the Codex
adapter while leaving artifact capture, record synthesis, and reporting
delegation where they already belong.

Adapters must not own benchmark phases or measurement semantics. In particular,
an adapter must not decide timing boundaries, collect workspace artifacts,
synthesize or merge process records, run benchmark report generation, apply
source-input immutability policy, or choose evaluator/report filters. Those
remain harness responsibilities so Codex, Claude, and future agents are measured
through the same lifecycle contract.

Adapters may expose candidate metadata, such as an agent-reported skill name,
model name, CLI version, or raw usage object. The coordinator and report layer
decide whether that metadata is trustworthy enough to use, including whether a
skill identity should become a report filter.

## Codex Adapter

The Codex adapter should preserve current behavior:

- CLI command: `codex exec --json ...`
- Model env: `CODEX_MODEL`
- Home/auth: `CODEX_HOME`, host `.codex/auth.json`, `.codex/config.toml`
- Event parser: current JSONL normalization
- Usage parser: current cumulative token parser
- Final message: current `--output-last-message` file

The current `harness/events.py` should split into `agents/codex.py` for
Codex-specific raw event handling and `harness/events.py` for neutral helpers.

## Claude Adapter

Claude support should be implemented only after confirming the chosen Claude
surface and its stable CLI/event contract. The adapter needs to answer:

- How is the CLI installed and version-pinned?
- Where is auth/config stored and how is it mounted?
- How is the model selected?
- Can the CLI stream structured JSON events?
- Where does the final assistant response come from?
- Does the CLI report token usage directly?
- How are tool calls and shell commands represented?
- What exit codes distinguish agent failure from task failure?

If Claude does not expose Codex-like structured events, the adapter should still
emit the neutral event contract, but with lower-fidelity activity fields and an
explicit parser warning in `agent_usage.json` or `agent_activity.json`.

## Docker Design For Multiple Agents

Use a matrix of agent and skill exposure, not one hard-coded Codex image.

Recommended image naming:

```text
nvflare-agent-benchmark:<agent>-skills
nvflare-agent-benchmark:<agent>-baseline
```

Recommended Docker stages:

```text
base                 Python, uv, NVFLARE wheel install machinery, tree
agent_codex          Codex CLI and Codex auth home defaults
agent_claude         Claude CLI and Claude auth home defaults
skills_<agent>       local NVFLARE wheel with that agent's packaged skills
baseline_<agent>     local NVFLARE wheel without packaged skills
```

The local NVFLARE checkout must remain build-only input. It should never be
copied into the runtime image except through built wheels and metadata.

Build mechanics:

- Build the two NVFLARE wheels once per source checkout:
  - skills wheel:
    `NVFLARE_PACKAGE_AGENT_SKILLS=1 uv build --wheel --out-dir ...`
  - no-skills wheel:
    `NVFLARE_PACKAGE_AGENT_SKILLS=0 uv build --wheel --out-dir ...`
- Reuse those wheels across all agent images.
- Build one skills image and one baseline image per agent because the agent CLI,
  auth home, and optional native dependencies differ by agent.
- Replace hard-coded `IMAGE_NAME` and `BASELINE_IMAGE_NAME` with image resolution
  from `(agent, variant)`.
- Agent-specific version build args should be namespaced:
  - `CODEX_CLI_VERSION=...`
  - `CLAUDE_CLI_VERSION=...`
  - `NODE_IMAGE=...`
  - `UV_IMAGE=...`

The generalized builder should accept:

```text
agent
variant = skills | baseline
wheel_set = skills_wheel, no_skills_wheel
agent_cli_version
image_name
```

This prevents an N-agent matrix from rebuilding the same NVFLARE wheels N times.

## Mode Model

Keep modes independent of agent:

```text
without_skills
with_skills_eval_off
with_skills_eval_on
```

Mode definitions should describe skill exposure and evaluator state only. Agent
selection should be orthogonal:

```text
agent = codex | claude | ...
mode = without_skills | with_skills_eval_off | with_skills_eval_on
job = /path/to/job-folder
```

This enables comparisons like:

```text
codex / with_skills_eval_off
claude / with_skills_eval_off
codex / without_skills
claude / without_skills
```

## Benchmark Scenario Matrix

The benchmark should model scenarios as a matrix, not as hard-coded run scripts.
Each scenario selects values across these axes:

| Axis | Values |
| --- | --- |
| `agent` | `codex`, `claude`, ... |
| `agent_model` | model name within the selected agent |
| `workflow` | FedAvg, SCAFFOLD, other NVFLARE workflows |
| `comparison` | explicit comparison object, not just pair/triple shorthand |
| `job` | path to an unstructured training job folder |
| `job_scale` | explicit scenario annotation: `small`, `medium`, `large` |
| `repeat_count` | number of repeats for noise control |

Important distinctions:

- `agent` and `agent_model` are separate axes. Comparing Codex models is not the
  same experiment as comparing Codex against Claude.
- `workflow` is separate from the job folder. The same job can be converted with
  FedAvg, SCAFFOLD, or another workflow if the prompt/scenario requests it.
- `workflow` does not imply a framework or skill package. The same SCAFFOLD
  request could be implemented with PyTorch, TensorFlow, PyTorch Lightning, or
  another approach. The agent decides the implementation path; the harness
  records what happened.
- `comparison` is an explicit object. Do not overload `pair` to mean only a
  skills/no-skills pair.
- `job` is still only a folder. The harness may record metadata about size, data
  files, README, and expected workflow, but it should not require a job schema.
- `job_scale` is a scenario annotation, not inferred by default. The harness may
  also record observed file/data sizes for reporting, but timeouts and resource
  policy should read the scenario annotation.

Comparison examples:

```yaml
comparison:
  type: mode_ablation
  modes: [without_skills, with_skills_eval_off, with_skills_eval_on]
```

```yaml
comparison:
  type: agent_comparison
  mode: with_skills_eval_off
  agents: [codex, claude]
```

```yaml
comparison:
  type: model_comparison
  agent: codex
  mode: with_skills_eval_off
  models: ["<codex-model-a>", "<codex-model-b>"]
```

For `type: one`, the mode must be explicit:

```yaml
comparison:
  type: one
  mode: with_skills_eval_off
```

Example scenario definition:

```yaml
name: ci_smoke_codex_scaffold_small
agents:
  - name: codex
    models: ["<codex-model-name>"]
comparison:
  type: mode_ablation
  modes: [without_skills, with_skills_eval_off, with_skills_eval_on]
workflows:
  - name: SCAFFOLD
jobs:
  - path: examples/agent_benchmark_jobs/ames_small
    scale: small
repeat_count: 1
```

Example larger benchmark:

```yaml
name: multi_agent_workflow_sweep
agents:
  - name: codex
    models: ["<codex-model-a>", "<codex-model-b>"]
  - name: claude
    models: ["<claude-model-name>"]
comparison:
  type: mode_ablation
  modes: [without_skills, with_skills_eval_off]
workflows:
  - name: FedAvg
  - name: SCAFFOLD
jobs:
  - path: /benchmarks/jobs/ames_small
    scale: small
  - path: /benchmarks/jobs/ames_large
    scale: large
repeat_count: 3
```

## Scenario Expansion

`harness/scenarios.py` should own scenario parsing, validation, and expansion.
Before the first run starts, it should produce a concrete `run_plan.json` from
the scenario YAML.

Expansion rules:

- For `mode_ablation` and `one`, run one complete comparison group per
  `(agent, model, workflow, job, repeat)` combination.
- For `agent_comparison`, the comparison object varies the agent axis. Each
  compared agent must resolve to exactly one model, either from a single model in
  the top-level agents entry or from an explicit `models_by_agent` field in the
  comparison object. Ambiguous model selection is a validation error.
- For `model_comparison`, the comparison object varies the model axis for one
  explicit agent. The top-level agents list provides defaults and auth/image
  metadata, but the comparison's models list defines the compared legs.
- For all comparison types, workflows, jobs, and repeats expand outside the
  compared axis. A two-workflow, two-job, three-repeat agent comparison creates
  twelve comparison groups.

Preflight validation should happen before any Docker run:

- validate scenario schema and comparison type;
- resolve job folders and confirm each job path is a directory;
- resolve agent/model selections and reject ambiguous cross-products;
- check evaluator/report tooling availability without selecting a skill for the
  agent;
- check required Docker images or build inputs are available;
- estimate expanded run count and result directory size;
- write `scenario.json` and `run_plan.json`.

Execution should be sequential by default. Parallel execution can be added later
behind an explicit scenario field such as `execution.parallelism`, but it should
not be the default because parallel runs can interfere with timing, resource
contention, and final result interpretation.

## Result Directory Layout

The result path must encode all scenario axes needed for aggregation and
debugging. Recommended canonical layout:

```text
results/
`-- <scenario_name>/
    |-- scenario.json
    |-- scenario_summary.json
    |-- reports/
    |   |-- scenario_report.md
    |   `-- scenario_report.json
    `-- runs/
        `-- agent=<agent>/
            `-- model=<model_slug>/
                `-- workflow=<workflow_slug>/
                    `-- job=<job_slug>/
                        `-- repeat=<NN>/
                            |-- repeat_summary.json
                            `-- mode=<mode>/
                                |-- run_summary.json
                                |-- agent_events.jsonl
                                |-- agent_usage.json
                                |-- agent_activity.json
                                |-- agent_last_message.txt
                                |-- records/
                                `-- workspace_delta_manifest.json
```

Rules:

- Slugs must be filesystem-safe and stable: lowercase, replace every
  non-alphanumeric run with `_`, trim leading/trailing `_`, truncate the visible
  part to 48 characters, and append an 8-character stable hash when truncation or
  collision handling is needed. Empty slugs become `item_<hash>`.
- `scenario.json` stores the fully expanded scenario, including resolved job
  paths, prompt hashes, wheel metadata, image tags, and agent versions.
- `run_plan.json` stores the expanded runs in execution order.
- Each repeat contains a complete comparison set. A triple ablation with
  `repeat_count: 3` creates three repeat folders, each with three mode folders.
- Reports should aggregate by walking `scenario.json` and the run tree, not by
  guessing from directory names alone.
- Result roots should be kept short, for example `/data/bench/<scenario>/`,
  because the canonical axis path is intentionally descriptive and can become
  long before artifact filenames are added.

## Repeat Aggregation

Repeats are first-class. Each repeat is a complete execution of the selected
comparison.

Per-repeat summaries:

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

Default statistics:

- median;
- mean;
- min;
- max;
- standard deviation when repeat count is at least 2;
- pass/fail counts;
- evaluator-score distribution when available.

For benchmark decision-making, prefer medians over single-run values. Reports
may show per-repeat tables, but the headline comparison should use median cost
and quality/pass-rate summaries.

## Prompt Parameterization

The harness should not edit job folders to choose a workflow. Workflow selection
comes from scenario configuration and prompt rendering.

Recommended prompt model:

```text
prompt_templates/base_conversion.md
prompt_templates/workflow_instruction.md
```

The runtime prompt is rendered from:

- base prompt template;
- job metadata summary;
- workflow instruction;
- mode instruction;
- agent-neutral output expectations.

Example render variables:

```text
JOB_INPUT_DIR=/workspace/input
WORKFLOW_NAME=SCAFFOLD
EXPECTED_MODE=with_skills_eval_off
```

The rendered prompt must be copied into each run directory as `prompt.txt` with
hash metadata. Reports should show the prompt hash. The harness must not rely on
prompt text for mode names, record paths, or evaluator filters; those remain
harness-supplied environment/config values.

Workflow instructions can be a short scenario-selected block, for example:

```text
Use the SCAFFOLD workflow. Use the appropriate NVFLARE SCAFFOLD APIs and produce
an exportable NVFLARE job.
```

This is different from making the job structured. The job is still just a
folder; the scenario chooses what conversion task to ask the agent to perform.

The prompt should not name a harness-selected skill package. The benchmark can
ask for a workflow such as SCAFFOLD, but framework choice and skill/tool use are
part of the agent's work.

## Skill And Evaluator Discovery

The harness must not bind workflow names to skill packages. A workflow such as
SCAFFOLD can be implemented through different frameworks and different
conversion skills. Choosing that path is agent behavior, not harness behavior.

The harness should discover skill identity only from artifacts produced during
the run, for example:

- the agent/evaluator record;
- NVFLARE skill-eval output;
- explicit structured metadata written by the agent or evaluator.

Reports should include:

```text
observed_skill_name
skill_name_source = agent_record | evaluator_record | skill_eval_output | unknown
skill_report_status = generated | skipped
```

If a downstream NVFLARE skill report requires a skill filter, the harness may
pass only the discovered skill identity. If no skill identity was discovered, the
harness should skip the skill-specific report and write `skill_report_filter.json`
with `status=skipped` and `reason=skill_not_discovered`. It should not infer a
skill from the workflow name or job folder.

## Summary Schema

Reports should consume a common summary schema independent of comparison type.

Every run summary should include:

```text
scenario_name
comparison_type
agent
agent_model
workflow
observed_skill_name
skill_name_source
skill_report_status
job_slug
job_path
job_scale
repeat_index
mode
skills_enabled
skill_eval_enabled
runtime_image
wheel_variant
elapsed_seconds
token_count
command_count
agent_exit_code
final_container_exit_code
eval_passed
evaluator_score
validation_metric
structure_score
artifact_paths
```

Every comparison summary should include:

```text
comparison_type
group_axes
compared_runs[]
per_repeat_results[]
aggregate_results{}
winner_policy
quality_gate
```

`observed_skill_name` is run output, not scenario input. It should be populated
only from structured agent/evaluator artifacts. If the run does not expose a
skill identity, use `unknown` and keep skill-specific report status as
`skipped`.

`winner_policy` describes how the report selected or refused to select a winner,
for example `median_elapsed_seconds_then_tokens_with_quality_gate` or
`no_single_cost_winner`. It should be explicit in the summary so readers can
audit the conclusion.

`quality_gate` describes the minimum correctness criteria applied before a cost
winner is considered meaningful, for example `eval_passed=true`, validation
metric present, or `null` when no configured gate exists. The harness should not
invent correctness from cost metrics.

Examples:

- Mode ablation groups by `(agent, model, workflow, job, repeat)`.
- Agent comparison groups by `(model policy, workflow, job, mode, repeat)`.
- Model comparison groups by `(agent, workflow, job, mode, repeat)`.

The report layer should not need separate hardcoded readers for pair,
triple-ablation, model comparison, and agent comparison. It should consume this
schema and render the comparison type.

## CI Selection

CI should not run the whole benchmark matrix. It should select a small,
predictable subset:

- one agent, normally Codex until another adapter is stable;
- one model;
- one small job folder;
- one workflow;
- one explicit comparison object, likely mode ablation if runtime budget permits,
  otherwise a two-mode ablation;
- one repeat.

The CI goal is harness health: Docker build still works, records are produced,
reports render, skill exposure modes behave correctly, and no agent-specific
parser assumptions regress.

Full benchmark sweeps should be scheduled or manually triggered, not part of
normal PR CI.

## Reporting Changes

Reports should become agent-neutral:

- "Agent events" instead of "Codex events"
- "Agent runtime" instead of "Codex runtime"
- "Agent usage" instead of "Codex usage"
- "Agent final message" instead of "Codex last message"

Reports should still show:

- agent name;
- agent CLI version;
- model;
- runtime image;
- wheel variant;
- skill exposure;
- evaluator state;
- FL algorithm;
- job folder hash/metadata.

For old artifacts, report readers should accept both neutral and Codex-specific
file names.

Mode order, compared runs, and report sections should be derived from
`scenario.json` and comparison summaries. Report code should not carry a fixed
three-mode constant such as a hard-coded ablation order.

## Test Strategy

Add tests at three levels.

Unit tests for pure parsers:

- metric parsing;
- event parsing;
- token parsing;
- structure tree rendering;
- record normalization;
- scenario expansion and result path slugs;
- repeat aggregation.

Adapter contract tests:

- Codex adapter maps sample Codex JSONL into neutral events.
- Claude adapter maps sample Claude output into neutral events.
- Missing usage data records a warning instead of inventing numbers.

Integration smoke tests:

- build images from local wheels;
- run a tiny synthetic job folder;
- run the selected CI scenario from `tests/agent_benchmark/scenarios/`;
- verify selected modes produce normalized records;
- verify reports render without agent-specific assumptions;
- verify scenario summary aggregation.

Long agent runs should remain opt-in and should not block normal NVFLARE unit
tests.

## Forward Checklist

Near-term guardrails:

- Document and enforce the current supported agent set: `codex` only.
- Fail fast when `BENCHMARK_AGENT` is not implemented.
- Validate unsupported agents before Docker image resolution, Docker build, or
  container launch so an unsupported value cannot silently select a misleading
  image tag.
- Keep Docker build context explicit and allowlisted: Dockerfile, harness
  modules, staged wheel artifacts, and build metadata only. The local NVFLARE
  checkout remains build input, not runtime context.
- Keep the unstructured job-folder input contract unchanged.

Agent-neutral execution:

- Extract Codex process launch from `harness/container/agent_run.py` into a
  narrow agent execution path.
- Keep lifecycle orchestration in `agent_run.py`; do not move record, artifact,
  timing, or report semantics out of their existing owner modules unless a
  concrete new responsibility requires it.
- Add adapter tests proving Codex raw events, final message, usage, activity,
  stderr, and exit status still produce the same neutral artifacts.

Scenario architecture:

- Add scenario definitions for CI smoke, model comparison, multi-agent
  comparison, workflow sweep, and job-size sweep.
- Add `harness/scenarios.py` for schema validation, run-plan expansion,
  preflight checks, and sequential execution.
- Add canonical result directory layout with stable slugs for scenario axes.
- Add prompt rendering from scenario workflow fields.
- Add repeat-level and scenario-level summary aggregation.
- Keep legacy `one`, `pair`, and `process-eval` commands as compatibility
  wrappers that construct equivalent scenario/run-plan executions once the
  scenario engine exists.

Reporting and schema:

- Make run summaries expose agent-neutral source-of-truth fields such as
  `agent_exit_code` and `agent_process_passed`, while preserving Codex fields as
  aliases for old artifacts.
- Make report readers prefer neutral artifacts and fall back to Codex names.
- Make skill report filtering explicit for multi-skill or multi-case scenario
  result trees instead of selecting the first discovered identity.
- Add observed skill identity capture from agent/evaluator artifacts and skip
  skill-specific reports when identity is unknown.

Future multi-agent support:

- Convert Docker build from Codex-specific args to agent-specific stages only
  when another real agent adapter is ready.
- Keep local NVFLARE repo out of Docker context; continue using built wheels and
  metadata as runtime inputs.
- Add Claude adapter only after Codex adapter reproduces current results and the
  Claude CLI/auth/event/usage/final-message contract is confirmed.
