# FedAvg: simplified

This example illustrates two features:
* How to perform Kaplan-Meirer Survival Analysis in federated setting
* How to use the new Flare Communicator API to contract a workflow: no need to write a controller.  

## FLARE Controller Communicator API

The Flare controller Communicator API only has small set APIs
* flare_comm = Communicator()
* flare_comm.init()
* flare.broadcast()

## Writing a new Workflow

With this new API writing the new workflow is really simple: 

For example for Kaplan-Meier Analysis, we could write a new workflow like this: 

* Controller Workflow (Server)

```

class FedAvg(WF):
    def __init__(self,
                 min_clients: int,
                 num_rounds: int,
                 output_path: str,
                 start_round: int = 1,
                 early_stop_metrics: dict = None,
                 model_format: str = None
                 ):
        super(FedAvg, self).__init__()
        self.logger = logging.getLogger(self.__class__.__name__)
        
        <skip .... init code .... >
 
        # (1) init flare_comm
        self.flare_comm = WFComm(result_check_interval=10)
        self.flare_comm.init(self)
        
    def run(self):
        net = Net()
        model = FLModel(params=net.state_dict(), params_type=ParamsType.FULL)
        for current_round in range(self.start_round, self.start_round + self.num_rounds):
        
            if self.early_stop_cond(model.metrics, self.early_stop_metrics):
                self.logger.info("early stop condition satisfied, stopping")
                break
            else:
                self.logger.info("early stop condition NOT satisfied, continue")

            self.current_round = current_round
            self.logger.info(f"Round {current_round}/{self.num_rounds} started.")

            self.logger.info("Scatter and Gather")
            sag_results = self.scatter_and_gather(model, current_round)

            self.logger.info("fed avg aggregate")
            aggr_result = self.aggr_fn(sag_results)

            self.logger.info(f"aggregate metrics = {aggr_result.metrics}")

            self.logger.info("update model")

            model = FLModelUtils.update_model(model, aggr_result)

            self.logger.info(f"best model selection")
            self.select_best_model(model)

        self.logger.info(f"save_model")
        self.save_model(self.best_model, self.output_path)

    def scatter_and_gather(self, model: FLModel, current_round):
        msg_payload = {"min_responses": self.min_clients,
                       "current_round": current_round,
                       "num_round": self.num_rounds,
                       "start_round": self.start_round,
                       "data": model}

        # (2) broadcast and wait
        results = self.flare_comm.broadcast_and_wait(msg_payload)
        return results

```

The base class ```WF``` is define as

```
class WF(ABC):

    @abstractmethod
    def run(self):
        raise NotImplemented
```
is mainly make sure user define ```run()``` method
 
## Configurations

### client-side configuration

This is the same as FLARE Client API configuration

### server-side configuration

  Server side controller is really simple, all we need is to user TaskController with newly defined workflow class
```KM```

```
{
  # version of the configuration
  format_version = 2
  task_data_filters =[]
  task_result_filters = []

  workflows = [
      {
        id = "fed_avg"
        path = "nvflare.app_common.workflows.wf_controller.WFController"
        args {
            task_name = "train"
            wf_class_path = "fedavg_wf.FedAvg",
            wf_args {
                min_clients = 2
                num_rounds = 10
                output_path = "/tmp/nvflare/fedavg/mode.pth"
                model_format = "torch"
                early_stop_metrics {
                    accuracy = 55
                }

            }
        }
      }
  ]

  components = []

}

```


## Run the job

assume current working directory is at ```hello-fedavg``` directory 

```
nvflare simulator job -w /tmp/nvflare/km/job -n 2 -t 2
```
