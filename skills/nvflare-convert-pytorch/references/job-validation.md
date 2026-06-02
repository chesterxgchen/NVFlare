# Job Validation And Export

The conversion is not complete until the user has a runnable local validation
path and an exported job folder when export is in scope.

## Local Validation

- Use `python job.py` for local recipe or SimEnv validation when the generated
  job file supports direct execution.
- Prefer synthetic data flags or small fixtures when the original dataset is
  unavailable.
- Report the command, status, and result directory.

## Export

- Use `python job.py --export --export-dir <dir>` only when the job file exposes
  those arguments.
- Inspect the exported folder for server/client app folders and expected config
  files before recommending submission.

## Approval Boundary

POC or production submission is outside this skill's default action. Ask for
explicit user approval before using any submit or runtime-start command.

## Common Gaps To Report

- The source training script has side effects at import time.
- The model has non-serializable state outside `state_dict`.
- The dataset path is site-specific and cannot be validated locally.
- The job file has no export path yet.
