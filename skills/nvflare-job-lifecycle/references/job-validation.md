# Exported Job Validation

Load this reference only when the user explicitly asks to validate without
submitting, or after `nvflare job submit` fails and local evidence is needed to
explain the failure. Do not make this a mandatory pre-submit phase for normal
submit requests.

## Source Of Truth Boundary

Use this reference, `nvflare agent inspect <path> --format json`, and public
`nvflare job ... --schema` output for validation behavior. Do not inspect
NVFLARE SDK source, generated docstrings, or `site-packages/nvflare/**` to
replace these rules. If installed CLI behavior differs, report a version
mismatch or skill gap.

## Scope

Keep validation deterministic, bounded, and local:

- inspect files, directories, symlinks, and config references;
- parse JSON configs and metadata when present;
- run `nvflare agent inspect <path> --format json` when available;
- stay inside the requested job root except for reporting symlink target paths;
- read only metadata and small known config files; skip binary artifacts,
  checkpoints, model weights, private-key contents, certificates, and unrelated
  source files;
- do not import user code, run training, start a POC system, submit the job, or
  modify the exported folder.

Validation-only means no submission. Post-submit-failure validation explains the
observed CLI failure; do not resubmit a corrected nearby path without user
approval.

## Root Identification

The requested path should be the submit-ready exported job root. Do not append a
job-name component before submit.

Recognize common exported roots by evidence such as:

- `meta.json`, `meta.conf`, `meta.yml`, or `meta.yaml` at the root;
- server config under `app/config/config_fed_server.*`,
  `app_server/config/config_fed_server.*`, or
  `server/config/config_fed_server.*`;
- client config under the matching `app/config/`, `app_site-*/config/`, or
  `site-*/config/` layout;
- custom code or resources under each app's `custom/` directory when referenced
  by config.

If the user points at a parent that contains one likely exported job child,
report the likely root and ask before submitting that child. If several likely
children exist, treat the target as ambiguous.

## Severity Model

For validation-only or post-submit-failure explanation, block a submit-ready
recommendation when:

- the requested path does not exist or is not a directory;
- the path is not recognizable as an exported job root;
- no recognizable server app/config can be found;
- required server or client app folders are missing for the detected layout;
- required `config_fed_server.*` or client config files are missing;
- a required JSON config or `meta.json` file is invalid JSON;
- a required custom file referenced by config is missing from the job root;
- the tree contains unsafe symlinks, path traversal, or submit-bound config with
  secret-like material such as private keys, tokens, passwords, or certificates
  embedded where job code/config will be uploaded;
- the target appears to be a copied workspace delta, source tree, simulator
  workspace, or nested wrong root rather than the exported job folder;
- `nvflare agent inspect <path> --format json` reports a state inconsistent
  with an exported job and the user has not provided an explicit override.

Warn, but do not block, when:

- optional `_export_manifest.json`, fingerprint metadata, or future export
  metadata is absent;
- launcher or resource hints are absent;
- optional metrics or result artifacts are not present before the job has run;
- the layout is recognizable but appears to be an older export shape.

Require an explicit user decision when:

- config contains absolute private data paths;
- symlinks point to clearly unrelated sensitive locations or create traversal
  risk. Symlinks by themselves are not automatically unsafe;
- environment hooks or scripts appear unrelated to launching training or FLARE
  services and could have side effects the user did not mention.

Normal executable training entry points, launch scripts, and commands such as
`torchrun` are expected job content and do not require confirmation merely
because they execute code.

## Validation Procedure

1. Record whether this is validation-only or post-submit-failure explanation.
2. Resolve and report the exact requested path. Stop if it is missing or not a
   directory.
3. Inspect a bounded file tree and identify the job root evidence, server app,
   client app folders, metadata file, and config files.
4. Parse required JSON files. For `.conf`, `.yml`, or `.yaml`, report presence
   and defer schema authority to FLARE CLI evidence unless a project-local
   parser is already part of the workflow.
5. Check config-referenced local files conservatively. Only mark missing files
   as blockers when the reference clearly points inside the job root or to a
   packaged custom file.
6. Check symlinks and path traversal. Report symlink target evidence without
   reading private key contents.
7. Run `nvflare agent inspect <path> --format json` when available and include
   its classification, warnings, and recommended skill evidence.
8. Summarize blockers, warnings, user decisions, and whether the folder appears
   submit-ready.

## Reporting

For validation-only, state clearly that no submit command was run. For
post-submit-failure explanation, include the original submit command, the CLI
error/status, and the local evidence that explains likely path or packaging
causes.
