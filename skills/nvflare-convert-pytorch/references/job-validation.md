# Job Validation And Export

The conversion is not complete until the user has a runnable local validation
path and an exported job folder when export is in scope.

## Local Validation

- Use `python job.py` for local recipe or SimEnv validation when the generated
  job file supports direct execution.
- Prefer synthetic data flags or small fixtures when the original dataset is
  unavailable.
- Report the command, status, result directory, and any dependency or data
  blocker.

## Export

- Use `python job.py --export --export-dir <dir>` to export a FedJob. These are
  FedJob system arguments and do not need to be declared by the job file.
- Inspect the exported folder for server/client app folders and expected config
  files before recommending submission.

## Validation Evidence

Before calling the generated job correct, report:

- selected recipe and the `nvflare recipe show` command used to inspect it;
- changed files and why they were changed;
- local validation command and pass/fail status;
- export command, export directory, and exported folder inspection result when
  export is in scope;
- unresolved blockers such as unavailable data, missing dependencies, or
  required user approval.

If `python job.py` cannot run, the conversion may still be saved as a draft, but
report it as unvalidated and name the concrete blocker.

## Evaluation Records

When a generated job does not run as expected, keep the failure as evaluation
evidence instead of treating it as a one-off note. Record the user request,
selected recipe, files changed, validation command, failure output summary,
root-cause hypothesis, and follow-up fix or blocker.

If the failure represents a repeatable skill gap, add or update an eval case,
benchmark gap, fixture, or reference note so future skill runs are tested against
the same scenario.

## Approval Boundary

POC or production submission is outside this skill's default action. Ask for
explicit user approval before using any submit or runtime-start command.

## POC Handoff

When the user explicitly approves POC after simulation, or provides a POC
workspace and asks for submission, validate the exported job folder first. Then
use the supplied POC workspace or start POC as requested, submit the exported
job, and wait or monitor if requested.

Report the POC workspace, submitted job folder, job ID, final status or current
status, command evidence, and any log/result paths. If the POC run fails, record
the failure as evaluation evidence using the same rule as local validation
failures.

## Common Gaps To Report

- The source training script has side effects at import time.
- The model has non-serializable state outside `state_dict`.
- The dataset path is site-specific and cannot be validated locally.
- The job file has no export path yet.
