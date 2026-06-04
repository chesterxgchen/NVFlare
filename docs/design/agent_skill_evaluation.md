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

The initial goal is narrower: every public FLARE skill must have enough measurement
to answer:

- Did the right prompt trigger the right skill?
- Did adjacent or unrelated prompts avoid the wrong skill?
- Did the agent follow mandatory instructions?
- Did the agent avoid prohibited actions?
- Did the task produce the expected validation evidence or artifact?
- Do referenced `nvflare` commands still exist for the target release?

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
            {"id": "first_pass_layout_violations", "description": "count of generated layout or artifact-location mistakes found before final acceptance"}
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

The IDs are stable labels, not metrics by themselves. The runtime evaluator or
reviewer checklist maps each ID to concrete evidence and records pass/fail for
that eval case.

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
/tmp/nvflare/skill_eval_runs/<skill>/<case_id>/<timestamp>.json
```

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
| `skill-global-negative-lint` | unrelated global negative prompts are missing or can trigger a FLARE skill | shared global negative prompt bank and per-skill `evals/evals.json` | Require coverage for prompts that should trigger no FLARE skill, such as unrelated web, Kubernetes-only, or generic coding tasks. The initial implementation may validate required negative eval entries; later runtime scoring can execute them. |
| `skill-policy-coverage-lint` | normative words appear without a nearby measurable behavior ID, deterministic helper test, or checklist item | `SKILL.md`, `references/`, helper tests, and `evals/evals.json` | Flag normative words such as `must`, `must not`, `required`, `prohibited`, and `approval` unless the rule maps to `nvflare.mandatory_behavior`, `nvflare.prohibited_behavior`, a deterministic helper test, or a release checklist item. |
| `skill-process-eval-lint` | missing process-evaluation metrics for a public skill, or malformed process metric entries | `evals/evals.json` | Require at least one `nvflare.process_evaluation.metrics` entry for every public skill. Each metric must have a stable `id` and `description` so runtime runs can record first-pass quality, correction count, unwanted actions, validation evidence completeness, and related process outcomes. |
| `skill-command-drift-lint` | referenced `nvflare` commands, flags, or JSON examples do not match the installed CLI or exported command schema | `SKILL.md`, `references/`, `scripts/`, CLI parser/schema output | Verify each referenced `nvflare` command, flag, and JSON example against the installed CLI or exported `--schema` output so stale commands fail before release. |
| `skill-helper-script-lint` | helper scripts lack tests or violate JSON stdout/stderr conventions | `skills/<skill>/scripts/` and tests | Require tests for shipped helper scripts, require machine-readable stdout when JSON output is promised, require diagnostics on stderr, and fail when a public skill calls a helper script marked as promoted to a product CLI command. |
| `skill-fixture-lint` | file-editing evals lack required `evals/files/` inputs or fixture source notes | `evals/evals.json`, `evals/files/`, and fixture notes | Ensure file-editing or artifact-producing evals reference existing deterministic input files under `evals/files/` and include source/provenance notes for fixtures. |
| `agent-doc-crosslink-lint` | design-doc links, lint IDs, or command references are stale | agent design docs and implementation plan | Resolve internal markdown links and anchors, verify referenced lint IDs and command names have canonical definitions, and fail on stale cross-document references. |

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
  "case_id": "ames-pytorch-fedavg-conversion",
  "skill": "nvflare-convert-pytorch",
  "skill_version": "0.1.0",
  "prompt_summary": "Convert AMES PyTorch code to FedAvg simulation with 2 sites",
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
  "process_metrics": {
    "turns_to_acceptable": 4,
    "user_correction_count": 3,
    "agent_self_correction_count": 1,
    "layout_violations": 3,
    "validation_commands_run": 5,
    "unnecessary_files_created": 4
  },
  "score": {
    "value": 3,
    "max": 5,
    "rationale": "Functional conversion, but several workflow/layout mistakes required user correction."
  },
  "skill_improvements": [
    "add generated-job folder rule",
    "require client.py/job.py/model.py",
    "default export/workspace/results to /tmp/nvflare"
  ]
}
```

Initial process score rubric:

| Score | Meaning |
| --- | --- |
| 5 | One-shot correct, no user correction, required evidence reported. |
| 4 | Minor issue, self-corrected or harmless, no meaningful user correction. |
| 3 | Functional result, but user correction was needed for workflow, layout, or evidence gaps. |
| 2 | Runnable or partially useful result, but violated important workflow, safety, or artifact rules. |
| 1 | Failed, unsafe, or incomplete result. |

The feedback loop is:

1. Run a realistic task with the skill enabled.
2. Record first-pass violations and correction count.
3. Score process quality separately from task metrics.
4. Add only the missing guardrails to `SKILL.md`, `references/`, helper scripts,
   or deterministic lints.
5. Add or update eval assertions and process metrics.
6. Re-run and verify correction count drops.

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
- Add short `BENCHMARK.md` summaries for public-candidate skills.
- Reuse Auto-FL research workflows as an advisory evaluation environment after
  the first skills exist.
