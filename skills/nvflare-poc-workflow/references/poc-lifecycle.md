# POC Lifecycle

Use this reference for user-approved POC configuration, preparation, startup,
and participant creation. Load `poc-readiness.md` before or after lifecycle
operations when readiness evidence is needed. Load
`poc-cleanup-and-recovery.md` before overwrite, stop, clean, or conflicting
workspace/port handling.

## Source Of Truth Boundary

Use public `nvflare poc <subcommand> --schema`, `nvflare agent doctor`, and
`nvflare system status` evidence. Do not read SDK source, generated docstrings,
or `site-packages/nvflare/**` to invent POC command behavior. If an installed
CLI lacks an expected option, report a version mismatch or skill gap.

## User Intent Boundary

POC lifecycle commands mutate local configuration, workspace files, startup-kit
registry state, or local processes. Run them only when the user explicitly asks
for the specific operation or confirms it:

- `nvflare poc config`
- `nvflare poc prepare`
- `nvflare poc start`
- `nvflare poc add-user`
- `nvflare poc add-site`

Readiness checks may be run without extra confirmation when they are needed to
answer the user's request.

## Configure Workspace

Use `nvflare poc config` to inspect or set the local POC workspace. To set a
workspace, require explicit user intent and a target path:

```bash
nvflare poc config --pw <poc_workspace_dir>
```

Before changing to a different workspace, check local readiness and active
system evidence. If another local POC system appears active, report the active
workspace, selected startup-kit context, and reachable ports/status before
asking whether to continue.

## Prepare

Use prepare when the user asks to create or refresh a local POC workspace or
startup kits:

```bash
nvflare poc prepare
```

Add supported options such as client count, client names, homomorphic
encryption, project input, Docker image, or debug only when the user supplied
them or the public schema confirms the option and the workflow requires it.

Before prepare, check local readiness/config evidence. If the target workspace
already appears prepared or a POC system appears active, ask before overwriting
or recreating anything. Do not clean or stop automatically unless the user
asked for that operation or confirms it.

After prepare, run local readiness/config evidence and report the selected
startup-kit context when visible:

```bash
nvflare agent doctor --format json
```

## Start

Use start only when the user asks to start local server/client processes:

```bash
nvflare poc start
```

Start all participants by default only when that matches user intent. Use
participant selection, exclusion, GPU IDs, timeout, no-wait, or debug options
only when supplied by the user or required by visible schema-backed context.

Before start, check local readiness/config evidence. If another local POC
system appears active or configured ports appear occupied by a conflicting POC
workspace, report the conflict and ask before starting.

After start, verify readiness through the selected startup kit and system
status:

```bash
nvflare agent doctor --online --format json
nvflare system status --format json
```

If start returns before readiness is complete, continue only until a terminal
ready/not-ready state, an explicit timeout, or a blocker is observed. Do not
finalize with an unverified "still starting" promise unless you report the
current command evidence and timeout boundary.

## Add User Or Site

Use add-user only when the user provides or confirms the certificate role,
email, and organization:

```bash
nvflare poc add-user <cert-role> <email> --org <org>
```

Use add-site only when the user provides or confirms the site name and
organization:

```bash
nvflare poc add-site <name> --org <org>
```

Use `--force` only when the user explicitly asks to replace or refresh an
existing participant or confirms after a conflict. After participant creation,
run `nvflare agent doctor --format json` and report the changed startup-kit or
service context when visible.

## Local Submit Target

When the user wants to run an exported job on the local POC system:

1. Prepare and start POC only if the user asked for those mutating operations.
2. Verify readiness with `poc-readiness.md`.
3. Hand off to `nvflare-job-lifecycle` for submit, list, metadata, wait,
   monitor, stats, logs, download, abort, delete, or clone.

Do not use the deprecated job-creation subcommand; exported jobs come from the
job authoring/export path and lifecycle submission uses the job lifecycle
skill.
