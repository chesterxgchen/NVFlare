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
