---
name: nvflare-poc-workflow
description: "Operate local NVFLARE POC systems: configure, prepare, start, verify readiness, stop, clean, add POC users/sites, and recover local orphaned POC processes with explicit user intent."
min_flare_version: "2.8.0"
blast_radius: submits_poc
category: Operations
skill_version: "0.1.0"
---

# NVFLARE POC Workflow

## Use When

Use when the user wants a local FLARE proof-of-concept system with separate
server and client processes, asks for POC configure/prepare/start/readiness,
stop/clean, add-user/add-site, local orphan-process recovery, or wants an
exported job run against a local POC target before production submission.

## Do Not Use When

Do not use for training-code conversion, SimEnv-only validation, production
deployment, Kubernetes setup, remote production operations, job failure root
cause diagnosis, or normal job submit/monitor/download after a POC system is
already running. Hand off to `nvflare-job-lifecycle` when the local POC system
is ready and the user wants to submit, monitor, inspect, download, abort,
delete, or clone jobs.

## Workflow

1. Classify the phase from the user's request: configure/prepare, start,
   readiness/status check, add-user/add-site, stop, clean, or orphan recovery.
2. Load `references/poc-readiness.md` for read-only local readiness/status
   checks and before or after any operation where a POC system should be
   running.
3. Load `references/poc-lifecycle.md` for `nvflare poc config`, `prepare`,
   `start`, `add-user`, and `add-site`.
4. Load `references/poc-cleanup-and-recovery.md` only for stop, clean,
   overwrite/recreate, active job protection, conflicting workspaces/ports, or
   orphan-process recovery.
5. After the POC system is running and the user wants job lifecycle operations,
   hand off to `nvflare-job-lifecycle`.

## Source Of Truth Boundary

Use this skill, its references, public `nvflare poc <subcommand> --schema`,
`nvflare agent doctor`, `nvflare system status`, and `nvflare job` command
schemas as the command source of truth. Do not read NVFLARE SDK source,
generated docstrings, or `site-packages/nvflare/**` to invent POC operational
semantics. If public CLI evidence conflicts with this skill, report the version
mismatch or skill gap instead of switching strategy.

## Requirements

- Must use only these POC commands: `nvflare poc config`, `prepare`, `start`,
  `stop`, `clean`, `add-user`, and `add-site`.
- Must not use or mention any POC status subcommand.
- Must not claim an NVFLARE process-management command exists for this
  workflow.
- Must not use the deprecated job-creation subcommand.
- Must run mutating POC operations only when the user explicitly asks for that
  operation or confirms it: prepare, start, stop, clean, add-user, or add-site.
- Must use `nvflare agent doctor --format json` for local readiness/config
  checks and `nvflare agent doctor --online --format json` for bounded online
  checks through the selected startup kit.
- Must use `nvflare system status --format json` for local system status once
  a POC system should be running.
- Must check active jobs with `nvflare job list --format json` before stop or
  clean when the system is reachable. If active job IDs are visible, ask before
  stopping or cleaning.
- Must keep orphan recovery isolated to the cleanup/recovery reference and
  require explicit confirmation before killing any process.

## Output Shape

Report the phase, POC workspace or selected startup-kit context, commands run,
observed readiness/system status, active-job protection result when relevant,
changed participants when add-user/add-site is used, and any blocker or
explicit handoff to `nvflare-job-lifecycle`.
