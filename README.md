**NV**IDIA **F**ederated **L**earning **A**pplication **R**untime **E**nvironment

[NVIDIA FLARE](https://nvflare.readthedocs.io/en/main/index.html) is a domain-agnostic, open-source, extensible SDK that 
allows researchers and data scientists to adapt existing ML/DL workflows(PyTorch, TensorFlow, Scikit-learn, XGBoost) 
to a federated paradigm. It enables platform developers to build a secure, privacy-preserving offering 
for a distributed multi-party collaboration. 

**NVIDIA FLARE** is built on a componentized architecture that allows you to take federated learning workloads 
from research and simulation to real-world production deployment. Key components include:

* **Simulator** for rapid development and prototyping
* **Dashboard UI** for simplified project management and deployment  
* **Built-in FL algorithms** (e.g., FedAvg, FedProx, FedOpt, Scaffold, ditto )
* **Built-in workflows** (e.g., Scatter and Gather, Cyclic, Global Model Evaluation, Cross-site validation)
* **Built-in operators** that support horizontal and vertical federated learning (including multi-party private set intersection),
federated statistics, [XGBoost](https://github.com/dmlc/xgboost), [MONAI](https://monai.io), and traditional machine algorithms 
* **Privacy preservation** with differential privacy, homomorphic encryption, and privacy filters
* **Layered API** design for customization and extensibility
* **Deployment** on cloud and on premise 
* **Built-in support** for system resiliency and fault tolerance 

## Installation
To install the [current release](https://pypi.org/project/nvflare/), you can simply run:
```
$ python3 -m pip install nvflare
```
## Getting started

You can quickly get started using the [FL simulator](https://nvflare.readthedocs.io/en/main/quick_start.html).

A detailed [getting started](https://nvflare.readthedocs.io/en/main/getting_started.html) guide is available in the [documentation](https://nvflare.readthedocs.io/en/main/index.html).
 
Examples and notebook tutorials are located [here](https://github.com/NVIDIA/NVFlare/tree/main/examples/).

## Related talks and publications

For a list of talks, blogs, and publications related to NVIDIA FLARE, see [here](docs/publications_and_talks.md).

## License

NVIDIA FLARE has Apache 2.0 license, as found in [LICENSE](https://github.com/NVIDIA/NVFlare/blob/dev/LICENSE) file. 
