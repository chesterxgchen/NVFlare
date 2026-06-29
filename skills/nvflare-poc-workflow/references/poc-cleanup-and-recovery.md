# POC Cleanup And Recovery

Use this reference only for stop, clean, overwrite/recreate protection,
conflicting active workspaces/ports, or orphaned local POC process recovery.
Normal readiness checks belong in `poc-readiness.md`; normal configure,
prepare, start, add-user, and add-site belong in `poc-lifecycle.md`.

## Source Of Truth Boundary

Use public CLI evidence first: `nvflare poc <subcommand> --schema`,
`nvflare agent doctor --format json`,
`nvflare agent doctor --online --format json`,
`nvflare system status --format json`, and `nvflare job list --format json`.
Do not inspect SDK source, generated docstrings, or `site-packages/nvflare/**`
to infer shutdown semantics. Do not claim an NVFLARE process-management
command exists for this workflow.

## Active Job Protection

Before `nvflare poc stop` or `nvflare poc clean`, check active jobs when the
system is reachable:

```bash
nvflare job list --format json
```

If visible active job IDs exist, report the job IDs and ask before stopping or
cleaning. If job listing is unreachable, report that active jobs could not be
verified and ask before destructive cleanup unless the user has already made an
explicit informed choice.

## Stop

Use stop only when the user explicitly asks to stop the local POC system or
confirms after active-job/conflict evidence:

```bash
nvflare poc stop
```

Use participant selection, exclusion, no-wait, or debug options only when the
user supplied them or public schema-backed context requires them. Prefer the
normal coordinated POC stop path before any process-level recovery.

After stop, verify with readiness/status evidence:

```bash
nvflare agent doctor --online --format json
nvflare system status --format json
```

If the system is no longer reachable, that may be expected after stop; report
the command response and the observed unreachable/stopped evidence rather than
treating every connection failure as an error.

## Clean

Use clean only when the user explicitly asks to clean the local POC workspace
or confirms after active-job/conflict evidence:

```bash
nvflare poc clean
```

Use `--force` only when the user explicitly asks to stop-before-cleanup or
confirms that behavior. Do not clean automatically after stop unless the user
asked for cleanup.

After clean, run local doctor evidence and report remaining configured
workspace/startup-kit state when visible:

```bash
nvflare agent doctor --format json
```

## Conflicting Workspace Or Port Evidence

When prepare/start/config evidence suggests another local POC workspace,
startup kit, or port is active:

1. Report the visible workspace, selected startup-kit context, server/admin
   addresses, ports, participant names, and command evidence.
2. Ask whether the user wants to continue with the new workspace, stop the
   active system, clean the active workspace, or only inspect.
3. Do not overwrite, start over, stop, clean, or kill processes without the
   user's explicit choice.

Starting a different POC workspace while another local POC appears active is
allowed only after explicit user confirmation and a report of the active
workspace/port/process evidence.

## Orphan Recovery

Orphan recovery is a fallback for local FLARE server/client processes that the
normal POC workspace metadata can no longer manage. Keep it bounded and
evidence-based.

Use normal metadata first:

- POC workspace from `nvflare poc config`;
- startup-kit and local config evidence from `nvflare agent doctor --format json`;
- online/system evidence from `nvflare agent doctor --online --format json`
  and `nvflare system status --format json`;
- pid files or service metadata under the known POC workspace/startup kits when
  visible without reading secrets.

Use `ps -aef` only when normal metadata is missing, stale, or insufficient to
identify leftover local FLARE processes. Bound the search to evidence that
matches the POC workspace, startup-kit paths, participant names, or configured
ports. Do not run broad process cleanup based on a generic Python or NVFLARE
string alone.

Before killing any process, report:

- PID and command line;
- matched workspace, startup-kit, participant, or port evidence;
- why normal `nvflare poc stop` could not manage it;
- whether active jobs could be checked and any visible job IDs.

Ask for explicit confirmation before sending a graceful termination signal.
Attempt graceful termination first. Check whether the process exited. Use force
kill only after a second explicit confirmation that names the remaining PID or
PIDs.

Do not kill processes when evidence is ambiguous, points outside the selected
POC workspace, or could belong to another user's unrelated FLARE deployment.
Report the ambiguity and ask for a narrower workspace, startup-kit path, port,
or PID evidence instead.

## Final Report

For stop, clean, or recovery, report commands run, active-job check result,
workspace/startup-kit context, final system status or unreachable/stopped
evidence, any PIDs signaled, and any remaining manual action required.
