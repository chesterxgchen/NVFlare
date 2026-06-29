---
name: nvflare-job-lifecycle
description: "Operate exported NVFLARE job folders after conversion or authoring: validate on request, submit to a configured FLARE system, list/meta/wait/monitor jobs, inspect stats/logs, download results, and explicitly abort/delete/clone jobs. Use for exported FLARE job operations, not training-code conversion or POC lifecycle setup."
min_flare_version: "2.8.0"
blast_radius: submits_production
category: Operations
skill_version: "0.1.0"
---

# NVFLARE Job Lifecycle

## Use When

Use when the user has an exported, submit-ready FLARE job folder or a submitted
job ID and asks to validate, submit, list, monitor, wait, inspect metadata,
read stats/logs, download results, abort, delete, or clone.

## Do Not Use When

Do not use for raw training-code conversion, recipe selection, generated
`client.py` or `job.py` authoring, POC prepare/start/stop/clean, deployment
setup, installation repair, or failed-job root cause diagnosis. Showing
stats/logs for a known job ID remains lifecycle work; explaining why a failed or
stalled job failed routes to `nvflare-diagnose-job`.

## Workflow

1. Classify the phase from the user's request: validation-only, submit,
   observe, download/report, or explicit abort/delete/clone.
2. For normal submit requests, do only minimal path and target-context sanity,
   then submit directly. Do not run full structural validation unless the user
   explicitly asks to validate or a submit failure needs local explanation.
3. Load `references/job-validation.md` only for validation-only requests or
   post-submit-failure explanation.
4. Load `references/submit-monitor-download.md` for submit, list, meta, wait,
   monitor, stats, logs, download, abort, delete, or clone.

## Source Of Truth Boundary

Use this skill, its references, `nvflare agent inspect`, `nvflare agent doctor`,
and `nvflare job <subcommand> --schema` as the command source of truth. Do not
read NVFLARE SDK source, generated docstrings, or `site-packages/nvflare/**` to
invent lifecycle command semantics. If public CLI evidence conflicts with this
skill, report the version mismatch or skill gap instead of switching strategy.

## Requirements

- Must not use any POC status subcommand.
- Must not use the deprecated job creation subcommand; exported jobs come from
  `python job.py --export --export-dir <exported_job_root>`.
- Must submit the requested exported job root directly with
  `nvflare job submit -j <exported_job_root> --format json`; do not append a
  nested job-name component.
- Must use `nvflare job list`, `meta`, `wait`, `monitor`, `stats`, `logs`, and
  `download` for normal lifecycle evidence.
- Must use abort, delete, or clone only when the user explicitly asks for that
  operation.
- Must submit to POC or production systems only when the user explicitly asks
  to submit and the startup-kit/study/role context is visible or supplied.
- Must not wrap operational CLI commands in generated Python or scrape human
  output when JSON or JSONL output is available.
- Must not run `python job.py`, import user training code, or start a local
  simulation while handling exported-job lifecycle work unless the user
  explicitly asks to run or simulate source.
- Must not use job log-configuration mutation as part of Phase 1 lifecycle
  work.
- Must not finalize while a lifecycle operation is still pending. Report
  terminal state, explicit timeout/current nonterminal state, or blocker with
  command evidence.

## Output Shape

Report the target job path or job ID, target study/startup-kit context when
used, commands run, observed status, result directory or artifact paths when
available, and any blockers or missing evidence.
