# NVFLARE Agent Skills Initial Implementation Plan

## Document Control

| Field | Value |
| --- | --- |
| Created date | 2026-05-26 |
| Updated date | 2026-06-04 |
| Status | Ready for Implementation |
| Sources | [Agent Integration](agent_integration.md), [Agent Skill Authoring](agent_skill_authoring.md), [Agent Skill Evaluation](agent_skill_evaluation.md), and the temporary deferred-roadmap planning note |
| Scope | First implementation cut for native NVFLARE agent skills |
| Out of scope | Public NVIDIA skills catalog mechanics, public scoreboard ownership, Node/npm/npx installer dependency, Auto-FL product roadmap, and deferred roadmap items |

## Intent

This plan implements the simplified initial design. Deferred mechanisms such as
receipts, provenance, durable workflow state, transcript replay, workspace
cleanup, full lifecycle commands, compatibility shims, PR-bot automation, and
the large policy catalog are intentionally not part of this plan. They live in
the temporary deferred-roadmap planning note.

The core test split is:

- Engineering correctness: unit, CLI, package, helper-script, lint, and release
  tests that can block NVFLARE CI/release.
- Runtime agent performance: trigger correctness, instruction following,
  prohibited-action avoidance, task validation, and benchmark notes that can
  block public skill promotion.

Do not report normal engineering tests as runtime skill-performance metrics.

## First Implementation Cut

The first useful slice is:

- `nvflare agent skills install --agent codex|claude [--skill <name>]
  [--dry-run] [--format json]`;
- `nvflare agent skills list --agent codex|claude --format json`;
- `nvflare agent skills performance [--skill <name>] [--case <eval-id>]
  [--records <path>] [--format json]` as a read-only process-evaluation
  summary;
- packaged skills copied from repo-root `skills/` into the NVFLARE wheel;
- minimal released-skill manifest with name, version/source hash, and
  FLARE-version compatibility;
- `nvflare agent inspect <path> --format json`;
- `nvflare agent doctor [--online] --format json`;
- guide-compatible skill layout under `skills/<skill>/`;
- initial lints for frontmatter, size, trigger boundaries, trigger overlap,
  catalog category, global negatives, policy coverage, command drift, helper
  scripts, fixtures, and doc crosslinks;
- at least one public-candidate skill, preferably `nvflare-orient` or
  `nvflare-convert-pytorch`, with `evals/evals.json` and a short
  `BENCHMARK.md`.

## Milestone Summary

| Milestone | Theme | Blocks Native Package Mechanics | Required Before First Agent-Skills Release |
| --- | --- | --- | --- |
| 0 | CLI envelope and `nvflare agent` command group | Yes | Yes |
| 1 | Skill source layout and minimal frontmatter validator | Yes | Yes |
| 2 | Wheel manifest and packaging | Yes | Yes |
| 3 | Native skill install/list | Yes | Yes |
| 4 | Read-only inspect and doctor | Yes | Yes |
| 5 | Initial skill lint and admission gate | Yes | Yes |
| 6 | Seed skill bundle | Yes | Yes |
| 7 | Runtime evaluator, eval summaries, and optional Auto-FL research runs | Internal skill-quality gate, not NVFLARE package mechanics | Yes |
| 8 | Customer lifecycle skill wave | No | Yes |
| 9 | Framework conversion skill wave | No | Yes |
| 10 | Specialized workflow skill wave | No | Yes |
| 11 | PET and security skill wave | No | Yes |
| 12 | Export manifest and fingerprint | Yes | Yes |
| 13 | Manifest-aware inspect and preflight | Yes | Yes |
| 14 | External publication handoff artifacts | No | Yes; final handoff gate |

The first native agent-skills release is not complete until the runtime
evaluator and follow-on skill waves are done. Runtime evaluation follows the
seed bundle and gates the later skill waves so one or a small number of skills
can be corrected before the same mistakes are copied across the catalog. It is
an internal quality gate, not an external publication step. Publication handoff
remains Milestone 14 because it packages the already evaluated release
artifacts.

## Initial PR Sequence

The first implementation PRs should stay small and map directly to the
milestones:

1. `nvflare/tool/agent/` skeleton plus reusable JSON envelope helper.
2. Repo-root `skills/` directory plus minimal `SKILL.md` frontmatter validator.
3. Wheel skill manifest plus packaging changes that include released skills in
   the built wheel.
4. Native `nvflare agent skills install/list` for `codex` and `claude`.
5. Read-only `nvflare agent inspect` and `nvflare agent doctor`.

This sequence combines the milestone breakdown with the review recommendation
to avoid bundling source layout, validation, manifest generation, and wheel
packaging into one large PR.

`nvflare agent skills performance` is part of the first useful release surface,
but it lands with the seed-skill bundle in Milestone 6 rather than in the
initial package-mechanics PR sequence.

## Milestone 0: CLI Envelope

Deliverables:

- Add `nvflare agent` command registration.
- Add shared JSON envelope helper with `schema_version`, `status`, `code`,
  `message`, `hint`, optional `recovery_category`, optional `suggested_skill`,
  and command-specific `data`.
- Define initial agent error codes: `INVALID_ARGS`, `CASE_REQUIRED`,
  `UNKNOWN_SKILL`, `UNKNOWN_CASE`, `EVIDENCE_REQUIRED`,
  `CHECKLIST_SCHEMA_INVALID`, `CHECKLIST_MISMATCH`, `INVALID_BEHAVIOR_ID`,
  `INVALID_STATUS`, `CONFLICTING_EVIDENCE`, `ARTIFACT_NOT_FOUND`,
  `RECORD_WRITE_FAILED`, and `UNSUPPORTED_SCHEMA_VERSION`.
- Add `--format json`, `--format jsonl` for streaming commands where needed,
  and `--schema` conventions for agent-facing commands.

Engineering tests:

- JSON success/error envelope tests.
- stdout/stderr separation tests.
- `--schema` tests that do not require operational arguments.
- non-interactive command tests.

## Milestone 1: Skill Source and Frontmatter

Deliverables:

- Add repo-root `skills/` with guide-compatible structure.
- Add minimal frontmatter validation for `name`, `description`,
  `min_flare_version`, and `blast_radius`.
- Add at least one fixture skill for validator tests.

Engineering tests:

- frontmatter parsing;
- directory-name and skill-name matching;
- required-field failures;
- invalid `blast_radius` fixture.

## Milestone 2: Wheel Manifest and Packaging

Deliverables:

- Add a minimal released-skill manifest with skill name, source hash or version,
  and FLARE-version compatibility.
- Define the source-hash contract for released skills: lowercase hex-encoded
  SHA-256 over sorted files under `skills/<skill>/`. For each included file,
  feed the UTF-8 relative path, a NUL byte, file contents, and a NUL byte into
  the single running SHA-256 state. Exclude `__pycache__`, `.pyc`, and `.pyo`
  files, and reject symlinks rather than following them.
- Update the active build backend configuration, such as `pyproject.toml`,
  `setup.py`, or package-data rules, so the wheel actually includes released
  skill files and the manifest.

Engineering tests:

- source-vs-wheel manifest checks;
- source hash/manifest validation;
- package contents check.

## Milestone 3: Native Install/List

Deliverables:

- Implement `nvflare agent skills install --agent codex|claude`.
- Implement `--skill`, `--dry-run`, `--format json`, and conflict reporting.
- Resolve `codex` to `$CODEX_HOME/skills` or `~/.codex/skills`.
- Resolve `claude` to `~/.claude/skills`.
- If `$CODEX_HOME` is set but the path does not exist, create only the
  `$CODEX_HOME/skills` path needed for installation after normal dry-run and
  conflict checks; report the resolved path in JSON output.
- Implement `nvflare agent skills list --agent codex|claude --format json`.
- Limit `skills list` conflicts to name-overlap conflicts with available
  NVFLARE-source skills or managed NVFLARE installs. Unrelated third-party
  skills already present in the target directory must not appear as conflicts.
- Ensure install does not require Node.js, npm, npx, network access, or an
  external skill CLI.

Engineering tests:

- `native-skill-install-no-node`;
- `skill-install-codex-claude-targets`;
- `skill-install-all-by-default`;
- `skill-install-safe-overwrite`;
- `skill-install-no-third-party-download`;
- `skill-list-ignores-unrelated-third-party-skills`;
- `skill-list-flags-name-overlap-external-skill`.

## Milestone 4: Inspect and Doctor

Deliverables:

- Implement read-only `nvflare agent inspect <path> --format json`.
- Implement static framework and FLARE-integration detection without importing
  or executing user code.
- Implement read-only `nvflare agent doctor --format json`.
- Add optional `doctor --online` bounded read-only checks through the active
  startup-kit context.

Engineering tests:

- static-only inspect fixtures with import side effects;
- redaction fixtures for secrets and sensitive paths;
- symlink and traversal cap fixtures;
- doctor read-only before/after checks.

## Milestone 5: Initial Lints and Admission Gate

Deliverables:

- Add `tools/agent_skill_checks/` or equivalent local entry point.
- Implement lints:
  `skill-frontmatter-lint`, `skill-md-size-lint`, `skill-trigger-lint`,
  `skill-trigger-overlap-lint`, `skill-catalog-category-lint`,
  `skill-global-negative-lint`, `skill-policy-coverage-lint`,
  `skill-command-drift-lint`, `skill-helper-script-lint`,
  `skill-fixture-lint`, and `agent-doc-crosslink-lint`.
- Add the shared global negative prompt bank at
  `skills/_shared/global_negative_prompts.json` with `schema_version: "1"` and
  `prompts` entries containing `id`, `prompt`, and `description`.
- Treat [Agent Skill Evaluation](agent_skill_evaluation.md#initial-engineering-lints)
  as the canonical lint behavior definition; the implementation plan should not
  restate each lint's inputs and pass/fail semantics.
- Implement release checklist coverage only from machine-readable
  `evals/release_checklist.json`; prose-only checklist mentions do not satisfy
  policy coverage lint.
- Implement command-drift lint by parsing `nvflare` snippets from skill docs and
  checking commands/flags against the installed CLI parser or exported command
  schema in the same checkout or wheel.
- Keep `evals/evals.json` guide-compatible and put FLARE-specific IDs under
  `nvflare.mandatory_behavior`, `nvflare.optional_behavior`, and
  `nvflare.prohibited_behavior`.
- Follow the example and behavior-ID pass/fail semantics in
  [Agent Skill Evaluation](agent_skill_evaluation.md#guide-compatible-eval-structure):
  mandatory IDs require evidence, prohibited IDs fail when observed, and
  optional IDs are recorded but non-blocking.
- Treat the 200-line `SKILL.md` limit as the hard initial lint. The roughly
  2,000-token target is advisory and can be reported with a simple
  whitespace-based estimate unless a tokenizer is standardized later.
- Emit lint findings with a shared shape: `id`, `severity`, `file`, `line`
  when available, `message`, and `hint`.

Engineering tests:

- lint fixtures for pass/fail cases;
- trigger-overlap lint fixtures with same-category overlap, adjacent-negative
  coverage, and unrelated-category non-overlap cases;
- CLI command-schema drift fixtures;
- global negative bank schema fixtures and per-skill global-negative coverage
  fixtures;
- doc crosslink fixtures for valid links, stale anchors, stale lint IDs, and
  stale command names.

## Milestone 6: Seed Skill Bundle

Deliverables:

- Add the first hand-vetted public-candidate skills.
- Keep each `SKILL.md` under the 200-line or roughly 2,000-token target.
- Move long content into `references/`.
- Add `evals/evals.json`, minimal `evals/files/` when needed, and a
  hand-authored `BENCHMARK.md` summarizing manual trigger checks, mandatory
  behavior checks, prohibited behavior checks, and known gaps.
- Add read-only `nvflare agent skills performance` reporting so reviewers can
  see the packaged process-metric contract and, when runtime process records
  exist, summarize score, elapsed time, token count, correction count, and
  conversion quality without running skills or inferring missing metrics.
  Milestone 6 only needs the command surface, packaged metric-contract display,
  empty-record summaries, and basic record-summary rendering. Full runtime
  record grouping, filtering, unavailable-count accounting, and schema-version
  rejection land in Milestone 7 with the evaluator.

Recommended first skills:

- `nvflare-orient`;
- `nvflare-convert-pytorch`;
- `nvflare-diagnose-job`.

Exit criteria:

- each public-candidate skill passes the initial admission gate;
- commands referenced by skills match the installed CLI;
- each skill has at least one positive trigger and one adjacent negative eval;
- public-candidate skills pass global negative trigger checks.
- `BENCHMARK.md` clearly states whether the skill is public-ready based on
  manual initial checks or still draft/internal pending Milestone 7 evaluation.
- `nvflare agent skills performance` can render both human-readable summaries
  and JSON output for seed skills, including empty-record summaries when no
  runtime evidence has been collected yet.

## Milestone 7: Runtime Evaluator and Auto-FL Research

Deliverables:

- Add an initial checklist-first runtime evaluator that consumes
  `skills/<skill>/evals/evals.json` plus reviewer checklist evidence and
  optional structured artifacts, maps `nvflare.mandatory_behavior`,
  `nvflare.prohibited_behavior`, and `nvflare.optional_behavior` IDs to
  evidence, applies the 1-5 process rubric from
  [Agent Skill Evaluation](agent_skill_evaluation.md#runtime-process-evaluation),
  and writes runtime process records under
  `~/.nvflare/agent_skill_eval_runs/<skill>/<case_id>/<timestamp>.json`.
- Keep evaluation mode binary:
  - `off`: normal skill use or raw artifact collection only; no score and no
    process record required.
  - `on`: produce a runtime process record from observed evidence and the
    predefined rubric.
- Make activation explicit: normal skill use is off; invoking
  `nvflare agent skills evaluate` is on; scripted harnesses turn evaluation on
  by invoking the same evaluator entry point after collecting artifacts.
- Document and implement the agent/harness convention
  `NVFLARE_SKILL_EVAL=on`: installed skills and scripted harnesses should check
  this environment variable before creating process-evaluation artifacts. When
  unset, agents should collect only task evidence needed for the user-facing
  result and should not create behavior maps, correction counters, checklist
  data, or other evaluation-only artifacts. When set to `on`, and when a
  matching eval case and bounded artifact or checklist evidence are available,
  call `nvflare agent skills evaluate` before the final response. The NVFLARE
  CLI itself does not read this variable. If the variable is unset, or if the
  case/evidence is unavailable, no process record is required. Harnesses may set
  `NVFLARE_SKILL_EVAL_CASE=<eval-id>` to avoid case selection ambiguity. If it
  is unset, installed skills may inspect `evals/evals.json` and select a case
  only when task context maps unambiguously to one case. Harnesses that run
  baseline and skill-assisted comparisons should pass explicit `--run-mode`
  values so summaries group the records separately.
- Do not add an LLM judge, human runtime mode, or agent self-scoring mode in
  this milestone. Agent-authored notes may be evidence, but the evaluator or
  reviewer checklist assigns the score from the documented rubric.
- Record evaluator cost separately from skill-run cost when timing or tokens are
  available. Skill-run `elapsed_seconds` and `token_count` must not silently
  include evaluator overhead.
- Add reviewer-checklist JSON input support for evidence that cannot yet be
  inferred from files or command logs. The checklist input must follow the
  schema defined in
  [Agent Skill Evaluation](agent_skill_evaluation.md#runtime-evaluator-and-records):
  `schema_version` value `"1"`, `skill`, `case_id`, `behavior_evidence`,
  `process_metrics`, `skill_selection`, `first_pass`, `final_result`, and
  `skill_improvements`, with no final score supplied by the checklist. Allow a
  `significant_violations` evidence list for reviewer-supplied workflow, safety,
  or artifact-rule violations outside the prohibited-behavior list. Each entry is
  an object with bounded `description` and `evidence_ref` strings. Automated
  detection of significant violations from artifact analysis is deferred.
- Add an evaluator entry point. The preferred first implementation is a
  product CLI command:
  `nvflare agent skills evaluate --skill <name> --case <eval-id>
  [--agent codex|claude|other|unknown]
  [--run-mode without_skill|with_skill|with_skill_forced]
  [--skill-version <version>] [--artifacts <path>] [--checklist <path>]
  [--records <path>] --format json`.
  At least one of `--artifacts` or `--checklist` is required. `--artifacts` is
  optional only when the reviewer checklist supplies all evidence required by
  the selected eval case. On success, stdout is a JSON envelope whose `data`
  includes `record_path` and the full runtime process `record`.
  `--case` is required for the initial implementation. Omitting it, selecting
  an unknown case, or selecting a case whose checklist does not match must return
  a JSON error envelope and write no runtime process record.
  `--records` is a records root directory. The evaluator writes
  `<records>/<skill>/<case_id>/<timestamp>.json`, where `<timestamp>` is the
  UTC microsecond format defined in
  [Agent Skill Evaluation](agent_skill_evaluation.md#runtime-evaluator-and-records).
  The default `~/.nvflare/agent_skill_eval_runs` location is the local durable
  records root; CI or benchmark workflows may pass an explicit `--records` path
  when records must be archived under a job workspace or collected by CI.
  If CLI surface is deferred, add an internal tool with the same arguments and
  JSON output shape, then promote it later.
- For the first evaluator pass, derive behavior IDs from the selected case in
  the skill's `evals/evals.json`. Do not hard-code a separate behavior-ID list
  in the evaluator or implementation plan. For `nvflare-convert-pytorch`, cover
  the behavior IDs that are actually present in its shipped `evals/evals.json`,
  including trigger-only and adjacent-negative cases that may have empty
  behavior maps.
- Do not infer behavior status from unstructured transcripts, patches, or
  generated files in M7. If `--artifacts` is supplied, parse only structured
  `run.json` and `evidence.json`; treat `commands.jsonl`, `diff.patch`, and
  `files/` as referenced evidence for human review.
- Define the runtime record schema fields:
  `schema_version` value `"1"`, `skill`, `skill_version`, `case_id`, `agent`,
  `run_mode`, `source_hash`, optional `source_commit`, optional
  `prompt_summary`, behavior result maps, `first_pass`, `final_result`,
  `eval_passed`, `process_metrics`, `significant_violations`, `score`,
  `skill_improvements`, and `evaluation`. The initial
  `evaluation.scoring_source` value is `agent_skill_evaluation:v1`.
- Compute `source_hash` with the same contract as the released-skill manifest:
  lowercase hex SHA-256 over sorted files under `skills/<skill>/`, feeding each
  relative path, a NUL byte, file contents, and a NUL byte into the single
  running SHA-256 state; exclude
  `__pycache__`, `.pyc`, and `.pyo` files; reject symlinks.
- Treat behavior IDs as scoped to the selected skill and eval case, not globally
  unique across all skills.
- Validate behavior status values against the design enum: `pass`, `fail`,
  `missing`, `not_applicable`, and `non_scoring_note`. Apply category-specific
  semantics: mandatory/optional `pass` means expected evidence was observed;
  prohibited `pass` means no prohibited evidence was observed;
  `not_applicable` is valid only for optional irrelevant evidence and is invalid
  for mandatory or prohibited IDs; `non_scoring_note` is invalid for canonical
  mandatory or prohibited IDs, is stored in the record's `optional_behavior` map,
  and has no score effect.
- Store only bounded, sanitized evidence snippets or artifact references in
  runtime records. Do not copy unbounded transcripts, large command outputs,
  secrets, credentials, private keys, access tokens, or sensitive absolute paths
  into process records. Enforce the design's evidence-entry bounds and use
  artifact references for larger evidence.
- Treat `--artifacts` as trusted evaluator input. Do not claim artifact
  integrity or chain-of-custody validation in this milestone.
- Reject conflicting artifact-derived and reviewer-checklist evidence instead
  of silently preferring one source. Artifacts may fill fields omitted by the
  checklist, and the checklist may supply fields unavailable from artifacts.
- Validate all inputs before writing, write records atomically, and write no
  partial success record on missing artifacts, unknown rejected behavior IDs,
  disk-write failures, or other validation errors.
- Apply the deterministic score constraints from the design doc, including
  score caps for user corrections, missing mandatory evidence, observed
  prohibited behavior, partial or unvalidated final results, and unsafe or
  incomplete results. When multiple constraints apply, the lowest applicable
  score or cap wins. Do not assign score 4 or 5 when
  `user_correction_count` or the corresponding layout/workflow or evidence-gap
  evidence is unavailable. Score 5 requires
  `agent_self_correction_count == 0`; score 4 requires
  `first_pass.accepted == true`, user correction count zero, and no missed
  instructions, layout violations, workflow violations, or evidence-gap
  violations. Cap significant workflow, safety, or artifact-rule violations
  outside the prohibited-behavior list at score 2 and set `eval_passed` false.
- Derive `eval_passed` from observable trigger/workflow evidence, behavior
  status maps, final-result fields, significant violations, and evaluator
  validation outcome. Do not derive `eval_passed` from `score.value`.
- For trigger-only and adjacent-negative cases with empty behavior maps, assign
  score from the trigger assertion result: score 5 for first-pass correct
  selection with required evidence, score 4 for harmless self-correction without
  user correction, score 3 when user correction is needed but the final trigger
  assertion is correct, and score 1 when the wrong skill is selected, a
  `negative_for` skill is triggered, or required skill-selection evidence is
  unavailable.
- For compound trigger cases with both `expected_skill` and `negative_for`, treat
  the assertion as passing only when `selected_skill == expected_skill` and
  `selected_skill != negative_for`; reject cases where both fields name the same
  skill.
- Validate `selected_skill`, `expected_skill`, and `negative_for` as strings or
  `null`. Support `negative_for: "*"` only for global-negative cases where no
  FLARE skill should be selected; treat it as passing only when `selected_skill`
  is JSON `null` or strips to `""`, `"none"`, `"no_skill"`, or `"null"`.
- Validate `score.value` as an integer 1 through 5, `score.max` as exactly 5,
  and `score.rationale` as a required bounded string generated from documented
  deterministic templates plus an optional short cap reason.
- Use the same 1-5 scale for `process_metrics.conversion_quality` as the
  process score rubric. It measures generated artifact quality rather than the
  whole process, and should be `null` when the case does not provide enough
  evidence to score conversion quality.
- Ensure `nvflare agent skills performance` remains read-only aggregation. It
  must not run the evaluator, infer scores from raw artifacts, call an LLM, or
  mutate records.
- Implement the documented aggregation semantics for `skills performance`: sort
  records by timestamp descending, group numeric summaries by `skill`,
  `skill_version`, `case_id`, non-null `run_mode`, and non-null source hash when
  available, omit `run_mode` or source hash from the group key when either is
  null, exclude `null` values from averages while reporting available and
  unavailable counts, support the `--case <eval-id>` filter, emit the documented
  JSON output shape, and reject unsupported `schema_version` values.
- Add the explicit benchmark-rendering command:
  `nvflare agent skills benchmark --skill <name> [--case <eval-id>]
  [--records <path>] [--output <path>] [--dry-run] [--format json]`.
  `--skill` is required. The command consumes `skills performance` summaries and
  renders a reviewable Markdown draft. It is mutating only when `--dry-run` is
  omitted. It must not run skills, run the evaluator, parse raw artifacts, call
  an LLM, infer missing metrics, or mutate runtime process records.
- Use `skills benchmark` to upgrade `BENCHMARK.md` from manual initial
  summaries to runtime summaries when automated or repeated eval evidence
  exists. If `--output` is omitted, write `BENCHMARK.md` in the selected skill
  directory. The rendered file is a publication/review draft; runtime records
  remain the raw evidence and `skills performance` remains the current computed
  view.
- Consume runtime process records with `nvflare agent skills performance` to
  visualize process score, conversion time, token usage, correction count,
  task-quality fields, and known improvement items before updating
  `BENCHMARK.md`.
- Measure positive trigger, negative trigger, mandatory behavior,
  prohibited behavior, and task validation for the seed skills before expanding
  to additional skill waves.
- Reuse Auto-FL research workflows as advisory evaluation scenarios after the
  relevant skills exist.

Engineering tests:

- evaluator loads a skill's `evals/evals.json`, selects one case, and rejects
  unknown skill/case IDs with JSON envelope errors;
- seed skills document the `NVFLARE_SKILL_EVAL=on` post-run convention,
  optional `NVFLARE_SKILL_EVAL_CASE=<eval-id>` case selection, and do not claim
  that the NVFLARE CLI reads the variables directly;
- evaluator rejects omitted `--case` with a JSON envelope error and writes no
  process record;
- evaluator supports trigger-only or adjacent-negative cases with empty behavior
  maps by deriving `eval_passed` from `expected_skill`, `negative_for`, assertion,
  final-result evidence, and explicit `skill_selection` evidence from
  `run.json`, `evidence.json`, or reviewer checklist rather than inferred
  transcript intent;
- evaluator assigns trigger-only and adjacent-negative scores according to the
  documented trigger assertion rules, including score 5 for first-pass correct
  selection and score 1 for wrong-skill or missing skill-selection evidence;
- evaluator validates compound `expected_skill` plus `negative_for` trigger
  cases, including the invalid same-skill case;
- evaluator rejects non-string, non-null `selected_skill`, `expected_skill`, and
  `negative_for` values;
- evaluator validates `negative_for: "*"` global-negative cases, including a
  passing no-skill-selected case;
- evaluator writes a process record under the requested records directory and
  preserves the documented schema, including UTC microsecond timestamped output
  paths and no overwrite on path collision;
- evaluator emits a success JSON envelope containing both `record_path` and the
  full runtime process `record`;
- evaluator resolves `skill_version` from packaged manifest or `SKILL.md`
  frontmatter, accepts `--skill-version` as an explicit override, and records
  `null` when no source is available;
- evaluator records `source_hash` with the same sorted-file SHA-256 contract as
  the released-skill manifest and rejects symlinked skill content;
- evaluator retries with a fresh timestamp on path collision and fails before
  writing if it cannot create a unique path after 5 retries;
- evaluator can write to a caller-supplied durable records root instead of the
  default `~/.nvflare/agent_skill_eval_runs` location;
- evaluator writes atomically and writes no partial success record on input
  validation, artifact, or disk-write failure;
- evaluator accepts checklist-only input when it supplies all required evidence,
  rejects runs with neither `--artifacts` nor `--checklist`, and requires
  `--artifacts` when no checklist is supplied;
- evaluator rejects checklist-only input that lacks any mandatory/prohibited
  behavior status, trigger-only skill-selection evidence, required final-result
  fields, or score-critical process metric fields;
- evaluator rejects checklist input with missing or non-`"1"` `schema_version`;
- evaluator rejects checklist input whose `skill` or `case_id` does not match
  the selected eval case and writes no process record;
- evaluator rejects unknown behavior IDs unless they are explicitly recorded as
  non-scoring notes;
- evaluator rejects conflicting artifact-derived and checklist-supplied
  behavior statuses or scalar result fields instead of choosing one source;
- evaluator rejects conflicting `run.json` and `evidence.json` scalar fields or
  behavior statuses;
- evaluator treats identical duplicate artifact/checklist values as
  non-conflicting and merges list-valued evidence by normalized unique entries;
- evaluator normalizes checklist `behavior_evidence.mandatory_behavior`,
  `behavior_evidence.prohibited_behavior`, and
  `behavior_evidence.optional_behavior` into the record's top-level behavior
  maps;
- evaluator derives behavior IDs from the selected case's `evals/evals.json`
  instead of a hard-coded behavior list;
- evaluator validates behavior status values against the documented enum;
- evaluator applies status semantics by behavior category, including prohibited
  `pass` meaning no prohibited evidence was observed and prohibited `fail`
  meaning the prohibited action was detected;
- evaluator rejects `not_applicable` for mandatory or prohibited behavior IDs
  and rejects `non_scoring_note` for canonical mandatory or prohibited behavior
  IDs while preserving accepted non-scoring notes in the record's
  `optional_behavior` map;
- evaluator records top-level `eval_passed` and fails it when required trigger or
  workflow evidence is missing, any mandatory behavior is missing/failing, any
  prohibited behavior is observed, final_result is not accepted, the final result
  is partial or unvalidated, significant violations are recorded, or evaluator
  validation fails;
- evaluator accepts `final_result.validation_passed` and
  `final_result.simulation_passed` as `null` for cases where those validation
  modes are not applicable;
- evaluator records `eval_passed=true` for a score-3 case where all applicable
  mandatory behavior passes, no prohibited behavior is observed, final_result is
  accepted, required validation passes, and the score was capped only by user
  correction;
- evaluator writes a valid failing runtime process record, not a validation
  error with no record, when prohibited behavior is observed or mandatory
  behavior is missing;
- mandatory behavior with missing evidence fails that behavior;
- prohibited behavior with observed evidence fails the eval case;
- optional behavior absence is recorded but does not fail;
- process score maps to the documented 1-5 rubric for each score level 1
  through 5, including score caps for user corrections, missing mandatory
  evidence, observed prohibited behavior, partial final results, and unsafe or
  incomplete results, with the lowest applicable cap winning;
- evaluator rejects score 4 when `first_pass.accepted` is false; score 4
  requires `first_pass.accepted=true`, `user_correction_count == 0`, and no
  missed instructions, layout violations, workflow violations, or evidence-gap
  violations;
- evaluator validates `score.value`, `score.max`, and bounded
  `score.rationale`, including required rationale presence and deterministic
  template selection;
- evaluator validates documented `process_metrics` types, nullability, and
  score-critical availability rules for `user_correction_count`,
  `agent_self_correction_count`, `missed_instruction_count`, and
  layout/workflow/evidence-gap counts, including
  `agent_self_correction_count` being required for score 5 but not score 4;
- evaluator records `missed_instruction_count > 0` as a score-3 cap while
  preserving `eval_passed=true` when required behavior, final result, validation,
  and prohibited-behavior checks otherwise pass;
- evaluator fills missing or `null` `missed_instruction_count` as a best-effort
  post-run count of mandatory behavior entries whose status is not `pass`, while
  trusting a supplied numeric count when broader harness evidence exists;
- evaluator does not infer missed instructions that are not represented by the
  selected eval case's mandatory behavior IDs or by an explicit structured
  `process_metrics.missed_instruction_count`;
- evaluator validates `first_pass.violations` and `skill_improvements` bounds:
  at most 10 strings each, with each string at most 512 characters;
- evaluator does not assign score 4 or 5 when `user_correction_count` or
  layout/workflow/evidence-gap violation evidence is unavailable;
- evaluator caps significant workflow, safety, or artifact-rule violations
  outside the prohibited-behavior list at score 2 and records
  `eval_passed=false`;
- evaluator accepts `significant_violations` as evidence in the reviewer
  checklist but still computes the final score itself;
- evaluator validates `significant_violations` entries as objects with
  `description` and `evidence_ref`, enforces the documented count and string
  bounds, and does not attempt automated significant-violation detection in M7;
- token count is stored as `null` when unavailable and is not inferred from
  transcript text;
- deterministic evaluator token count is stored as `0` when no token-consuming
  evaluation step runs;
- process records store sanitized bounded evidence snippets or artifact
  references instead of unbounded raw transcripts, large command output, secrets,
  credentials, private keys, access tokens, or sensitive absolute paths;
- evaluator treats artifacts as trusted input and does not claim integrity
  validation or chain-of-custody guarantees;
- evaluator timing is recorded separately from skill-run timing;
- `skills performance` aggregates evaluator-written records but does not create
  or modify them;
- `skills performance` supports `--case`, sorts records by timestamp descending,
  groups summaries by skill/version/case and non-null run mode/source hash, omits
  `run_mode` or source hash from the group key when either is null, skips `null`
  values in numeric averages while reporting exact unavailable counts, rejects
  averaging mixed skill versions or mixed non-null source hashes, emits the
  documented JSON output shape, and rejects unsupported schema versions.
- `skills performance` computes `eval_pass_rate` as true `eval_passed` count
  divided by group `record_count` and emits it as a plain float.
- `skills performance` exits successfully with metric contracts and empty
  `summaries`/`records` arrays when no runtime records match.
- `skills benchmark` requires `--skill`, supports `--case`, `--records`,
  `--output`, and `--dry-run`, writes a Markdown benchmark draft only when
  `--dry-run` is omitted, returns rendered content in the JSON envelope, and
  leaves runtime process records unchanged.
- `skills benchmark --dry-run` renders the same content without creating or
  modifying `BENCHMARK.md`.
- `skills benchmark` output includes scope, records root, packaged metric
  contracts, grouped runtime summaries, and recent record paths from
  `skills performance`, and does not infer metrics or parse artifacts itself.

This milestone evaluates the seed skill set before additional skill waves are
implemented. Runtime evaluation evidence is required before a skill is used as a
template for broader catalog expansion. It does not perform external
publication or handoff. Auto-FL remains an advisory research test case: run
existing Auto-FL tasks without skills, with skills available, and optionally
with a skill forced to isolate skill content.

## Milestone 8: Customer Lifecycle Skill Wave

The seed bundle plus runtime evaluator prove the package, install, lint,
authoring, and evaluation mechanics. The rest of the skill roadmap should be
implemented as follow-on skill-development waves, not left as an unowned
candidate list. Every new skill in these waves must use the authoring and
evaluation contract:

- `SKILL.md` with required frontmatter, trigger boundaries, negative trigger
  guidance, approval checkpoints, and validation checklist;
- `references/` for long examples, framework details, diagnosis patterns, and
  command walkthroughs;
- optional `scripts/` only for deterministic JSON-producing helpers that are
  candidates for later promotion into `nvflare agent` commands;
- `evals/evals.json`, fixtures under `evals/files/` when needed, and
  `BENCHMARK.md` with trigger checks, mandatory behavior checks, prohibited
  behavior checks, and known gaps;
- admission through the initial skill lints, command-drift checks, trigger
  overlap checks, global negative checks, and doc crosslink checks.

Each wave must include at least one runtime evaluator record for each new public
skill before that wave is considered complete. A wave can carry a documented
draft/internal exception, but that skill cannot be used as a template for later
waves or included in publication handoff until Milestone 7 evaluation passes for
that skill.

Deliverables:

- Add `nvflare-setup-local`, `nvflare-local-validation`,
  `nvflare-poc-workflow`, `nvflare-generate-job`,
  `nvflare-identity-and-config`, `nvflare-job-lifecycle`, and
  `nvflare-production-submit`.
- Cover local readiness, job generation, validation, submission, monitoring,
  log/stat download, and production approval boundaries.

## Milestone 9: Framework Conversion Skill Wave

Deliverables:

- Add `nvflare-convert-lightning`, `nvflare-convert-tensorflow`,
  `nvflare-convert-huggingface`, `nvflare-convert-xgboost`,
  `nvflare-convert-sklearn`, and `nvflare-convert-survival-analysis`.
- Scope each skill to the framework-specific edit pattern, examples, recipes,
  validation commands, and negative triggers defined in the authoring design's
  conversion table.

## Milestone 10: Specialized Workflow Skill Wave

Deliverables:

- Add `nvflare-experiment-tracking`, `nvflare-site-specific-training`, and
  `nvflare-collaborative-etl`.
- Cover TensorBoard/MLflow instrumentation, heterogeneous site scripts or
  app/config folders, federated ETL, preprocessing, feature validation,
  data-quality checks, and safe handoff into training or statistics workflows.

## Milestone 11: PET and Security Skill Wave

Deliverables:

- Start with `nvflare-run-private-set-intersection` for PSI/private set
  intersection.
- Add DP, HE, and privacy-policy-filter skills only after their evidence,
  validation fixtures, approval checkpoints, and production safety contracts are
  ready.

Each wave should update the product skill catalog in
[Agent Integration](agent_integration.md#product-skill-catalog), the source
tables in [Agent Skill Authoring](agent_skill_authoring.md), and any deferred
roadmap entries that are promoted into current scope. A skill is not considered
implemented just because its name appears in the catalog; implementation means
the full authoring package, engineering lint coverage, and evaluation evidence
exist in the repo.

## Milestone 12: Export Manifest and Fingerprint

Deliverables:

- Add `_export_manifest.json` to exported job folders with required files,
  source path/hash, timestamp, NVFLARE version, exporter, and validation status.
- Add a nested `fingerprint` section in `_export_manifest.json` with FLARE,
  Python, recipe, framework dependency, and source-hash metadata.
- Prefer one manifest file with a nested fingerprint unless separate consumers
  need a separate `job_fingerprint.json`.

Engineering tests:

- exported job manifest content and schema tests;
- manifest source-hash and required-file validation tests;
- backward-compatible export tests for jobs that do not request manifest-aware
  behavior.

## Milestone 13: Manifest-Aware Inspect and Preflight

Deliverables:

- Make `nvflare agent inspect` consume `_export_manifest.json` and nested
  fingerprint metadata when present.
- Keep `nvflare agent inspect` compatible with current exported jobs that lack
  the manifest.
- Make future submit preflight consume the same manifest/fingerprint contract
  when that submit-preflight surface is promoted into current scope.

Engineering tests:

- inspect tests for exported jobs with and without `_export_manifest.json`;
- stale manifest, missing required file, and source-hash mismatch fixtures;
- preflight compatibility tests when submit preflight is implemented.

## Milestone 14: Publication Handoff

Deliverables:

- Tie released skill content to the NVFLARE release that ships it.
- Provide guide-compatible skill files and initial evaluation evidence.
- Keep external catalog registration, signing, public installer metadata, and
  public scoreboard mechanics outside this implementation plan.
- Do not hand off a skill as public-ready until Milestone 7 runtime evaluation
  passes for that skill.

## Deferred Work

Do not implement these in the initial implementation unless a separate scope decision promotes them:

- receipts, provenance, and durable workflow state;
- transcript record/replay;
- workspace cleanup;
- full lifecycle commands beyond install/list;
- compatibility shims, `obsoletes`, and changelog commands;
- PR-bot automation;
- large policy catalog;
- full paired harness, instruction-monitor service, and cost-accounting system;
- public scoreboard mechanics.
