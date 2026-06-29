# Submit, Monitor, And Download

Use this reference for exported job operations against a configured FLARE
system. Prefer JSON or JSONL command output and public command schemas. Do not
use any POC status subcommand, the deprecated job creation subcommand,
generated Python CLI wrappers, or human-output scraping.

## Source Of Truth Boundary

Use this reference, `nvflare agent doctor --online --format json`, and
`nvflare job <subcommand> --schema` for lifecycle command semantics. Do not
inspect NVFLARE SDK source, generated docstrings, or `site-packages/nvflare/**`
to override the skill path. If the installed CLI lacks an expected option or
behaves differently, report a version mismatch or skill gap.

## Target Context

Identify the target context before remote operations:

- exported job root for submit;
- job ID for observe/download/abort/delete/clone;
- study name when the target is not the default study;
- startup-kit path, kit ID, submit token, or active configured kit when supplied
  or required by the environment.

When option details are uncertain, inspect the public schema:

```bash
nvflare job submit --schema
nvflare job wait --schema
nvflare job monitor --schema
nvflare job download --schema
```

Do not use job log-configuration mutation in this Phase 1 workflow.

## Pre-Submit

For normal submit requests:

1. Confirm the requested path exists and is a directory.
2. Treat the requested path as the submit target. Do not append another
   directory component.
3. Do not run full structural validation unless the user asked to validate or a
   prior submit failed.
4. Check target readiness with the selected startup-kit context when online
   submission is requested. Inspect `nvflare agent doctor --schema`; when the
   installed command supports per-command startup-kit selectors, use the same
   selector you will use for submit so readiness validates the selected kit, not
   an unrelated active default. When no explicit kit is supplied, validate the
   active default kit:

```bash
nvflare agent doctor --online --format json
```

If the system is unreachable, no active startup kit is configured, or the
visible role/study context is wrong, report a blocker instead of submitting.

## Submit

Submit only when the user explicitly requested submission:

```bash
nvflare job submit -j <exported_job_root> --format json
```

Add `--study <name>`, `--submit-token <token>`, `--kit-id <id>`, or
`--startup-kit <path>` only when the user supplied it or the selected target
context requires it.

Interpret success as a successful upload/registration, not completed training.
A successful response must provide a job ID such as `data.job_id` or
`data.existing_job_id` and a non-failure submit/status response. Queued,
submitted, or running means the job was accepted; it is not terminal training
success.

If submit fails, report the exact path, command, exit status, and CLI
error/status. Load `job-validation.md` only when local explanation is useful.
Do not guess and submit a sibling or child folder without user approval.

## List And Metadata

Use list and metadata for current server evidence:

```bash
nvflare job list --format json
nvflare job meta <job_id> --format json
```

Include `--study`, `--kit-id`, or `--startup-kit` consistently when the target
context requires it. Use metadata to confirm the job ID, status, submitter,
study, and relevant timestamps before destructive operations.

## Wait Or Monitor

Use monitor when the user wants streaming progress:

```bash
nvflare job monitor <job_id> --format jsonl
```

Use wait when a bounded non-streaming command is enough:

```bash
nvflare job wait <job_id> --format json
```

Keep waiting or monitoring until a terminal state is observed or an explicit
timeout/current nonterminal state is reached. Do not finalize with a waiting
promise or any message that implies the operation is still pending without
reporting the observed current state and command evidence.

## Stats And Logs

Use stats and logs for bounded observation, including for failed jobs when the
user asks to see logs or stats rather than to diagnose root cause:

```bash
nvflare job stats <job_id> --format json
nvflare job logs <job_id> --format json
```

When logs may be large, inspect the schema and use bounded options such as site,
tail, since, or max-bytes when available. Preserve server/site labels from the
CLI response. If the job is failed, stalled, or suspicious and the user asks why
it failed or wants recovery guidance, hand off to `nvflare-diagnose-job`.

## Download And Report Results

Download only after terminal state when the user asks for results or the
workflow requires result reporting. Write only to a user-specified result
directory or a clearly reported temporary results directory; never write results
into the source tree or exported job root by default:

```bash
nvflare job download <job_id> -o <result_dir> --format json
```

Use the JSON response as the source of truth for artifact paths. After download,
report:

- job ID and terminal status;
- result directory;
- `data.artifacts.global_model`, `data.artifacts.metrics_summary`,
  `data.artifacts.client_logs`, and `data.artifacts.round_metrics` when
  present;
- `data.missing_artifacts` or equivalent missing-evidence details;
- any mismatch between requested results and available artifacts.

If metrics are present, summarize the declared primary/final metric, round
metrics, and artifact paths. If metrics are missing, say which expected artifact
was absent instead of inventing a metric from logs. Do not infer production
artifact paths from simulator workspace conventions.

## Abort, Delete, And Clone

Run these only when the user explicitly requests the operation.

Before abort or delete, confirm the target job ID and current status when
possible:

```bash
nvflare job meta <job_id> --format json
```

Then use the specific requested command. Abort and delete are destructive and
the CLI rejects them in non-interactive mode without `--force`; add `--force`
only after the user explicitly requested the operation or confirmed it:

```bash
nvflare job abort <job_id> --force --format json
nvflare job delete <job_id> --force --format json
nvflare job clone <job_id> --format json
```

For delete, report whether results or artifacts were downloaded first, or that
the user chose to skip download. For clone, report the new job ID or cloned job
path from the JSON response.

## Final Report

Always include command evidence and the observed outcome:

- submitted job root or job ID;
- study/startup-kit context used;
- job ID returned by submit or selected by the user;
- terminal status, current nonterminal status with timeout, or blocker;
- download directory and artifact paths when applicable;
- missing evidence and the exact next command only when further user action is
  required.
