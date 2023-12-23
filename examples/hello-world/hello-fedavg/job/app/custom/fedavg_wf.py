from nvflare.app_common.utils.fl_model_utils import FLModelUtils

from net import Net
from nvflare.app_common.abstract.fl_model import FLModel, ParamsType
from nvflare.app_common.workflows.flare_ctrl.wf_spec import WF


# Server Workflow

class FedAvg(WF):
    def __init__(self,
                 min_clients: int,
                 output_path: str):
        super(FedAvg, self).__init__()

        self.output_path = output_path
        self.min_clients = min_clients
        self.num_rounds = 10
        self.flare_comm.init(self)
        self.best_model = None

    def run(self):
        net = Net()
        model = FLModel(params=net.state_dict(), params_type=ParamsType.FULL)

        for current_round in range(0, self.num_rounds):
            print(f"Round {current_round}/{self.num_rounds} started.")

            print(f"Scatter and Gather")
            results = self.scatter_and_gather(model)

            print(f"Aggregate.")
            aggr_results = self.aggr_fn(results)

            print(f"update model")
            model = self.update_model(model, aggr_results)

            print(f"best model selection")
            best_model = self.best_model_fn(model)
            self.best_model = best_model

            print(f"save_model")
            self.save(best_model, "/tmp/nvflare/fed_avg/model/")

    def scatter_and_gather(self, model: FLModel):
        msg_payload = {"min_responses": self.min_clients,
                       "data": model}
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
