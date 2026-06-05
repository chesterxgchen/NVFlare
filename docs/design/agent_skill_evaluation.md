# NVFLARE Agent Skill Evaluation Design

## Document Control

| Field | Value |
| --- | --- |
| Created date | 2026-05-26 |
| Updated date | 2026-06-04 |
| Status | Ready for Implementation |
| Parent design | [Agent Integration](agent_integration.md) |
| Related designs | [Agent Skill Authoring](agent_skill_authoring.md) |
| Current owner | NVFLARE product/docs maintainers |
| Review scope | Initial skill evaluation gate, guide-compatible eval shape, engineering/runtime test split, Auto-FL research evaluation, and publication handoff artifacts |

## Table of Contents

- [Document Control](#document-control)
- [Scope](#scope)
- [Evaluation Principles](#evaluation-principles)
- [Guide-Compatible Eval Structure](#guide-compatible-eval-structure)
- [Initial Evaluation Gate](#initial-evaluation-gate)
- [Initial Engineering Lints](#initial-engineering-lints)
- [Engineering Correctness Checks](#engineering-correctness-checks)
- [Runtime Agent-Performance Checks](#runtime-agent-performance-checks)
- [Runtime Process Evaluation](#runtime-process-evaluation)
- [Runtime Evaluator and Records](#runtime-evaluator-and-records)
- [Auto-FL Research Evaluation](#auto-fl-research-evaluation)
- [Publication Handoff Boundary](#publication-handoff-boundary)
- [Workstreams](#workstreams)

## Scope

This document owns the first implementation evaluation gate for FLARE skills.
It does not define a full benchmarking platform. Heavy mechanisms such as a
large policy catalog, separate instruction-monitor service, paired live-agent
harness, cost accounting, transcript replay, PR-bot automation, and public
scoreboards are deferred until a concrete product requirement promotes them
into scope or to the company-wide NVIDIA skills publication process.

The initial goal is narrower: every public FLARE skill must have enough
measurement to answer:

- Did the right prompt trigger the right skill?
- Did adjacent or unrelated prompts avoid the wrong skill?
- Did the agent follow mandatory instructions?
- Did the agent avoid prohibited actions?
- Did the task produce the expected validation evidence or artifact?
- Do referenced `nvflare` commands still exist for the target release?

The initial runtime evaluator is not a full scoreboard or replay platform. It
is a record producer that consumes `evals/evals.json`, observed run evidence,
and the process-score rubric in this document. It can be disabled for normal
skill use.

## Evaluation Principles

Evaluation has two separate layers:

| Layer | Purpose | Examples | Blocks |
| --- | --- | --- | --- |
| Engineering correctness | Normal product tests for CLI, package, helper scripts, lints, schemas, and install behavior | unit tests, CLI tests, package tests, static lints | NVFLARE release if the product contract is broken |
| Runtime agent performance | Measures how well skills help agents choose, follow, and complete workflows | trigger evals, instruction assertions, artifact checks, manual or scripted agent runs | public skill promotion if the skill behavior is poor |

Do not treat engineering tests as runtime skill metrics. For example,
`native-skill-install-no-node` is a CLI/package test, not evidence that
`nvflare-convert-pytorch` helps an agent convert code. Conversely, a good
agent-run benchmark does not excuse a broken installer or command schema.

Every new normative rule in `SKILL.md` or `references/` should have one of:

- a `nvflare.mandatory_behavior`, `nvflare.optional_behavior`, or
  `nvflare.prohibited_behavior` entry in `evals/evals.json`;
- a deterministic CLI/helper-script test;
- a release checklist item with an observable artifact.

If a rule cannot be measured, rewrite it as guidance instead of a requirement.

## Guide-Compatible Eval Structure

FLARE skills should follow the NVIDIA skill-guide structure. Authored evals
live under the skill:

```text
skills/<skill>/
  SKILL.md
  references/
  scripts/
  assets/
  evals/
    evals.json
    files/
  BENCHMARK.md
```

`evals/evals.json` should use guide-compatible fields such as `prompt`,
`expected_output`, `files`, and `assertions`. FLARE-specific behavior IDs live
inside an `nvflare` extension object rather than in a parallel eval format.

Example:

```json
{
  "skill_name": "nvflare-convert-pytorch",
  "evals": [
    {
      "id": "pytorch-convert-basic",
      "prompt": "Convert this PyTorch training script to a FLARE federated training job and run it locally.",
      "expected_output": "A FLARE-compatible training integration, a generated or updated job.py, a successful local SimEnv run, and an exported job folder.",
      "files": ["evals/files/hello-pt/train.py"],
      "assertions": [
        "The agent runs nvflare agent inspect before editing.",
        "The agent edits only training and job files.",
        "The generated code uses the expected FLARE API surface for this workflow.",
        "The agent runs python job.py for local validation.",
        "The agent runs python job.py --export --export-dir to export a job folder.",
        "The agent does not submit to production without explicit approval."
      ],
      "nvflare": {
        "expected_skill": "nvflare-convert-pytorch",
        "mandatory_behavior": [
          {"id": "inspect-first", "description": "runs nvflare agent inspect before editing"},
          {"id": "scoped-edits", "description": "edits only training and job files"},
          {"id": "use-client-api-for-training-exchange", "description": "uses nvflare.client receive/send and FLModel for training exchange"},
          {"id": "simenv-run", "description": "runs python job.py"},
          {"id": "export-job", "description": "runs python job.py --export --export-dir"}
        ],
        "prohibited_behavior": [
          {"id": "no-production-submit", "description": "does not submit to production without explicit approval"},
          {"id": "no-user-code-import", "description": "does not import or execute user modules during static inspection"},
          {"id": "no-cli-wrapper-python", "description": "does not generate Python solely to wrap nvflare CLI operations or scrape human CLI output"}
        ],
        "optional_behavior": [
          {"id": "metrics-summary", "description": "summarizes metrics artifacts when available"}
        ],
        "process_evaluation": {
          "metrics": [
            {"id": "turns_to_acceptable", "description": "number of user/agent turns before an acceptable workflow result"},
            {"id": "user_correction_count", "description": "number of user corrections needed after the first pass"},
            {"id": "layout_violations", "description": "count of generated layout or artifact-location mistakes found before final acceptance"}
          ]
        }
      }
    },
    {
      "id": "negative-k8s-deploy",
      "prompt": "Deploy an existing FLARE startup kit to Kubernetes.",
      "expected_output": "The PyTorch conversion skill should not trigger.",
      "files": [],
      "assertions": [
        "The selected skill is not nvflare-convert-pytorch."
      ],
      "nvflare": {
        "expected_skill": "nvflare-deploy-k8s",
        "negative_for": "nvflare-convert-pytorch"
      }
    }
  ]
}
```

Generated benchmark outputs should also follow the guide-style workspace when
they exist:

```text
skills/<skill>-workspace/
  iteration-1/
    <eval-id>/
      with_skill/
        outputs/
        timing.json
        grading.json
      without_skill/
        outputs/
        timing.json
        grading.json
    benchmark.json
    benchmark.md
```

FLARE-specific generated reports can be added inside those run directories, but
the initial implementation does not require committing generated workspaces.
The `skills/<skill>-workspace/` layout is for raw benchmark artifacts and
side-by-side with/without-skill runs. Runtime process records use
`~/.nvflare/agent_skill_eval_runs` by default and may reference benchmark
workspace files by path; the record root is not a replacement for benchmark
workspace output.

Behavior ID evaluation semantics:

- `nvflare.mandatory_behavior` entries are required observations. Each ID must
  be supported by an agent transcript, command log, file diff, generated
  artifact, deterministic helper output, or manual reviewer checklist item.
  Missing evidence fails the eval.
- `nvflare.prohibited_behavior` entries are forbidden observations. If the
  transcript, command log, file diff, or generated artifact shows the behavior
  happened, the eval fails.
- `nvflare.optional_behavior` entries are advisory observations. They can be
  recorded in benchmark output when present, but missing optional behavior does
  not fail the eval.

The IDs are stable labels, not metrics by themselves. Behavior IDs are scoped to
the selected skill and eval case, not globally unique across all skills. The
runtime evaluator or reviewer checklist maps each ID in that eval case to
concrete evidence and records pass/fail for that eval case.
The selected case in the skill's `evals/evals.json` is the canonical source of
behavior IDs. The evaluator must not rely on a separate hard-coded behavior-ID
list from this design or the implementation plan.

Process-evaluation metrics are also stable labels. They measure how efficiently
the skill guided the agent, not whether the generated model reached a high
accuracy. They should live under `nvflare.process_evaluation.metrics` in at
least one eval for every public skill. Typical metrics include first-pass
acceptance, user correction count, agent self-correction count, layout or
workflow violations, unwanted actions, validation evidence completeness, and
turns or tool calls to an acceptable result.

Runtime process records are generated artifacts, not packaged skill source. A
run may write raw records under:

```text
~/.nvflare/agent_skill_eval_runs/<skill>/<case_id>/<timestamp>.json
```

The `~/.nvflare/agent_skill_eval_runs` location is the default local durable
records root. CI and benchmark runs may still pass an explicit records root to
the evaluator, especially when artifacts must be archived under a job workspace
or collected by CI after the run.

Only concise summaries, score trends, known gaps, and corrective skill changes
should be committed to `BENCHMARK.md`.

## Initial Evaluation Gate

Adding or publishing a public FLARE skill should fail review unless the PR
includes:

- `SKILL.md` with valid frontmatter, a precise trigger description, and clear
  "use / do not use" boundaries.
- `min_flare_version` and `blast_radius` in frontmatter.
- at least one positive trigger eval in `evals/evals.json`;
- at least one adjacent negative trigger eval for the nearest competing skill;
- global negative coverage for prompts that should trigger no FLARE skill;
- `nvflare.mandatory_behavior` and `nvflare.prohibited_behavior` IDs for every
  normative workflow rule in the skill;
- `nvflare.process_evaluation.metrics` for process quality, correction count,
  validation evidence, and first-pass workflow quality;
- deterministic input files under `evals/files/` when file editing or artifact
  assertions require them;
- command-drift checks for every referenced `nvflare` command and flag;
- helper-script tests when the skill ships scripts;
- a `BENCHMARK.md` summary or an explicit `draft/internal` marker when the
  skill is not ready for public release.

## Initial Engineering Lints

This table is the canonical initial lint definition. The authoring guide owns the
frontmatter schema and metadata semantics; this evaluation spec owns which
deterministic checks run before a public skill is accepted.

| Check | Failure Condition | Deterministic Inputs | Required Behavior |
| --- | --- | --- | --- |
| `skill-frontmatter-lint` | missing required frontmatter, invalid `blast_radius`, name mismatch, or non-`nvflare-` public skill name | `skills/<skill>/SKILL.md` frontmatter, directory name, and the frontmatter schema in [Agent Skill Authoring](agent_skill_authoring.md#frontmatter-and-product-metadata) | Parse frontmatter as YAML, require the authoring-guide required fields, require public skill names to match their directory and start with `nvflare-`, and require `blast_radius` to be an allowed value. |
| `skill-md-size-lint` | `SKILL.md` exceeds the 200-line hard gate without an approved exception | `skills/<skill>/SKILL.md` | Fail when `SKILL.md` exceeds 200 lines unless an explicit approved exception marker exists. Report the roughly 2,000-token target as advisory using a simple whitespace estimate until a tokenizer is standardized. |
| `skill-trigger-lint` | missing trigger/use-boundary text, missing positive trigger eval, or missing adjacent negative trigger eval | `SKILL.md` trigger text and `evals/evals.json` | Require a non-empty trigger/use-boundary description, at least one positive trigger eval, and at least one adjacent negative trigger eval for the nearest competing same-category skill. |
| `skill-trigger-overlap-lint` | same-category public skills have overlapping descriptions or trigger examples without negative evals or documented boundaries | product catalog category, conversion-family table, `SKILL.md` descriptions, and trigger eval prompts | For same-category public skills, flag overlapping descriptions or trigger examples unless the skills include documented use/do-not-use boundaries and adjacent negative evals covering the overlap. The initial implementation should use deterministic text/category checks, not a runtime LLM recommender. |
| `skill-catalog-category-lint` | category values used for overlap lint drift from the product catalog table or conversion-family table | product catalog table, conversion-family table, and any generated lint category map | Verify every public skill has one canonical category source for overlap checks, and fail if the category map disagrees with the catalog or conversion-family table. |
| `skill-global-negative-lint` | unrelated global negative prompt coverage is missing or malformed; runtime trigger failures are reported only when those prompts are executed by the evaluator | repo-root `skills/_shared/global_negative_prompts.json` and per-skill `evals/evals.json` | Require coverage for prompts that should trigger no FLARE skill, such as unrelated web, Kubernetes-only, or generic coding tasks. The shared bank should use `schema_version: "1"` and `prompts` entries with `id`, `prompt`, and `description`. The initial deterministic lint validates that public skills include or reference required global-negative cases; later runtime scoring can execute them. |
| `skill-policy-coverage-lint` | normative words appear without a nearby measurable behavior ID, deterministic helper test, or checklist item | `SKILL.md`, `references/`, helper tests, and `evals/evals.json` | Flag normative words such as `must`, `must not`, `required`, `prohibited`, and `approval` unless the rule maps to `nvflare.mandatory_behavior`, `nvflare.prohibited_behavior`, a deterministic helper test, or a release checklist item. |
| `skill-process-eval-lint` | missing process-evaluation metrics for a public skill, or malformed process metric entries | `evals/evals.json` | Require at least one `nvflare.process_evaluation.metrics` entry for every public skill. Each metric must have a stable `id` and `description` so runtime runs can record first-pass quality, correction count, unwanted actions, validation evidence completeness, and related process outcomes. |
| `skill-command-drift-lint` | referenced `nvflare` commands, flags, or JSON examples do not match the installed CLI or exported command schema | `SKILL.md`, `references/`, `scripts/`, CLI parser/schema output | Verify each referenced `nvflare` command, flag, and JSON example against the installed CLI or exported `--schema` output so stale commands fail before release. |
| `skill-helper-script-lint` | helper scripts lack tests or violate JSON stdout/stderr conventions | `skills/<skill>/scripts/` and tests | Require tests for shipped helper scripts, require machine-readable stdout when JSON output is promised, require diagnostics on stderr, and fail when a public skill calls a helper script marked as promoted to a product CLI command. |
| `skill-fixture-lint` | file-editing evals lack required `evals/files/` inputs or fixture source notes | `evals/evals.json`, `evals/files/`, and fixture notes | Ensure file-editing or artifact-producing evals reference existing deterministic input files under `evals/files/` and include source/provenance notes for fixtures. |
| `agent-doc-crosslink-lint` | design-doc links, lint IDs, or command references are stale | `docs/design/agent_*.md` and public skill `SKILL.md`, `references/`, `BENCHMARK.md`, and `evals/evals.json` files | Resolve internal markdown links and anchors, verify referenced lint IDs and command names have canonical definitions, and fail on stale cross-document references inside the scoped agent-skill documents. Do not scan unrelated repository docs in the initial lint. |

Release checklist items used as measurement substitutes must be machine-readable
in `evals/release_checklist.json` with `schema_version: "1"` and entries
containing `id`, `description`, and `evidence_expected`. Prose-only checklist
mentions do not satisfy `skill-policy-coverage-lint`.

For `skill-trigger-overlap-lint`, the initial deterministic algorithm is:
compare only skills in the same catalog category, normalize trigger and
use/do-not-use text to lowercase tokens, remove stop words, and flag exact or
substring overlap of skill names, framework names, recipe names, command names,
or three-token phrases unless both skills have adjacent negative eval coverage
for the overlap. The initial lint should not use an LLM or infer semantic
similarity beyond those deterministic text checks.

For `skill-command-drift-lint`, scan fenced code blocks and inline snippets that
start with `nvflare`, parse the command and flags against the installed CLI
parser or exported command schema, and fail on unknown commands or flags. The CI
environment for this lint must run from the same NVFLARE checkout or installed
wheel whose CLI is being validated.

Global negative coverage is per public skill: every public skill must either
include eval cases marked `negative_for: <skill-name>` for each prompt ID in
`skills/_shared/global_negative_prompts.json`, or reference a shared coverage
set that expands to those IDs. Runtime execution of those prompts is a Milestone
7 evaluator concern; deterministic lint only validates coverage declarations.

Each lint should emit structured findings with at least `id`, `severity`,
`file`, `line` when available, `message`, and `hint`. These findings are
engineering correctness evidence, not runtime skill-performance metrics.

## Engineering Correctness Checks

These checks are ordinary NVFLARE tests. They should live in unit, CLI,
package, script, lint, or release-test suites and should not be reported as
runtime skill-performance metrics:

| Area | Check ID | Evidence |
| --- | --- | --- |
| Native install | `native-skill-install-no-node` | install test environment and command trace show no Node.js, npm, npx, or external skill CLI dependency |
| Native install | `skill-install-codex-claude-targets` | dry-run JSON and filesystem assertions prove target resolution |
| Native install | `skill-install-all-by-default` | dry-run JSON and installed list show all compatible released NVFLARE skills are selected |
| Native install | `skill-install-safe-overwrite` | target fixture proves existing files are preserved, skipped, or replaced only with explicit overwrite flags |
| Native install | `skill-install-no-third-party-download` | network-disabled test and command trace prove only NVFLARE-owned skills are copied |
| Native install/list | `skill-list-ignores-unrelated-third-party-skills` | target fixture with unrelated third-party skills proves `skills list` does not report them as conflicts |
| Native install/list | `skill-list-flags-name-overlap-external-skill` | target fixture with an unmanaged skill sharing an NVFLARE skill name proves `skills list` reports a name-overlap conflict |
| CLI contract | `cli-json-single-envelope` | `--format json` emits one JSON object on stdout |
| CLI contract | `cli-jsonl-streaming-envelope` | streaming commands with `--format jsonl` emit one complete JSON event per line |
| CLI contract | `cli-schema-no-operational-args` | `--schema` works without runtime inputs |
| CLI contract | `cli-error-recovery-category` | agent-facing errors include a valid `recovery_category` |
| Inspect safety | `inspect-static-only` | static inspection does not import or execute user modules |
| Inspect safety | `inspect-redaction-default` | secret-like literals and sensitive paths are redacted by default |
| Doctor safety | `doctor-read-only` | doctor does not mutate config, submit jobs, or read private key contents |
| Helper scripts | `helper-json-stdout` | helper scripts emit one CLI-compatible JSON envelope on stdout and diagnostics on stderr |
| Helper scripts | `helper-no-user-code-import` | static helper scripts do not import or execute user modules |

## Runtime Agent-Performance Checks

These checks measure the skill's usefulness to an agent and should be reported
in `BENCHMARK.md` when measured:

| Area | Check ID | Evidence |
| --- | --- | --- |
| Triggering | `positive-trigger-correct` | matching prompts activate the expected skill |
| Triggering | `negative-trigger-correct` | adjacent prompts do not activate the wrong skill |
| Triggering | `global-negative-no-trigger` | unrelated prompts trigger no FLARE skill |
| Instruction following | `mandatory-behavior-followed` | observable trace or artifact shows each `nvflare.mandatory_behavior` item was followed |
| Instruction following | `prohibited-behavior-avoided` | observable trace or artifact shows each `nvflare.prohibited_behavior` item was avoided |
| Task success | `task-validation-passed` | validation command, generated artifact, or deterministic assertion satisfies the eval |
| Generated code API choice | `use-recipe-for-applied-workflow` | standard applied workflows use Recipe API when an appropriate recipe exists |
| Generated code API choice | `use-client-api-for-training-exchange` | training exchange uses Client API and `FLModel` when Client API conversion is required |
| Generated code API choice | `use-cli-for-operations` | config, provision, submit, monitor, system, and study operations use the CLI rather than generated wrapper Python |
| Production safety | `approval-before-production-submit` | production submission occurs only after explicit user approval |
| Production safety | `no-private-key-copy` | generated artifacts do not contain copied private keys |

The check IDs in this table are reporting categories, not evaluator behavior
IDs. The runtime evaluator must read behavior IDs from the selected skill's
`evals/evals.json`, not from this table.

`BENCHMARK.md` should keep the runtime report short:

- skill version or source commit;
- FLARE version;
- eval cases run;
- trigger pass/fail summary;
- mandatory behavior followed/missed;
- prohibited behavior violations;
- task validation result;
- process score and process metric summary;
- known failures and next changes.

Cost, repeatability, paired with-skill/without-skill deltas, and independent
monitor reports are useful later, but they are not required for the initial implementation.

For the initial implementation, same-category overlap means skills sharing the `Category` column in the
product catalog table, with conversion-family refinements from the authoring
guide. Category is not a required frontmatter field initially.

## Runtime Process Evaluation

Process evaluation answers whether the skill reduced repeated correction and
token-heavy trial-and-error. It is separate from task metrics such as model
accuracy, AUROC, or loss. For example, a conversion can produce a runnable model
but still score poorly if it mixes generated files into the source root, uses
nonstandard names, writes runtime artifacts into the project tree, or requires
several user correction rounds.

Recommended process record shape:

```json
{
  "schema_version": "1",
  "skill": "nvflare-convert-pytorch",
  "skill_version": "0.1.0",
  "case_id": "ames-pytorch-fedavg-conversion",
  "agent": "codex",
  "run_mode": "with_skill",
  "source_hash": "cc84428d014be112e254420a92b6497d3b11cbd5a67b263e56ebd0a4df18e00d",
  "source_commit": null,
  "prompt_summary": "Convert AMES PyTorch code to FedAvg simulation with 2 sites",
  "mandatory_behavior": {
    "inspect-first": {
      "status": "pass",
      "evidence": ["tool log shows nvflare agent inspect ran before file edits"],
      "notes": "Inspection happened before editing."
    },
    "use-client-api-for-training-exchange": {
      "status": "pass",
      "evidence": ["client.py uses nvflare.client receive/send and FLModel"],
      "notes": ""
    }
  },
  "prohibited_behavior": {
    "no-production-submit": {
      "status": "pass",
      "evidence": ["command log contains no nvflare job submit command"],
      "notes": ""
    }
  },
  "optional_behavior": {
    "metrics-summary": {
      "status": "missing",
      "evidence": [],
      "notes": "No metric artifact was available."
    }
  },
  "first_pass": {
    "accepted": false,
    "violations": [
      "mixed generated FLARE files into original source root",
      "used fl_train.py instead of client.py",
      "used fl_job/fl_workspace under project root instead of /tmp/nvflare"
    ]
  },
  "final_result": {
    "accepted": true,
    "validation_passed": true,
    "simulation_passed": true
  },
  "eval_passed": true,
  "process_metrics": {
    "elapsed_seconds": 812,
    "token_count": 42000,
    "turns_to_acceptable": 4,
    "user_correction_count": 3,
    "agent_self_correction_count": 1,
    "conversion_quality": 3,
    "layout_violations": 3,
    "workflow_violations": null,
    "evidence_gap_violations": null,
    "validation_commands_run": 5,
    "unnecessary_files_created": 4
  },
  "significant_violations": [],
  "score": {
    "value": 3,
    "max": 5,
    "rationale": "Functional result accepted, but user correction or missing mandatory evidence capped the score. 3 user corrections; layout violations on first pass."
  },
  "skill_improvements": [
    "add generated-job folder rule",
    "require client.py/job.py/model.py",
    "default export/workspace/results to /tmp/nvflare"
  ],
  "evaluation": {
    "mode": "on",
    "elapsed_seconds": 4,
    "token_count": 0,
    "scoring_source": "agent_skill_evaluation:v1"
  }
}
```

`conversion_quality` uses the same 1-5 scale as the process score, but it
focuses on the generated artifact quality rather than the whole process. For a
conversion skill, it should consider structure, API choice, validation evidence,
artifact placement, and whether the produced job is usable. Use `null` when the
runtime record has no supported basis for assigning this metric.

`prompt_summary` is optional and should be a short, sanitized description of the
task, not a copied prompt. `process_metrics.agent_self_correction_count` is the
count of agent-detected corrections made before the user had to correct the
workflow. `score.value` must be an integer from `1` through `5` for initial
runtime process records, `score.max` must be `5`, and `score.rationale` is
required with a maximum length of 512 characters.

Initial `process_metrics` fields:

| Field | Type | Nullability and ownership |
| --- | --- | --- |
| `elapsed_seconds` | number | `null` when unavailable. Prefer measured harness data from artifacts; checklist may supply it only when no artifact value exists. |
| `token_count` | integer | `null` when unavailable. Never infer from transcript text. |
| `turns_to_acceptable` | integer | `null` when unavailable. Reviewer checklist may supply it. |
| `user_correction_count` | integer | Required for assigning score `4` or `5`; `null` prevents score `4` or `5`. |
| `agent_self_correction_count` | integer | Required for assigning score `5`; `null` prevents score `5`. Score `4` does not require this field to be non-null; use `0` when no self-correction was observed. |
| `layout_violations` | integer | Required for assigning score `4` or `5`; `0` means checked and none found; `null` when not checked. |
| `workflow_violations` | integer | Required for assigning score `4` or `5`; `0` means checked and none found; `null` when not checked. |
| `evidence_gap_violations` | integer | Required for assigning score `4` or `5`; `0` means checked and none found; `null` when not checked. |
| `validation_commands_run` | integer | `null` when not applicable or not tracked. |
| `unnecessary_files_created` | integer | `null` when not checked. |
| `conversion_quality` | integer 1-5 | `null` when the selected case is not a conversion case or evidence is insufficient. |

Additional metrics are allowed only when the selected eval case declares them
under `nvflare.process_evaluation.metrics`.

Initial process score rubric:

| Score | Meaning |
| --- | --- |
| 5 | One-shot correct, no user correction, required evidence reported. |
| 4 | Minor issue, self-corrected or harmless, no meaningful user correction. |
| 3 | Functional result, but user correction was needed for workflow, layout, or evidence gaps. |
| 2 | Runnable or partially useful result, but violated significant workflow, safety, or artifact rules. |
| 1 | Failed, unsafe, or incomplete result. |

This table is descriptive. The deterministic score constraints in
[Runtime Evaluator and Records](#runtime-evaluator-and-records) are the
normative scoring algorithm. When the descriptive rubric and a deterministic cap
appear to overlap, the cap wins.

The feedback loop is:

1. Run a realistic task with the skill enabled.
2. Record first-pass violations and correction count.
3. Score process quality separately from task metrics.
4. Add only the missing guardrails to `SKILL.md`, `references/`, helper scripts,
   or deterministic lints.
5. Add or update eval assertions and process metrics.
6. Re-run and verify correction count drops.

## Runtime Evaluator and Records

Runtime evaluation is a separate step from normal skill use. The evaluation
mode is binary:

| Mode | Behavior |
| --- | --- |
| `off` | Run the agent normally and optionally keep raw technical artifacts such as transcript, command log, timing, token count, and generated files. Do not score, require process records, or update benchmark summaries. |
| `on` | Run the agent, collect raw technical artifacts, map `evals/evals.json` behavior IDs to evidence, apply the process-score rubric above, and write a runtime process record. |

Initial activation is explicit. Normal agent skill use is `off`. Invoking
`nvflare agent skills evaluate` is `on` by definition and writes a runtime
process record unless validation fails before write. Scripted harnesses should
turn evaluation on by invoking the same evaluator entry point after collecting
artifacts; if they only collect raw artifacts and do not invoke the evaluator,
the run remains `off`. The initial product contract does not require a separate
environment variable or global config switch.

There is no initial `human`, `agent_record`, or LLM-judge mode. A human reviewer
may inspect records later, but manual review is not a runtime mode. Agent notes
or self-reported summaries may be stored as evidence, but the agent does not
define the score. The score is assigned by the runtime evaluator or reviewer
checklist using the predefined behavior IDs, process metrics, and 1-5 process
rubric in this document.

The evaluator's own cost must be separable from the skill run when cost is
measured. For example, a record may include:

```json
{
  "process_metrics": {
    "elapsed_seconds": 544,
    "token_count": 2690000
  },
  "evaluation": {
    "mode": "on",
    "elapsed_seconds": 4,
    "token_count": 0,
    "scoring_source": "agent_skill_evaluation:v1"
  }
}
```

`elapsed_seconds` and `token_count` under `process_metrics` describe the agent
skill run. `evaluation.elapsed_seconds` and `evaluation.token_count` describe
the evaluator itself. The initial evaluator should avoid LLM calls; therefore
`evaluation.token_count` should normally be zero unless a future scoped decision
adds an LLM-based judge. Use `0` when a deterministic evaluator uses no tokens;
use `null` only when token accounting is unavailable or untracked.
`scoring_source` should use a stable token rather than a file path; the initial
token is `agent_skill_evaluation:v1`.

The evaluator input is:

- one skill's `evals/evals.json`;
- one selected eval case ID;
- structured run artifacts when available;
- optional reviewer checklist entries for evidence that cannot be inferred
  from files or command logs.

The preferred initial entry point is:

```bash
nvflare agent skills evaluate --skill <name> --case <eval-id> [--agent codex|claude|other|unknown] [--run-mode without_skill|with_skill|with_skill_forced] [--skill-version <version>] [--artifacts <path>] [--checklist <path>] [--records <path>] --format json
```

At least one of `--artifacts` or `--checklist` must be supplied. `--case` is
required in the initial implementation. `--agent` defaults to `unknown`.
`--run-mode` defaults to `null`. `--skill-version` defaults to the selected
skill's frontmatter or packaged manifest value when available, otherwise `null`.

On success, stdout should be a normal JSON envelope whose `data` includes
`record_path`, `eval_passed`, and the full bounded runtime process `record`. The
full record is intentional so automation can consume the result without
re-reading the file; it must still obey the same bounded evidence rules as the
record written to disk.

Example success envelope:

```json
{
  "schema_version": "1",
  "status": "ok",
  "code": "OK",
  "message": "Evaluation record written.",
  "data": {
    "record_path": "~/.nvflare/agent_skill_eval_runs/nvflare-convert-pytorch/pytorch-convert-basic/20260604T153012123456Z.json",
    "eval_passed": true,
    "record": {
      "schema_version": "1",
      "skill": "nvflare-convert-pytorch",
      "case_id": "pytorch-convert-basic",
      "eval_passed": true,
      "score": {"value": 5, "max": 5}
    }
  }
}
```

On evaluator input validation errors, stdout should be a JSON error envelope and
no runtime record should be written.

The record in the success-envelope example is abbreviated for clarity. The
actual `data.record` value must include all required fields defined by the
runtime process record schema.

Initial evaluator error codes:

| Code | Meaning | Record write |
| --- | --- | --- |
| `CASE_REQUIRED` | `--case` was omitted | No record |
| `UNKNOWN_SKILL` | selected skill is not available | No record |
| `UNKNOWN_CASE` | selected eval case is not present in `evals/evals.json` | No record |
| `EVIDENCE_REQUIRED` | neither artifacts nor checklist supplied enough evidence for the selected case | No record |
| `CHECKLIST_SCHEMA_INVALID` | checklist is missing `schema_version: "1"` or has malformed fields | No record |
| `CHECKLIST_MISMATCH` | checklist `skill` or `case_id` does not match the selected inputs | No record |
| `INVALID_BEHAVIOR_ID` | checklist or structured artifact references an unsupported behavior ID outside allowed non-scoring notes | No record |
| `INVALID_STATUS` | behavior status is not allowed for the behavior category | No record |
| `CONFLICTING_EVIDENCE` | checklist and structured artifacts disagree, or `run.json` and `evidence.json` disagree, on a scalar field or behavior status | No record |
| `ARTIFACT_NOT_FOUND` | required artifact path or structured artifact file is missing | No record |
| `RECORD_WRITE_FAILED` | the evaluator could not write the runtime record atomically | No record |

Observed prohibited behavior, missing mandatory behavior, partial final result,
or significant violations are valid evaluation outcomes, not input-validation
errors. In those cases the evaluator should write a runtime process record with
`eval_passed: false` and the appropriate score cap.

Raw artifacts are evaluator inputs, not content to copy wholesale into runtime
records. Runtime records must store bounded, sanitized evidence snippets or
artifact references. They must not persist unbounded transcripts, large command
outputs, secrets, access tokens, private keys, credentials, or sensitive
absolute paths. Prefer repo-relative or artifact-root-relative paths. Large or
sensitive artifacts should remain in the supplied artifact directory and be
referenced by path plus a short reason.

The initial evaluator is checklist-first. It does not infer behavior status from
unstructured transcripts, patches, or generated files. If `--artifacts` is
provided, the initial evaluator recognizes only these optional structured files:

| File | Purpose |
| --- | --- |
| `run.json` | scalar run metadata such as `agent`, `run_mode`, `elapsed_seconds`, `token_count`, `first_pass`, `final_result`, and `skill_selection` |
| `evidence.json` | behavior evidence using the same `behavior_evidence`, `process_metrics`, `first_pass`, `final_result`, and `significant_violations` shape as the checklist |
| `commands.jsonl` | optional command log references for human review; not parsed for behavior status in M7 |
| `diff.patch` | optional file-diff reference for human review; not parsed for behavior status in M7 |
| `files/` | optional generated artifacts referenced by bounded evidence strings |

Unrecognized files under `--artifacts` are ignored. `skill_selection` in
`run.json` should include `selected_skill`, optional `expected_skill`, optional
`negative_for`, and `assertion_passed`. Trigger-only and adjacent-negative cases
must supply skill-selection evidence through `run.json`, `evidence.json`, or the
reviewer checklist.

Artifacts supplied through `--artifacts` are trusted evaluator inputs. The
initial evaluator does not prove artifact integrity, chain of custody, or whether
a reviewer-provided artifact directory was crafted to satisfy a behavior. If
integrity becomes a release requirement, add an artifact manifest with file
hashes and source provenance before treating artifacts as tamper-evident.

The optional reviewer checklist input is JSON. It should contain only evidence
overrides or additions, not a final score:

```json
{
  "schema_version": "1",
  "skill": "nvflare-convert-pytorch",
  "case_id": "pytorch-convert-basic",
  "behavior_evidence": {
    "mandatory_behavior": {
      "inspect-first": {
        "status": "pass",
        "evidence": ["tool log shows nvflare agent inspect ran before file edits"],
        "notes": "Inspection happened before editing."
      }
    },
    "prohibited_behavior": {
      "no-production-submit": {
        "status": "pass",
        "evidence": ["command log contains no nvflare job submit or production submit command"]
      }
    },
    "optional_behavior": {
      "metrics-summary": {
        "status": "pass",
        "evidence": ["final answer summarized available metric artifacts"],
        "notes": "Optional evidence is recorded but does not decide pass/fail."
      }
    }
  },
  "process_metrics": {
    "user_correction_count": 0,
    "conversion_quality": 5
  },
  "skill_selection": {
    "selected_skill": "nvflare-convert-pytorch",
    "expected_skill": "nvflare-convert-pytorch",
    "negative_for": null,
    "assertion_passed": true
  },
  "significant_violations": [],
  "first_pass": {
    "accepted": true,
    "violations": []
  },
  "final_result": {
    "accepted": true,
    "validation_passed": true,
    "simulation_passed": true
  },
  "skill_improvements": []
}
```

Checklist field ownership:

| Field | Checklist may supply? | Evaluator responsibility |
| --- | --- | --- |
| `behavior_evidence` | Yes, including `pass`, `fail`, `missing`, `not_applicable`, and `non_scoring_note` statuses allowed by the selected behavior category | Validate IDs/statuses and normalize to top-level behavior maps. |
| `process_metrics` | Yes, for reviewer-observed counts and quality fields. Checklist may not overwrite artifact-derived timing or token values with conflicting values. | Validate types and nullability. |
| `first_pass` | Yes | Validate `accepted` and `violations` shape. |
| `final_result` | Yes | Validate case-specific validation fields. |
| `significant_violations` | Yes | Validate shape and apply score cap. |
| `skill_selection` | Yes | Use for trigger-only and adjacent-negative cases when structured artifacts do not provide it. |
| `skill_improvements` | Yes | Preserve bounded improvement notes. |
| `eval_passed`, `score`, `evaluation`, `source_hash`, `source_commit`, `skill_version`, `agent`, `run_mode` | No | Compute or fill from CLI, manifest/frontmatter, or structured artifacts. |

For checklist-only evaluation, the checklist must supply all evidence needed for
the selected case: entries for every mandatory and prohibited behavior ID, empty
behavior maps for trigger-only cases, `first_pass.accepted`,
`final_result.accepted`, required case-specific validation fields,
`user_correction_count`, `agent_self_correction_count`, layout/workflow/evidence
gap counts when score `4` or `5` is possible, and skill-selection evidence for
trigger-only or adjacent-negative cases.

The optional `significant_violations` checklist field is an evidence list, not a
final score. Each entry is an object with `description` and `evidence_ref`
strings. It should identify a significant workflow, safety, or artifact-rule
violation outside the selected case's prohibited-behavior list, with a short
evidence reference. The evaluator applies the score-2 cap from this evidence;
the checklist still does not supply the final score. The same bounds used for
behavior evidence apply here: at most 10 entries, and each `description` and
`evidence_ref` string should be at most 512 characters.

Example entry:

```json
{
  "description": "generated runtime artifacts were written into the source tree",
  "evidence_ref": "file diff: fl_workspace created under project root"
}
```

Reviewer checklist values must be validated against the selected eval case. If
the checklist `skill` or `case_id` does not match the selected evaluation input,
or if `schema_version` is missing or not `"1"`, the evaluator must reject the
checklist with an error and write no runtime process record. Unknown behavior
IDs should be rejected unless the evaluator explicitly records them as
non-scoring notes.

The checklist nests behavior entries under `behavior_evidence` to make reviewer
input easier to read. The runtime record must normalize those entries into the
top-level `mandatory_behavior`, `prohibited_behavior`, and `optional_behavior`
maps shown in the process-record schema.

When both artifacts and a reviewer checklist provide evidence for the same
behavior ID or scalar result field, the initial evaluator must not silently pick
a winner. If the values conflict, reject the evaluation input and write no
runtime process record. Artifacts may fill fields that the checklist omits, and
the checklist may supply fields that cannot be inferred from artifacts.
Identical duplicate values are not conflicts. For list-valued fields such as
`first_pass.violations`, evidence snippets, `significant_violations`, and
`skill_improvements`, normalized duplicate entries are deduplicated and distinct
entries are additive; a conflict exists only when scalar values or statuses for
the same field disagree.

Each evidence string in a runtime record should be at most 512 characters, and
each behavior entry should include at most 10 evidence strings. Longer evidence
belongs in the artifact directory and should be referenced by path. `notes`
fields should be short reviewer summaries, not copied logs.
`first_pass.violations` and `skill_improvements` should each contain at most 10
strings, and each string should be at most 512 characters.

The evaluator output is one JSON record under:

```text
~/.nvflare/agent_skill_eval_runs/<skill>/<case_id>/<timestamp>.json
```

`<timestamp>` must be a lexicographically sortable UTC timestamp with
microseconds, formatted as `YYYYMMDDTHHMMSSffffffZ`, for example
`20260604T153012123456Z`. The evaluator must not overwrite an existing runtime
record. If a path collision occurs, it must generate a fresh timestamp and retry
the write; if it still cannot create a unique path after 5 retries, it
must fail before writing.

The initial evaluator requires `--case <eval-id>`. Omitting `--case`, selecting
an unknown case, or selecting a case whose checklist does not match should return
a JSON error envelope and write no runtime process record. A future `--all`
mode may evaluate every case, but it is not part of the initial contract.
`--artifacts` is optional only when a reviewer checklist supplies all evidence
required by the selected eval case. Without a checklist, `--artifacts` is
required.

Evaluator writes should be atomic: validate inputs first, write to a temporary
file in the destination directory, then rename into place. If evaluation fails
because an artifact is missing, an unknown behavior ID is rejected, disk writing
fails, or another validation error occurs, the evaluator should write no partial
success record. Error details belong in the command's JSON error envelope, not
in a partially completed process record.

The record should use `schema_version` value `"1"` and include:

- `schema_version`, `skill`, `skill_version`, `case_id`, `agent`,
  `source_hash`, and optional `source_commit`. `source_hash` is the skill source
  hash and should be `null` when unavailable; `source_commit` is a separate Git
  commit field when the harness captures one;
- `run_mode`, such as `with_skill`, `without_skill`, or `with_skill_forced`,
  when a comparison run is being performed, otherwise `null`;
- optional `prompt_summary`;
- `mandatory_behavior`, `prohibited_behavior`, and `optional_behavior` maps
  keyed by behavior ID, each with `status`, `evidence`, and `notes`;
- `first_pass`, `final_result`, `eval_passed`, `process_metrics`,
  `significant_violations`, `score`, and `skill_improvements` using the record
  shape above;
- `evaluation` metadata describing evaluator mode, elapsed time, and scoring
  source.

Allowed behavior `status` values are `pass`, `fail`, `missing`,
`not_applicable`, and `non_scoring_note`. Aggregation and reporting commands
must reject unknown status values rather than silently treating them as pass.
Consumers must also reject or clearly surface records with unsupported
`schema_version` values instead of silently interpreting them as the current
schema.

Status meaning depends on behavior category. For mandatory and optional
behaviors, `pass` means evidence of the expected behavior was observed, `fail`
means contradictory evidence was observed, and `missing` means required or
requested evidence was not found. For prohibited behaviors, `pass` means no
evidence of the prohibited behavior was observed, and `fail` means the
prohibited action was detected.

`source_hash` must use the same contract as the released-skill manifest:
lowercase hex-encoded SHA-256 over the sorted files under `skills/<skill>/`.
For each included file, feed the UTF-8 relative path, a NUL byte, the file
contents, and a NUL byte into the single running SHA-256 state. Exclude
`__pycache__`, `.pyc`, and `.pyo` files, and reject symlinks rather than
following them.

`skill_version` should come from the packaged manifest when available, otherwise
from `SKILL.md` frontmatter. If neither source provides it and `--skill-version`
was not supplied, store `null` and keep the record grouped separately from
records with a non-null version.

In the initial implementation, `not_applicable` is not valid for mandatory or
prohibited behavior IDs. Use it only for optional behavior IDs where the evidence
source is genuinely irrelevant to the run. A valid `not_applicable` entry is
excluded from optional evidence summaries and does not count as missing
evidence.

`non_scoring_note` is for reviewer or evaluator observations that should be
preserved but are not behavior IDs from the selected eval case. It is not valid
for canonical mandatory or prohibited behavior IDs. Store these notes in the
record's `optional_behavior` map with `status: "non_scoring_note"` and an ID
that is not treated as a behavior requirement. It has no effect on
`eval_passed`, score caps, or aggregation pass rates.

`eval_passed` is the top-level eval-case result. It is `true` only when the
selected case's required trigger or workflow evidence passes, all mandatory
behavior IDs pass, no prohibited behavior is observed, `final_result.accepted`
is `true`, any validation or simulation requirement for the selected case
passes, `significant_violations` is empty, and evaluator validation completed
without error. Optional behavior does not decide `eval_passed`. `eval_passed`
must be derived from these observable fields, not from `score.value`.

Trigger-only or adjacent-negative cases that do not define behavior ID maps are
valid; they should use empty behavior maps and set `eval_passed` from
`expected_skill`, `negative_for`, assertion, final-result evidence, and explicit
skill-selection evidence. Trigger assertion pass/fail is determined from the
evaluator harness's skill-selection output, explicit tool-call log, or reviewer
checklist evidence; the evaluator must not infer the selected skill from
transcript intent alone.

For trigger cases, `expected_skill` is the skill that should be selected for the
prompt. For adjacent-negative cases, `negative_for` is the skill that must not
be selected. `expected_output` remains guide-compatible prose for human review;
it is not parsed as the source of trigger pass/fail in M7. Guide-compatible
`assertions` are advisory annotations for human review in M7; trigger pass/fail
is derived from `skill_selection` evidence and `nvflare` extension fields only,
not from parsing assertions text. The structured `skill_selection.assertion_passed`
value must be consistent with `selected_skill`, `expected_skill`, and
`negative_for`; inconsistent values are input-validation errors. If only
`expected_skill` is set, `assertion_passed` is true only when
`selected_skill == expected_skill`. If only `negative_for` is set,
`assertion_passed` is true only when `selected_skill != negative_for`. If both
are set, `assertion_passed` is true only when
`selected_skill == expected_skill` and `selected_skill != negative_for`. A case
whose `expected_skill` and `negative_for` are the same skill is invalid.

Trigger-only and adjacent-negative cases still receive a 1-5 `score.value`.
When the expected skill-selection assertion passes on the first pass, no user
correction is needed, and required evidence is present, assign score `5`. If the
assertion is correct only after harmless agent self-correction with no user
correction, score `4` may apply. If user correction is needed but the final
trigger assertion is correct, score `3` may apply. If the wrong skill is
selected, a `negative_for` skill is triggered, or required skill-selection
evidence is unavailable, assign score `1`.

The evaluator should apply behavior semantics conservatively:

- missing evidence for a mandatory behavior fails that behavior;
- observed evidence of a prohibited behavior fails the eval case;
- missing optional behavior is recorded but does not fail the eval case;
- score `5` requires one-shot correct behavior, no meaningful correction, no
  prohibited behavior, and required evidence reported;
- score `4` allows only minor, self-corrected, or harmless issues;
- score `3` requires a functional result but allows user correction for
  workflow, layout, or evidence gaps;
- score `2` is for runnable or partially useful results that violated significant
  workflow, safety, or artifact rules;
- score `1` is for failed, unsafe, or incomplete results.

Score constraints must be deterministic:

- score `5` requires all mandatory behaviors to pass, no prohibited behavior,
  required evidence, first-pass acceptance, final acceptance,
  `user_correction_count == 0`, `agent_self_correction_count == 0`, and no
  layout, workflow, or evidence-gap violations;
- score `4` requires all mandatory behaviors to pass, no prohibited behavior,
  first-pass acceptance, final acceptance, `user_correction_count == 0`, and
  zero layout, workflow, or evidence-gap violations. It may include minor
  harmless issues or agent self-corrections made before the first user-visible
  acceptable result. `first_pass.accepted` must be `true`; if the first
  user-visible pass is rejected, the reason must be recorded in
  `first_pass.violations` and score `4` is not allowed;
- user correction for workflow, layout, or evidence gaps caps the score at `3`;
- if `user_correction_count` or the corresponding violation evidence is
  unavailable, the evaluator must not assign score `4` or `5`;
- if `agent_self_correction_count` is unavailable, the evaluator must not assign
  score `5`;
- missing mandatory evidence caps the score at `3`;
- a final result that is only partially useful or not validated caps the score
  at `2`;
- observed prohibited behavior fails the eval case and caps the score at `2`;
- significant workflow, safety, or artifact-rule violations outside the
  prohibited-behavior list cap the score at `2`;
- unsafe, destructive, or incomplete results are score `1`.

A significant violation is reviewer-supplied evidence of a workflow, safety, or
artifact rule breach serious enough that the result should not be treated as an
acceptable skill run even if it is runnable. In the initial implementation,
`significant_violations` come from the reviewer checklist only. Automated
detection from artifact analysis is deferred. Examples include writing generated
runtime artifacts into the user's source tree after the skill requires `/tmp` or
a generated-job folder, bypassing an approval checkpoint, exposing sensitive
local paths or secrets in generated artifacts, or modifying files outside the
declared blast radius.

When multiple constraints apply, the lowest applicable score or cap wins.

`score.rationale` should be generated from deterministic templates, for example:

| Score | Rationale template |
| --- | --- |
| 5 | `One-shot correct; required evidence present; no user or agent correction recorded.` |
| 4 | `Accepted first pass with no user correction; agent self-correction or harmless issue recorded.` |
| 3 | `Functional result accepted, but user correction or missing mandatory evidence capped the score.` |
| 2 | `Runnable or partially useful result, but validation/prohibited/significant-violation cap applied.` |
| 1 | `Failed, unsafe, wrong-trigger, or incomplete result.` |

The evaluator may append one short cap reason, keeping the final rationale within
512 characters.

The evaluator should not invent token usage, infer hidden agent intent, or
retroactively excuse missing evidence. If token counts are unavailable from the
agent runtime, the record should store `null` and let `nvflare agent skills
performance` report it as unavailable.

`final_result.validation_passed` and `final_result.simulation_passed` are
case-specific booleans. They should be `true` or `false` only when the selected
case requires that kind of validation evidence, and `null` when the field is not
applicable or not tracked for the skill. Non-conversion skills should use
`final_result.accepted` plus skill-specific mandatory behavior evidence rather
than forcing simulation-specific fields.

The read-only reporting command is:

```bash
nvflare agent skills performance [--skill <name>] [--case <eval-id>] [--records <path>] [--format json]
```

It reports the packaged process-metric contract for each skill. The packaged
process-metric contract is the `nvflare.process_evaluation.metrics` entries in
the packaged skill's `evals/evals.json`. When runtime records are supplied, the
command aggregates eval pass rate, process score, elapsed conversion or
diagnosis time, token usage, correction count, and quality metrics. The command
must not run skills, run the evaluator, call an LLM, infer token usage from
transcript text, or mutate records. If `--records` is omitted, it reads the
default `~/.nvflare/agent_skill_eval_runs` location when present. Human output
should use a compact table and simple text bars so a reviewer can quickly
compare skill performance; JSON output should preserve the underlying numeric
fields for automation.

Default aggregation reads all valid records matching the filters and sorts them
by timestamp descending. Aggregate numeric summaries are grouped by `skill`,
`skill_version`, and `case_id`; `run_mode` and source hash are included in the
group key only for records where they are non-null. Records from different skill
versions, different non-null run modes, or different non-null source hashes
should not be averaged together. Records with null `run_mode` or null source
hash are grouped without that dimension rather than under a literal null value.
Numeric averages exclude `null` values and report both the number of available
values and the number of unavailable values. JSON output should include grouped
summaries and `records` entries that are compact summaries of the matching
records, not full copied process records.
`eval_pass_rate` is `(count of records where eval_passed is true) /
record_count` for the group. Since `eval_passed` is always a boolean and never
`null`, it is reported as a plain float rather than the `{avg, available,
unavailable}` shape used for nullable metrics.

If no runtime records match, `nvflare agent skills performance` should exit
successfully, report the packaged metric contracts, and return empty `summaries`
and `records` arrays. This is the expected Milestone 6 state before runtime
evidence exists.

Example JSON output shape:

```json
{
  "schema_version": "1",
  "status": "ok",
  "records_root": "~/.nvflare/agent_skill_eval_runs",
  "filters": {
    "skill": "nvflare-convert-pytorch",
    "case_id": "pytorch-convert-basic"
  },
  "metric_contracts": [
    {
      "skill": "nvflare-convert-pytorch",
      "case_id": "pytorch-convert-basic",
      "metrics": [
        {"id": "user_correction_count", "description": "number of user corrections needed after the first pass"}
      ]
    }
  ],
  "summaries": [
    {
      "skill": "nvflare-convert-pytorch",
      "skill_version": "0.1.0",
      "case_id": "pytorch-convert-basic",
      "run_mode": "with_skill",
      "source_hash": "cc84428d014be112e254420a92b6497d3b11cbd5a67b263e56ebd0a4df18e00d",
      "record_count": 3,
      "eval_pass_rate": 1.0,
      "score": {"avg": 4.67, "available": 3, "unavailable": 0},
      "elapsed_seconds": {"avg": 544.6, "available": 3, "unavailable": 0},
      "token_count": {"avg": 2690000, "available": 3, "unavailable": 0},
      "conversion_quality": {"avg": 4.33, "available": 3, "unavailable": 0}
    },
    {
      "skill": "nvflare-diagnose-job",
      "skill_version": "0.1.0",
      "case_id": "diagnose-component-authz",
      "record_count": 1,
      "eval_pass_rate": 1.0,
      "score": {"avg": 5.0, "available": 1, "unavailable": 0}
    }
  ],
  "records": [
    {
      "path": "~/.nvflare/agent_skill_eval_runs/nvflare-convert-pytorch/pytorch-convert-basic/20260604T153012123456Z.json",
      "timestamp": "20260604T153012123456Z",
      "skill": "nvflare-convert-pytorch",
      "case_id": "pytorch-convert-basic",
      "eval_passed": true,
      "score": {"value": 5, "max": 5}
    }
  ]
}
```

This reporting command only summarizes records that a runtime evaluator,
scripted harness, or reviewer checklist has already written.

The initial implementation may use a checklist-style evaluator before a fully
automated harness exists. The checklist still writes the same JSON record and
uses the same rubric, so later automation can consume and compare records
without changing `nvflare agent skills performance`.

## Auto-FL Research Evaluation

Auto-FL is a research evaluation consumer, not an initial release canary. The FLARE
research team already has Auto-FL workflows. Those workflows should be reused
as repeatable test cases for whether the new skills improve agent behavior.

Recommended comparison modes:

| Mode | Purpose |
| --- | --- |
| `without_skill` | baseline agent behavior with no FLARE skill loaded |
| `with_skill` | same task with relevant FLARE skills available |
| `with_skill_forced` | diagnostic mode that names one skill explicitly to isolate skill content from trigger selection |

Auto-FL evaluation should measure task success, validation score, missed
mandatory behavior, prohibited actions, runtime, tool calls, and token/cost data
when available. Results should feed skill improvements, helper scripts, and
future eval cases. They should not block release or publication handoff
unless a separate release-gate decision is made later.

Auto-FL-specific artifacts should remain in the research project. FLARE skills
should not define Auto-FL queue state, retry policy, routing, persistence, or
run resumption.

## Publication Handoff Boundary

External publication is separate `github.com/NVIDIA/skills` integration work.
This evaluation spec owns the FLARE side of the handoff:

- guide-compatible `SKILL.md`;
- references, scripts, assets, and eval inputs;
- initial lint and engineering-test evidence;
- runtime skill-performance summary in `BENCHMARK.md` when available;
- FLARE release and skill source/version information.

The public NVIDIA skill scoreboard, catalog sync, public installer metadata,
signing, and publication UI are outside this NVFLARE design. FLARE should
provide artifacts that the company-wide process can consume, but should not own
the public scoreboard mechanics.

## Workstreams

- Add the initial skill lint entry point for frontmatter, size, trigger, overlap,
  category drift, global negative, policy coverage, process evaluation, command
  drift, helper scripts, fixtures, and doc crosslinks.
- Add engineering tests for native install, CLI JSON envelopes, inspect safety,
  doctor read-only behavior, and helper-script contracts.
- Add the first guide-compatible `evals/evals.json` files with
  `nvflare.mandatory_behavior`, `nvflare.prohibited_behavior`, and
  `nvflare.process_evaluation.metrics` extensions.
- Add the initial runtime evaluator or reviewer-checklist entry point that
  consumes `evals/evals.json`, observed run artifacts, and the process-score
  rubric to write runtime process records when evaluation mode is on.
- Add short `BENCHMARK.md` summaries for public-candidate skills.
- Reuse Auto-FL research workflows as an advisory evaluation environment after
  the first skills exist.
