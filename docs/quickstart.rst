############
Quick Start
############

This quick start guide means to help the user get FLARE up & running
quickly without introducing any advanced concepts. For more details, refer
to :ref:`getting_started`.

Since FLARE offers different modes of running the system, we only cover the simplest approaches here.
This quick start guide uses the **examples/hello-world/hello-numpy-sag** as an example.
You will find the details in the example's README.md file.

For now, you will need to clone the GitHub repo NVFLARE https://github.com/NVIDIA/NVFlare/tree/main (from the `main` branch) to get the examples.

We also assume you have worked with Python, already set up the virtual env.
If you are new to this, please refer :ref:`getting_started`.

#. **Install NVFLARE**

Install NVFLARE

.. code-block:: shell

  $ python3 -m pip install nvflare

Clone NVFLARE repo to get examples, switch main branch (the latest stable branch)

.. code-block:: shell

  $ git clone https://github.com/NVIDIA/NVFlare.git
  $ cd NVFlare
  $ git switch main

#. **Quick start with CLI**
Create a temp directory as workspace and install requirements/dependencies:

.. code-block:: shell
  $ mkdir -p /tmp/nvflare
  $ python3 -m pip install -r examples/hello-world/hello-numpy-sag/requirements.txt

#. **Quick Start with Simulator**

.. code-block:: shell

   nvflare simulator -w /tmp/nvflare/ -n 2 -t 2 examples/hello-world/hello-numpy-sag

Now you can watch the simulator run two clients (n=2) with two threads (t=2)
and logs are saved in the `/tmp/nvflare` workspace.

#. **Quick start with POC mode**
Instead of using the simulator, you can simulate the real deployment with
multiple processes via POC mode:

.. code-block:: shell

   $ nvflare poc --prepare -n 2
   $ nvflare poc --start -ex admin

From another terminal, start FLARE console:

.. code-block:: shell

   $ nvflare poc --start -p admin

Once FLARE Console started, you can check the status of the server.

.. code-block:: console
   $ check_status server
   $ submit_job hello-world/hello-numpy-sag
