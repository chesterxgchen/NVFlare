from nvflare.app_common.abstract.fl_model import FLModel
from nvflare.app_common.workflows.base_fedavg import BaseFedAvg


import torch
import torch.nn as nn
import torch.nn.functional as F


class Net(nn.Module):
    def __init__(self):
        super().__init__()
        self.conv1 = nn.Conv2d(3, 6, 5)
        self.pool = nn.MaxPool2d(2, 2)
        self.conv2 = nn.Conv2d(6, 16, 5)
        self.fc1 = nn.Linear(16 * 5 * 5, 120)
        self.fc2 = nn.Linear(120, 84)
        self.fc3 = nn.Linear(84, 10)

    def forward(self, x):
        x = self.pool(F.relu(self.conv1(x)))
        x = self.pool(F.relu(self.conv2(x)))
        x = torch.flatten(x, 1)  # flatten all dimensions except batch
        x = F.relu(self.fc1(x))
        x = F.relu(self.fc2(x))
        x = self.fc3(x)
        return x


class FedAvg2(BaseFedAvg):
    def __init__(self,
                 min_clients: int = 1000,
                 num_rounds: int = 5,
                 persist_every_n_rounds: int = 1,
                 model_init_fn=None,
                 persist_fn=None,
                 aggregate_fn=None,
                 best_model_selector=None,
                 stop_fn=None,
                 ):
        super().__init__(min_clients=min_clients,
                         num_rounds=num_rounds,
                         persist_every_n_rounds=persist_every_n_rounds,
                         )
        self.min_clients = min_clients
        self.num_rounds = num_rounds
        self.model_init_fn = model_init_fn if model_init_fn else self.default_model_init_fn()
        self.persist_fn = persist_fn if persist_fn else self.default_persist_fn()
        self.aggregate_fn = aggregate_fn if aggregate_fn else self.default_aggregate_fn()
        self.best_model_selector = best_model_selector if best_model_selector else self.default_best_model_selector
        self.stop_fn = stop_fn if stop_fn else self.default_stop_fn


    def default_model_init_fn(self):
        net = Net()

    def default_persist_fn(self):
        pass

    def default_aggregate_fn(self):
        pass

    def default_best_model_selector(self, model: FLModel):
        return model

    def default_stop_fn(self):
        return self._current_round > self._num_rounds

    def run(self) -> None:
        self.info("Start FedAvg.")

        while not self.stop_fn():
            self.info(f"Round {self._current_round} started.")

            clients = self.sample_clients(self._min_clients)

            results = self.send_model_and_wait(targets=clients, data=self.model)

            aggregate_results: FLModel = self.aggregate(results, aggregate_fn=self.aggregate_fn)

            best_model = self.best_model_selector(aggregate_results)
            self.persist_fn(best_model)

        self.info("Finished FedAvg.")
