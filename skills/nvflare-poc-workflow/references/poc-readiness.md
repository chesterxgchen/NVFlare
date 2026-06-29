# POC Readiness

Use this reference for read-only local POC readiness and status evidence. This
reference does not authorize prepare, start, stop, clean, add-user, add-site,
or process killing.

## Source Of Truth Boundary

Use public CLI output and command schemas only. The authority for readiness is
`nvflare agent doctor --format json`, bounded online readiness through
`nvflare agent doctor --online --format json`, and system status through
`nvflare system status --format json` once a local POC system should be
running. Do not inspect SDK source, generated docstrings, or
`site-packages/nvflare/**` to infer hidden readiness states.

## Evidence Order

1. Identify the intended POC workspace, startup-kit, kit ID, study, or local
   context from the user request and visible CLI evidence.
2. Run local readiness/config checks:

```bash
nvflare agent doctor --format json
```

3. If a POC system should be running, run bounded online checks through the
   selected startup kit or active configured kit:

```bash
nvflare agent doctor --online --format json
```

4. Once the system should be running, check local system status:

```bash
nvflare system status --format json
```

5. If command options for startup-kit selection, study selection, or JSON
   output are uncertain, inspect the public schema before choosing options.

## Readiness Interpretation

Treat a POC system as ready only when public command evidence shows the local
configuration is valid, a selected startup kit can perform bounded online
checks, and local system status reports reachable server/client state.

Treat these as blockers or partial readiness, not success:

- no active or selected startup kit for the intended POC system;
- local config points at a different workspace than the user intends;
- doctor reports missing or invalid local config;
- online doctor cannot reach the selected local system;
- system status cannot reach the server after POC should be running;
- visible server/client state is missing, partial, or inconsistent with the
  requested participant set.

When readiness is partial, report which evidence is present and which command
failed or returned missing state. Do not fill gaps by inspecting private
runtime files or SDK internals.

## Status Requests

For user requests like "is my POC running" or "check local POC status", do not
use a POC status subcommand. Use:

```bash
nvflare agent doctor --format json
nvflare agent doctor --online --format json
nvflare system status --format json
```

Skip the online and system-status commands only when local doctor evidence
shows there is no selected or usable startup-kit context. In that case, report
that the system status cannot be checked until a valid local context is
selected or prepared.

## Handoff Point

When readiness evidence shows the local POC system is running and the user
wants job submit, list, metadata, wait, monitor, stats, logs, download, abort,
delete, or clone, stop using this skill and hand off to
`nvflare-job-lifecycle`.
