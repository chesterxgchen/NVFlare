.. _hello_pt:

Hello PyTorch
=============

Hello PyTorch is the recommended first federated-learning example for PyTorch.
It uses :class:`FedAvgRecipe<nvflare.app_opt.pt.recipes.fedavg.FedAvgRecipe>`
with ordinary PyTorch model, data-loading, training, and evaluation code.

The zero-argument path is deterministic, CPU-safe, and offline. Two clients
train on distinct synthetic image data for two federated rounds, and the
persisted final global model is evaluated on separate site-local evaluation
data. CIFAR-10 and TensorBoard remain explicit follow-up options.

The :github_nvflare_link:`example README <examples/hello-world/hello-pt/README.md>`
is the authoritative reference for every option, default, artifact, and
troubleshooting note. This page provides the guided first-run path.

Get and install the example
---------------------------

Create and activate a Python virtual environment, then get the source and enter
the example directory:

.. code-block:: bash

   git clone https://github.com/NVIDIA/NVFlare.git
   cd NVFlare/examples/hello-world/hello-pt

Install the dependencies from that directory:

.. code-block:: bash

   python -m pip install -r requirements.txt

For alternative installation methods, see :ref:`installation`.

Run the quickstart
------------------

.. code-block:: bash

   python job.py

The default run uses two simulated clients, two federated rounds, one local
epoch per round, and no data download or tracking service. Each client receives
its own reproducible training and evaluation samples. Labels are encoded by
class-specific image regions, giving the small convolutional network a genuine
and testable learning signal instead of unrelated random images and labels.

The client script follows the Client API lifecycle:

1. Receive the current global model.
2. Evaluate that received model.
3. Train it on the client's local data.
4. Send updated model parameters, metrics, and completed optimizer-step count.

Raw examples remain at the client. The server performs weighted FedAvg
aggregation, persists the final global model, and requests its final evaluation
on both sites.

Inspect the result
------------------

The command prints the result directory. For the default simulation it is
``/tmp/nvflare/simulation/hello-pt``. The primary artifacts under
``server/simulate_job`` are:

- ``app_server/FL_global_model.pt`` -- the persisted final global model.
- ``cross_site_val/cross_val_results.json`` -- final evaluation metrics by site.

The automated acceptance test requires at least 60% final accuracy on both
sites and at least a 40 percentage-point improvement over the initial global
model. These thresholds prove that the example learns; they are not benchmark
claims.

Continue across environments
----------------------------

After simulation succeeds, run the same Recipe, model, client script, and local
training loop through a local POC federation:

.. code-block:: bash

   python job.py --env poc

POC starts separate local server and client processes, submits and monitors the
job, downloads the result, and stops the services. It is an optional
second-stage check and takes longer than simulation because of that lifecycle.
The printed result path and POC logs remain available after the services stop.

A production submission requires a running provisioned deployment, network
connectivity, and an authorized admin startup kit:

.. code-block:: bash

   python job.py --env prod --startup-kit /path/to/admin/startup-kit

You can instead export the same application without connecting to a federation:

.. code-block:: bash

   python job.py --export --export-dir /tmp/nvflare/jobs/job_config

Export verifies construction of the deployable job. It does not verify
production connectivity, identity, authorization, or external execution. See
:ref:`provisioned_setup` for production deployment procedures.

Optional follow-up paths
------------------------

Run ``python job.py --help`` for the complete example and Recipe export options.
Useful follow-ups include:

.. code-block:: bash

   # Download and use CIFAR-10 explicitly.
   python job.py --dataset cifar10 --epochs 2 --batch_size 16 --num_workers 2

   # Enable TensorBoard after installing it.
   python -m pip install tensorboard
   python job.py --experiment_tracking tensorboard

   # Also evaluate the clients' final local models.
   python job.py --cross_site_eval

For the API concepts behind the example, continue with
:ref:`Client API <client_api>` and :ref:`Available Recipes <available_recipes>`.
