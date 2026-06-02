---
name: nvflare-convert-pytorch
description: "Convert existing PyTorch training code into an NVFLARE federated job using Client API model exchange, local validation, and job export; do not use for other frameworks or deployment-only tasks."
min_flare_version: "2.8.0"
blast_radius: edits_files
skill_version: "0.1.0"
---

# NVFLARE Convert PyTorch

Use when the user asks to convert an existing PyTorch training script,
`torch.nn.Module`, `state_dict` workflow, data loader, checkpoint, or metric
loop into an NVFLARE federated training job.

Do not use for PyTorch Lightning, Hugging Face Trainer, TensorFlow, XGBoost,
scikit-learn, Kubernetes deployment, production submission, or generic PyTorch
debugging that does not ask for FLARE conversion.

## Workflow

1. Run `nvflare agent inspect <path> --format json` before editing.
2. Identify the model definition, training loop, data loading, metrics, and
   checkpoint behavior.
3. Convert training exchange to the FLARE Client API: initialize FLARE, receive
   an `FLModel`, load `params` into the PyTorch model, train or evaluate, and
   send an `FLModel` with updated `params`, metrics, and useful metadata.
4. Add or update a `job.py` that uses an appropriate PyTorch recipe or job API
   path for local simulation and export.
5. Validate locally with `python job.py` and export with
   `python job.py --export --export-dir <dir>` when the job supports export.

## Checklist

- Keep edits scoped to training, model, job, and small config files.
- Preserve user data paths and require user confirmation before changing them.
- Prefer synthetic or fixture data for validation when the original dataset is
  unavailable.
- Do not submit to POC or production without explicit user approval.
- Do not generate Python solely to wrap `nvflare` CLI commands or scrape human
  CLI output.

Load `references/pytorch-client-api-conversion.md` for conversion details and
`references/job-validation.md` for validation and export guidance.
