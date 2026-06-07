# PyTorch Client API Conversion

This reference covers standard PyTorch training loops that already have a
`torch.nn.Module`, optimizer, data loaders, and metrics.

## Conversion Pattern

- Import `nvflare.client as flare`.
- Call `flare.init()` before the training loop that participates in FLARE.
- Loop while `flare.is_running()`.
- Call `flare.receive()` to get the incoming `FLModel`.
- Load `input_model.params` into the PyTorch model with `load_state_dict`.
- Train or evaluate using the user's existing data loader and optimizer.
- Send `flare.FLModel(params=model.cpu().state_dict(), metrics=..., meta=...)`
  with `flare.send(...)`.

## Generated Source Layout

For PyTorch conversions, honor the user's requested target location. If the user
does not specify one, choose a scoped location that avoids overwriting original
training files; a separate generated folder such as
`<project>/nvflare_jobs/<job_name>/` is allowed but not required. Keep exported
jobs, simulation workspaces, generated model artifacts, and temporary caches out
of the source-code root by default; use explicit runtime locations under
`/tmp/nvflare/` unless the user provides another path.

The generated job folder should normally contain:

- `client.py`: FLARE Client API entry point;
- `job.py`: recipe or FedJob builder, simulation entry point, and export entry
  point;
- `model.py`: copied, wrapped, or imported model definition when needed;
- `requirements.txt` or a small requirements file only when dependencies differ
  from the source project.

Avoid names such as `fl_train.py` for the generated FLARE Client API entry
point unless the user explicitly requests that naming. Keep the original
`train.py` intact as the source training reference.

For standard FedAvg, package shared generated files for all clients. Do not
replace all-client deployment with explicit per-site deployment unless the
conversion has real per-site differences such as different scripts, arguments,
data-split settings, or launch behavior.

## Model Construction Consistency

The model created by `job.py` for the server-side initial model and the model
created by `client.py` before `load_state_dict` must have matching constructor
arguments and state-dict shapes. When the original model needs arguments such as
input dimension, vocabulary size, number of classes, hidden size, or dropout,
make those values explicit in both places.

Acceptable patterns include:

- a shared `model_args` dict imported by both `job.py` and `client.py`;
- a small JSON/config file read by both sides;
- explicit CLI arguments passed through recipe `train_args` and parsed by
  `client.py`, with the same values used in `job.py`.

Before simulation, validate the generated model construction path when possible
by instantiating the server-side and client-side model with the same arguments
and checking that `load_state_dict` can accept the initial parameters. Treat a
state-dict key or tensor-shape mismatch as a conversion bug, not as a reason to
change the model architecture without user approval.

## Evaluation Branch

When the task is evaluation-only, use `flare.is_evaluate()` to send metrics
without local training.

## Scope Boundaries

- Keep user model architecture and loss function unless the user asks for a
  change.
- Keep data loading local to the site and do not add code that copies private
  data into generated artifacts.
- For checkpoints, preserve user checkpoint semantics and document what is
  federated versus site-local.
- For metrics, send scalar summaries in the `metrics` field and keep rich
  tracking artifacts in the normal experiment-tracking path.

## Job Pattern Reference

Load `recipe-selection.md` before creating or updating `job.py` so the selected
recipe matches the user's requested FL workflow. Do not assume NVFLARE
repository examples are available in the user's environment.
