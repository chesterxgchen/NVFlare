# Hello PyTorch

This quickstart trains a small image classifier with federated averaging (FedAvg). Two simulated clients train on
independently generated local datasets for three rounds, and then evaluate the persisted final global model on
separate evaluation data. The zero-argument path is deterministic, runs on CPU, downloads no dataset, and requires no
tracking service.

## Install

Create and activate a virtual environment, then get the source and enter the
example directory:

```bash
git clone https://github.com/NVIDIA/NVFlare.git
cd NVFlare/examples/hello-world/hello-pt
```

Install the example dependencies from that directory:

```bash
python -m pip install -r requirements.txt
```

For other installation options, see the [NVFlare installation guide](https://nvflare.readthedocs.io/en/main/installation.html).

## Run the default quickstart

```bash
python job.py
```

The default run uses:

| Setting | Default |
| --- | --- |
| Dataset | Deterministic synthetic images with a class-related signal |
| Clients | 2 |
| Federated rounds | 3 |
| Local epochs per round | 1 |
| Training examples per client | 200 |
| Evaluation examples per client | 100 |
| Batch size | 32 |
| Data-loader workers | 0 |
| Experiment tracking | Off |
| Post-training evaluation | Final global model on both clients |

Results are written under `/tmp/nvflare/simulation/hello-pt`. The two primary outputs are:

- `server/simulate_job/app_server/FL_global_model.pt`: the persisted final global model.
- `server/simulate_job/cross_site_val/cross_val_results.json`: evaluation metrics by client and model.

In the evaluation JSON, use the `SRV_FL_global_model.pt` result for each site. The automated acceptance test requires
at least 60% accuracy on both sites and at least a 40 percentage-point improvement over the initial global model.
These thresholds are calibrated to the fixed model and data seeds with the three-round default. They verify that this
specific federated run changed the model meaningfully; they are not guarantees for other initializations or
hyperparameters and are not benchmark claims.

## Why this default is better than the previous version

The previous zero-argument run selected CIFAR-10, so it depended on a network download and could fail in an offline
or restricted environment. Its optional synthetic path used random images and random labels with no relationship
between them. A model cannot learn a repeatable classification rule from that data, so a successful job process did
not demonstrate successful learning. The simulated clients also used the same CIFAR-10 data, and final global-model
evaluation was optional.

The new default addresses those problems directly:

- Each label is represented by a bright image region at a class-specific position, giving the model a simple,
  verifiable signal to learn.
- Site and split seeds make runs reproducible while keeping each client's training data and evaluation data distinct.
- The bounded CPU workload runs without a dataset download, TensorBoard, or extra command-line flags.
- The primary `accuracy` metric measures the received global model, keeping server-side best-model selection aligned
  with that exact model. `accuracy_after_local_training` separately shows the immediate local training progress.
- The persisted final global model is evaluated on both clients by default, and an integration test loads the artifact
  and enforces the learning thresholds above.
- CIFAR-10 and TensorBoard remain available as explicit options for users who want them.

The data remains local to each client. Clients send model parameters, evaluation metrics, and the number of completed
optimizer steps; they do not send their training examples to the server.

## Code structure

```text
hello-pt/
├── client.py          # Client-side training and evaluation
├── job.py             # FedAvg recipe and simulation entry point
├── model.py           # PyTorch model definition and deterministic initialization
├── prepare_data.py    # Site- and split-specific default data preparation
├── requirements.txt   # Default dependencies
└── README.md
```

## Client-side workflow

Most of [`client.py`](client.py) is ordinary PyTorch training code. The block below is the actual task loop from that
file, with only its indentation normalized. The complete `main()` initializes `client_name`, `model`, `optimizer`,
`loss`, `train_loader`, `test_loader`, `device`, `summary_writer`, `last_params`, and the parsed `args` immediately
before this loop. The module imports `torch` and `nvflare.client` (as `flare`), defines `LOCAL_MODEL_PATH`, and calls
`flare.init()` before entering the loop.

```python
while flare.is_running():
    # (4) receives FLModel from NVFlare
    input_model = flare.receive()
    print(f"site = {client_name}, current_round={input_model.current_round}")

    # Cross-site evaluation requests the client's latest local model without
    # sending model parameters in the request.
    if flare.is_submit_model():
        if last_params is None:
            error_msg = "submit_model called before a local model was trained"
            print(f"ERROR: {error_msg}")
            # TaskScriptRunner converts this exception into TOPIC_ABORT so the
            # executor can report the task failure instead of waiting for a result.
            raise RuntimeError(error_msg)
        print(f"site = {client_name}, submitting local model")
        flare.send(flare.FLModel(params=last_params))
        continue

    # (5) loads model from NVFlare
    model.load_state_dict(input_model.params)
    # (6) evaluate the received global model before local training
    accuracy_before_training = evaluate(model, test_loader, device)

    # (optional) Task branch for cross-site evaluation
    if flare.is_evaluate():
        print(f"site = {client_name}, running cross-site evaluation")
        # For CSE, just return the evaluation metrics without training
        output_model = flare.FLModel(metrics={"accuracy": accuracy_before_training})
        flare.send(output_model)
        continue

    steps = args.epochs * len(train_loader)
    for epoch in range(args.epochs):
        running_loss = 0.0
        for i, batch in enumerate(train_loader):
            images, labels = batch[0].to(device), batch[1].to(device)
            optimizer.zero_grad()

            predictions = model(images)
            cost = loss(predictions, labels)
            cost.backward()
            optimizer.step()

            running_loss += cost.item()
        avg_loss = running_loss / len(train_loader)
        print(f"site={client_name}, epoch={epoch + 1}/{args.epochs}, loss={avg_loss:.4f}")
        if summary_writer:
            global_step = input_model.current_round * args.epochs + epoch
            summary_writer.add_scalar(tag="train_loss", scalar=avg_loss, global_step=global_step)

    print(f"Finished Training for {client_name}")
    trained_accuracy = evaluate(model, test_loader, device)

    last_params = {name: param.detach().cpu().clone() for name, param in model.state_dict().items()}
    torch.save(last_params, LOCAL_MODEL_PATH)

    # (7) construct trained FL model
    output_model = flare.FLModel(
        params=last_params,
        # The primary metric evaluates the received global model, which is
        # the model the server considers for best-model selection. Report
        # the trained local model separately to make progress visible.
        metrics={
            "accuracy": accuracy_before_training,
            "accuracy_after_local_training": trained_accuracy,
        },
        meta={"NUM_STEPS_CURRENT_ROUND": steps},
    )
    print(f"site: {client_name}, sending model to server.")
    # (8) send model back to NVFlare
    flare.send(output_model)
```

The linked file is the runnable source; this excerpt introduces no alternate helper functions or signatures.

## Server-side workflow

[`job.py`](job.py) uses `FedAvgRecipe`, so the example does not need custom server code:

```python
recipe = FedAvgRecipe(
    name="hello-pt",
    min_clients=2,
    num_rounds=3,
    model=create_model(),
    train_script="client.py",
    train_args="...",
)
add_final_global_evaluation(recipe)
recipe.execute(SimEnv(num_clients=2))
```

The recipe initializes the global model, sends it to selected clients, collects local updates, performs weighted
FedAvg aggregation, persists the result, and requests the final evaluation.

## Customize the run

See all options:

```bash
python job.py --help
```

Use CIFAR-10 instead of the deterministic quickstart data:

Simulated clients share the cache at `/tmp/nvflare/data`. If CIFAR-10 is not
already present, download both splits once before starting the simulation;
concurrent first-use downloads from multiple clients can race:

```bash
python - <<'PY'
from torchvision.datasets import CIFAR10

for train in (True, False):
    CIFAR10(root="/tmp/nvflare/data", train=train, download=True)
PY
```

```bash
python job.py --dataset cifar10
```

All simulated clients then read the same logical CIFAR-10 training and test
datasets from that shared cache. This option is useful for experimentation but
does not demonstrate a federated data partition. The default synthetic path
remains offline and gives every site distinct training and evaluation samples.

The beginner entry point intentionally exposes only the number of clients,
number of rounds, and dataset choice. Environment selection, experiment
tracking, full cross-site evaluation, external-process execution, and memory
tuning belong in the environment-continuity follow-up rather than the first
federated-learning run.

## Export a deployable job

```bash
python job.py --export --export-dir /tmp/nvflare/jobs/job_config
```

The exported job is written under `/tmp/nvflare/jobs/job_config/hello-pt`.

## Notebook

For an interactive CIFAR-10 and TensorBoard-oriented variant, see [`hello-pt.ipynb`](hello-pt.ipynb). The canonical
deterministic quickstart and its tested defaults are defined by `job.py`.
