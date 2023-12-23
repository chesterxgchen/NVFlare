from typing import List

from net import Net
from nvflare.app_common.abstract.fl_model import FLModel, ParamsType
from nvflare.app_common.utils.fl_model_utils import FLModelUtils
from nvflare.app_common.workflows.flare_ctrl.wf_spec import WF


# Server Workflow

class FedAvg(WF):
    def __init__(self,
                 min_clients: int,
                 output_path: str,
                 num_rounds: int,
                 stop_metrics: dict = None
                 ):
        super(FedAvg, self).__init__()

        self.output_path = output_path
        self.min_clients = min_clients
        self.num_rounds = num_rounds

        # (1) init flare_comm
        self.flare_comm.init(self)
        self.best_model = None

        # early stop metrics values: accuracy, auc, loss, running_loss
        self.stop_metrics = stop_metrics

    def run(self):
        net = Net()
        model = FLModel(params=net.state_dict(), params_type=ParamsType.FULL)

        for current_round in range(0, self.num_rounds):

            if self.stop_cond(model.metrics, self.stop_metrics):
                return

            print(f"Round {current_round}/{self.num_rounds} started.")

            print(f"Scatter and Gather")
            results = self.scatter_and_gather(model, current_round)

            print(f"Aggregate.")
            aggr_results = self.aggr_fn(results)

            print(f"update model")
            model = self.update_model(model, aggr_results)

            print(f"best model selection")
            best_model = self.best_model_fn(model)
            self.best_model = best_model

            print(f"save_model")
            self.save(best_model, "/tmp/nvflare/fed_avg/model/")

    def scatter_and_gather(self, model: FLModel, current_round):
        msg_payload = {"min_responses": self.min_clients,
                       "current_round": current_round,
                       "data": model}

        # (2) broadcast and wait
        results = self.flare_comm.broadcast(msg_payload)
        return results

    def aggr_fn(self, task_result: dict) -> FLModel:
        pass

    def save(self, model: FLModel, file_path: str):
        pass

    def update_model(self, model: FLModel, aggr_results) -> FLModel:
        return FLModelUtils.update_model(model, aggr_results)

    def best_model_fn(self, model) -> FLModel:
        pass

    def stop_cond(self, metrics: dict, stop_metrics: dict):
        if stop_metrics is None:
            return False

        key = "accuracy"
        if key in stop_metrics:
            value = metrics.get(key, -100)
            target_value = stop_metrics.get(key, -1)
            if value >= target_value:
                return True

        key = "auc"
        if key in stop_metrics:
            value = metrics.get(key, -100)
            target_value = stop_metrics.get(key, -1)
            if value >= target_value:
                return True

        key = "loss"
        if key in stop_metrics:
            value = metrics.get(key, 1e+10)
            target_value = stop_metrics.get(key, -1)
            if value <= target_value:
                return True

        key = "running_loss"
        if key in stop_metrics:
            value = metrics.get(key, 1e+10)
            target_value = stop_metrics.get(key, -1)
            if value <= target_value:
                return True
