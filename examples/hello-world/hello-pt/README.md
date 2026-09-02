# Hello PyTorch

This quickstart trains a small image classifier with federated averaging (FedAvg). Two simulated clients train on
distinct local datasets for two rounds, and then evaluate the persisted final global model on separate evaluation
data. The zero-argument path is deterministic, runs on CPU, downloads no dataset, and requires no tracking service.

## Install

Create and activate a virtual environment, then install the example dependencies:

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
| Federated rounds | 2 |
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
These thresholds verify that federated training changed the model meaningfully; they are not benchmark claims.

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
├── synthetic_data.py  # Site- and split-specific default data
├── requirements.txt   # Default dependencies
└── README.md
```

## Client-side workflow

Most of [`client.py`](client.py) is ordinary PyTorch training code. The Client API adds the federated exchange:

```python
import nvflare.client as flare

flare.init()
while flare.is_running():
    input_model = flare.receive()
    model.load_state_dict(input_model.params)

    # Evaluate and train with this site's local data.
    global_accuracy = evaluate(model)
    steps = train(model)
    local_accuracy = evaluate(model)
    trained_params = {
        name: value.detach().cpu().clone()
        for name, value in model.state_dict().items()
    }
    flare.send(
        flare.FLModel(
            params=trained_params,
            metrics={
                "accuracy": global_accuracy,
                "accuracy_after_local_training": local_accuracy,
            },
            meta={"NUM_STEPS_CURRENT_ROUND": steps},
        )
    )
```

This is a focused excerpt; the complete client also handles evaluation and local-model submission tasks.

## Server-side workflow

[`job.py`](job.py) uses `FedAvgRecipe`, so the example does not need custom server code:

```python
recipe = FedAvgRecipe(
    name="hello-pt",
    min_clients=2,
    num_rounds=2,
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

Use a larger synthetic workload:

```bash
python job.py --train_size 1000 --test_size 200 --num_rounds 3
```

Use CIFAR-10 instead of the deterministic quickstart data:

```bash
python job.py --dataset cifar10 --epochs 2 --batch_size 16 --num_workers 2
```

CIFAR-10 is downloaded on first use. In this simulated example, each client receives its own local copy of the same
dataset; this option is useful for experimentation but does not demonstrate a federated data partition.

Enable TensorBoard explicitly:

```bash
python -m pip install tensorboard
python job.py --experiment_tracking tensorboard
```

Add full cross-site evaluation, including the clients' submitted local models:

```bash
python job.py --cross_site_eval
```

The default post-training workflow guarantees evaluation of the final global model. Full cross-site evaluation adds
the clients' final local models to the evaluation inventory.

The example also supports `--enable_log_streaming`, `--launch_external_process`, and
`--client_memory_gc_rounds`. See `python job.py --help` for details.

## Export a deployable job

```bash
python job.py --export --export-dir /tmp/nvflare/jobs/job_config
```

The exported job is written under `/tmp/nvflare/jobs/job_config/hello-pt`.

## Notebook

For an interactive CIFAR-10 and TensorBoard-oriented variant, see [`hello-pt.ipynb`](hello-pt.ipynb). The canonical
deterministic quickstart and its tested defaults are defined by `job.py`.
