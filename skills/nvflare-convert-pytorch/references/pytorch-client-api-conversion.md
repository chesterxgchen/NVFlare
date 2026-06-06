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

For PyTorch conversions, create generated FLARE source in a separate job folder
unless the user asks for in-place conversion. Prefer
`<project>/nvflare_jobs/<job_name>/` for source files. Keep exported jobs,
simulation workspaces, generated model artifacts, and temporary caches out of
the original training-code root by default; use explicit runtime locations under
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

## Reference Examples

- `examples/hello-world/hello-pt/client.py`
- `examples/hello-world/hello-pt/job.py`
- `examples/advanced/cifar10/pt`

`hello-pt` uses FedAvg. Load `recipe-selection.md` before creating or updating
`job.py` so the selected recipe matches the user's requested FL workflow.
