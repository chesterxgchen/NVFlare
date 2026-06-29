# Orientation Routing Reference

`nvflare-orient` is the lead skill for ambiguous NVFLARE requests. It should
turn project evidence and user intent into one narrow next action.

## Evidence Sources

- `nvflare agent inspect <path> --format json` for framework, FLARE usage,
  conversion state, safety findings, and recommended skills.
- `nvflare agent doctor --format json` for local CLI, skill bundle, startup-kit,
  POC, and optional online readiness.
- User-provided target files, job folders, logs, or stated deployment context.

## Routing Rules

- Existing PyTorch training loop needing FLARE conversion:
  `nvflare-convert-pytorch`.
- Exported FLARE job folders with lifecycle intent such as validate, submit,
  monitor, wait, download, abort, delete, or clone: `nvflare-job-lifecycle`.
- Exported FLARE job folders stay lifecycle work even when framework source
  files such as `train.py` or `model.py` are included as job custom code.
- Raw framework training code without exported FLARE job metadata/config remains
  conversion work, not lifecycle work.
- Generic "help me use FLARE here" with no clear workflow: inspect first, then
  recommend the narrowest skill.
- Existing FLARE job where the user asks for logs, stats, metadata, monitoring,
  or download remains `nvflare-job-lifecycle`, even if the status is failed.
- Existing FLARE job where the user asks why it failed, why it is stalled, or
  how to recover: `nvflare-diagnose-job`, not lifecycle.
- Local POC prepare, start, verify/check running, stop, clean, cleanup, or
  orphan-process recovery: `nvflare-poc-workflow`.
- Once a POC is already running and the user asks to submit, monitor, wait,
  download, abort, delete, or clone an exported job: `nvflare-job-lifecycle`,
  not POC workflow.
- Raw framework training code remains conversion work even when the user plans
  to run the converted job in local POC afterward.
- Failed, stalled, or suspicious jobs where the user asks for root cause remain
  `nvflare-diagnose-job`, even in POC.
- Kubernetes deployment or identity/startup-kit setup: route to the
  corresponding operations or deployment skill when available.
- Non-FLARE Python, web, data science, or generic ML questions: no FLARE skill.

## Output Shape

Summaries should name:

- target path inspected;
- strongest evidence found;
- recommended next skill or no-skill decision;
- validation or approval boundary before any mutating follow-up.

Do not turn routing into implementation. Once the next skill is clear, hand off
instead of continuing with broad advice.
