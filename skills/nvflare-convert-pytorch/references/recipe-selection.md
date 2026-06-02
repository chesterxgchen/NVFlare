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

After selecting a candidate recipe, inspect its parameters:

```bash
nvflare recipe show <recipe-name> --format json
```

## Quick Algorithm Guide

If the user does not know which FL algorithm they need, explain the choices in
plain language before editing `job.py`:

- FedAvg: the default starting point for most horizontal FL jobs. Each site
  trains locally, sends model weights or updates, and the server averages them.
  Use this when the user simply asks to federate normal PyTorch training.
- FedAvg with HE: FedAvg plus homomorphic encryption support for protected
  aggregation. Use only when the user asks for HE or encrypted aggregation.
- FedProx: FedAvg-style training with a proximal term in the client loss to
  improve stability when site data or compute behavior is very different.
- FedOpt: server-side optimizer variants such as FedAdam, FedYogi, or FedAdagrad.
  Use when the user wants server optimizer control or better behavior than plain
  averaging on heterogeneous data.
- SCAFFOLD: adds control variates to reduce client drift on non-IID data. Use
  when the user specifically asks for SCAFFOLD or drift mitigation.
- Cyclic: sends the model through clients sequentially instead of aggregating
  updates on the server. Use when the requested workflow is client-to-client or
  cyclic weight transfer.
- Swarm Learning: peer/client-parent aggregation topology instead of a normal
  server-centered FedAvg topology. Use when the user asks for swarm learning.
- FedEval: evaluation-only. Use when the user wants to distribute a checkpoint
  to sites and collect metrics without federated training updates.

For deeper background, see the algorithm papers for
[FedAvg](https://proceedings.mlr.press/v54/mcmahan17a.html),
[FedProx](https://arxiv.org/abs/1812.06127),
[FedOpt](https://openreview.net/forum?id=LkFG3lB13U5),
[SCAFFOLD](https://proceedings.mlr.press/v119/karimireddy20a.html), and
[Swarm Learning](https://www.nature.com/articles/s41586-021-03583-3). For
Cyclic recipes, use the local catalog and
`nvflare recipe show cyclic-pt --format json`.

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
