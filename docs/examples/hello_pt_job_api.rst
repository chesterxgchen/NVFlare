.. _hello_pt_job_api:

Hello PyTorch with the Job API
==============================

The maintained Hello PyTorch Job API walkthrough is now consolidated in
:doc:`../hello-world/hello-pt/index`. Its zero-argument path uses deterministic,
site-distinct synthetic data, one local epoch per round, optional experiment
tracking, and final-global-model evaluation. CIFAR-10 is an explicit follow-up
rather than a first-run dependency.

The same ``job.py`` also demonstrates the execution-environment progression:

.. code-block:: bash

   python job.py
   python job.py --env poc
   python job.py --env prod --startup-kit /path/to/admin/startup-kit

These commands reuse one
:class:`FedAvgRecipe<nvflare.app_opt.pt.recipes.fedavg.FedAvgRecipe>`, model,
client script, and local training loop. Simulation is the fast first run, POC
checks separate local processes, and production requires an existing
provisioned deployment and authorized startup kit.

See the :github_nvflare_link:`example README <examples/hello-world/hello-pt/README.md>`
for the authoritative commands, options, artifacts, data contract, and
limitations. For general concepts, see :ref:`Client API <client_api>` and
:ref:`Available Recipes <available_recipes>`.
