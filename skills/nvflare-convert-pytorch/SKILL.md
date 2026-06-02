---
name: nvflare-convert-pytorch
description: "Convert existing PyTorch training code into an NVFLARE federated job using Client API model exchange, local validation, and job export; do not use for other frameworks or deployment-only tasks."
min_flare_version: "2.8.0"
blast_radius: edits_files
skill_version: "0.1.0"
---

# NVFLARE Convert PyTorch

## Use When

Use when the user asks to convert an existing PyTorch training script,
`torch.nn.Module`, `state_dict` workflow, data loader, checkpoint, or metric
loop into an NVFLARE federated training job.

## Do Not Use When

Do not use for PyTorch Lightning, Hugging Face Trainer, TensorFlow, XGBoost,
scikit-learn, Kubernetes deployment, production submission, or generic PyTorch
debugging that does not ask for FLARE conversion.

## Workflow

1. Run `nvflare agent inspect <path> --format json` before editing.
2. Identify the model definition, training loop, data loading, metrics, and
   checkpoint behavior.
3. Run `nvflare recipe list --framework pytorch --format json` and select the
   recipe from the requested FL workflow, not from PyTorch alone. Use FedAvg
   only for standard horizontal model-parameter aggregation.
4. Convert training exchange to the FLARE Client API: initialize FLARE, receive
   an `FLModel`, load `params` into the PyTorch model, train or evaluate, and
   send an `FLModel` with updated `params`, metrics, and useful metadata.
5. Add or update a `job.py` that uses the selected PyTorch recipe or job API
   path for local simulation and export.
6. Validate locally with `python job.py` and export with
   `python job.py --export --export-dir <dir>` using the FedJob system
   arguments.

## Natural User Requests

Users may describe the conversion in product terms, for example: "Here is my
PyTorch training code. Convert it to FLARE FL code, run it with 3 simulated
sites on this dataset, split the dataset evenly, use FedAvg, and train for 3
rounds." Extract recipe, site count, rounds, dataset path, split policy,
training args, validation intent, and approval boundaries from this wording
before asking follow-up questions.

Users may also approve a runtime handoff after simulation, for example:
"Simulation looks good. Start POC and submit the exported job" or "I have a POC
workspace here; submit the job to it." Treat this as explicit POC approval, then
validate the exported job path, use the supplied or created POC workspace, submit
the job, wait or monitor as requested, and report job ID, status, logs or result
paths, and any failure evidence.

Users may iterate on a generated job, for example: "Change the batch size to 64
and run it again", "Use 5 rounds", "Set min clients to 4", or "Switch from
FedAvg to SCAFFOLD and rerun." Treat hyperparameter and recipe changes as scoped
job updates. For recipe changes, rerun `nvflare recipe show <recipe-name>
--format json`, update `job.py` and client exchange only as required by the new
recipe, then rerun local validation and export if requested.

Users may ask for the "best" recipe or highest accuracy across available
recipes. Treat this as bounded experiment planning and execution, not as a
guarantee. Ask for the target metric and budget if missing, compare only
compatible PyTorch recipes from `nvflare recipe list --framework pytorch
--format json`, keep dataset split and training budget comparable, run requested
experiments, and report measured results, not claims without evidence.

Users may ask to rerun with different data distributions, for example: "Split
the dataset differently to represent IID and heterogeneous non-IID sites, train
again, and show me the result." Treat this as a data-partition experiment. Define
the split strategies, keep recipe and training budget comparable, avoid copying
private data into generated artifacts, rerun validation for each split, and
report measured metrics and result paths.

Users may ask to repeat an experiment with a different dataset from a URL. Treat
the URL as a user-provided data source, validate the download or access plan,
record dataset source/version details, follow the existing `download_data` and
`prepare_data` structure, preserve comparable recipe and training settings
unless asked to tune them, rerun validation, and report measured results and any
download, license, size, or preprocessing blocker.

Users may ask to generate synthetic data for each site. Treat this as a
data-generation and prepare/split step, not as a hidden change to training.
Infer shape, labels, and expected task type from the model, transforms, and data
loader only when they are clear. Otherwise ask for a data generation spec or an
approved generator/library. Follow the existing `download_data`/`prepare_data`
structure or hello-world conventions, make generation deterministic with seed
and site count, write per-site outputs explicitly, and report generated-data
schema and counts.

Users may ask to simulate site heterogeneity such as different training speed,
learning rate, batch size, epochs, or local workload per site. Prefer per-site
arguments or per-site config in `job.py` over copying the whole training script.
Create site-specific scripts only when the behavior cannot be represented by
arguments/config, and keep the shared training logic factored to avoid drift.

## Requirements

- Must keep edits scoped to training, model, job, and small config files.
- Must preserve user data paths and require user confirmation before changing
  them.
- Must translate natural user requests into concrete recipe, site-count,
  dataset, split, training, validation, and export settings.
- Must prefer synthetic or fixture data for validation when the original dataset is
  unavailable.
- Must report recipe choice, validation commands, export status, and remaining
  blockers before calling the conversion complete.
- Must not submit to POC or production without explicit user approval.
- Must not generate Python solely to wrap `nvflare` CLI commands or scrape
  human CLI output.

## Agent Responsibilities

- Run project inspection and recipe discovery before selecting a recipe.
- Explain the selected recipe when the user's algorithm intent is ambiguous.
- Convert Client API model exchange and generate or update `job.py`.
- Run local validation when dependencies and safe data are available.
- Apply requested hyperparameter, site-count, round-count, min-client, or recipe
  changes to the existing generated job and rerun validation.
- For recipe-search requests, define the metric, compatible recipes, run budget,
  and comparison plan before executing experiments.
- For data-distribution experiments, define IID/non-IID split strategies and
  compare measured results under the same recipe and training budget.
- For dataset-replacement experiments, record dataset source details, validate
  access/download assumptions, follow existing data-prep structure, and rerun
  with comparable settings.
- For synthetic-data experiments, add deterministic generation and per-site
  prepare outputs that follow existing data-prep conventions. Do not invent a
  synthetic data schema when the task, shape, labels, or expected behavior are
  unclear.
- For site-heterogeneity experiments, prefer site-specific args/config over
  duplicate scripts and report each site's settings.
- Export and inspect the exported job folder when export is requested.
- Submit to POC only when the user explicitly asks for POC after conversion or
  provides a POC workspace and asks for submission.
- Report commands run, status, result paths, failed checks, and user actions
  needed for unresolved blockers.

## User Input And Approval

- Ask the user to clarify FL workflow intent when recipe selection is uncertain.
- Ask before changing private data paths, replacing dataset access, or using
  non-fixture data for validation.
- Ask before POC, production, or startup-kit based runtime submission.

Load `references/recipe-selection.md` before creating `job.py`,
`references/pytorch-client-api-conversion.md` for conversion details, and
`references/job-validation.md` for validation and export guidance.
