# PyTorch Recipe Selection

PyTorch identifies the training framework; it does not determine the federated
workflow. Choose the recipe from the user's FL intent, topology, and aggregation
requirements.

## Discover Recipes

Run the local recipe catalog before creating or updating `job.py`:

```bash
nvflare recipe list --framework pytorch --format json
```

Use the returned recipe metadata as the source of truth for recipe names,
modules, classes, algorithms, aggregation mode, state exchange, privacy metadata,
and optional dependencies.

## Selection Rules

- Use `fedavg-pt` for standard horizontal federated training where clients train
  the same PyTorch model locally and the server aggregates model weights or
  weight diffs across rounds.
- Use `fedavg-he-pt` when the user asks for FedAvg with homomorphic encryption.
- Use `fedprox-pt` when the user asks for FedProx or proximal loss behavior.
- Use `fedopt-pt` when the user asks for server-side optimizer variants such as
  FedAdam, FedYogi, or FedAdagrad behavior.
- Use `scaffold-pt` when the user asks for SCAFFOLD-style control variates or
  client-drift mitigation.
- Use `cyclic-pt` when the user asks for sequential client-to-client model
  transfer rather than server aggregation.
- Use `swarm-pt` when the user asks for swarm learning or peer/client-parent
  aggregation topology.
- Use `fedeval-pt` for evaluation-only jobs that send a checkpoint to sites and
  collect metrics without local training updates.
- Ask the user before choosing when the requested FL workflow is not clear.

## Example Scope

`examples/hello-world/hello-pt` is the FedAvg reference example. It is useful for
standard Client API model exchange and FedAvg `job.py` structure, but it should
not be treated as the universal PyTorch recipe. For non-FedAvg workflows, use the
matching recipe from the catalog and keep the PyTorch Client API exchange aligned
with that recipe's expected task names, metadata, and parameter format.
