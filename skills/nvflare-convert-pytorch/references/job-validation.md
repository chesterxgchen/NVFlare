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

## Iterative Reruns

When the user asks to change batch size, train args, number of rounds,
`min_clients`, site count, or recipe, update only the affected training args or
job configuration. For recipe changes, rerun
`nvflare recipe show <recipe-name> --format json` and verify the new recipe's
parameters before editing.

After each change, rerun local validation when possible. If an exported job was
previously produced and export remains in scope, export again so the job folder
matches the updated source.

## Recipe Search And Accuracy Comparison

When the user asks for the best recipe or best accuracy, first define the target
metric, validation split, maximum run budget, and compatible recipe set. Do not
promise that one recipe is best without measured evidence from comparable runs.

Use `nvflare recipe list --framework pytorch --format json` to find candidates
and `nvflare recipe show <recipe-name> --format json` for each candidate selected
for comparison. Keep dataset split, number of sites, rounds, epochs, seed, and
evaluation metric comparable unless the user asks to tune them.

Report a small results table with recipe, settings, metric value, command,
status, and result path. If a candidate cannot run, report the blocker instead
of silently dropping it.

## Data Distribution Experiments

When the user asks to compare IID and heterogeneous data splits, define the split
strategy before editing. Examples include equal random IID shards, label-skewed
non-IID shards, quantity-skewed shards, or user-provided per-site partitions.

Keep recipe, rounds, epochs, batch size, seed, and metric comparable unless the
user asks to tune them. Do not copy private data into generated artifacts; prefer
split indices, deterministic samplers, or site-local path arguments.

Report a table with split strategy, per-site sample counts or label summary when
available, metric value, command, status, and result path. If a split cannot be
created safely from the available data, report the blocker.

## Dataset Replacement Experiments

When the user provides a dataset URL and asks to repeat an experiment, record the
URL, dataset name when known, version or timestamp when available, expected
download size if known, license or access constraints when visible, and local
cache/path used for validation.

Do not hide download, preprocessing, schema, or label-mapping assumptions. Keep
recipe, site count, rounds, epochs, batch size, seed, split policy, and metric
comparable unless the user asks to tune them. If the new dataset requires a data
loader or preprocessing change, keep it scoped and report the changed files.

Follow the project's existing data-prep structure. If it already has
`download_data.py`, `prepare_data.py`, `prepare_data.sh`, or equivalent helpers,
extend those rather than creating a parallel structure. If no helper exists and
a new one is needed, use the established NVFLARE example convention of separate
download and prepare/split steps, and keep download paths, cache paths, and
per-site output directories explicit.

Use hello-world examples as the first convention reference for new helpers:
`examples/hello-world/hello-lr/download_data.py`,
`examples/hello-world/hello-lr/prepare_data.py`,
`examples/hello-world/hello-jax/prepare_data.py`, and shell-based examples such
as `examples/hello-world/hello-cyclic/prepare_data.sh`.

Report command, status, metric value, result path, dataset source, and any
blocker. If the URL is unavailable or the dataset cannot be downloaded in the
current environment, report the experiment as blocked rather than substituting a
different dataset silently.

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
