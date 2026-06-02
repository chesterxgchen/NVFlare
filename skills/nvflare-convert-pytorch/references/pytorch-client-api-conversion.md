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
