# Kaplan-Meier Analysis

This example illustrates two features:
* How to perform Kaplan-Meirer Survival Analysis in federated setting
* How to use the new Flare Communicator API to contract a workflow: no need to write a controller.  

## FLARE Controller Communicator API

The Flare controller Communicator API only has small set APIs
* flare_comm = Communicator()
* flare_comm.init()
* flare.broadcast()
* flare.send() (todo)

## Writing a new Workflow

With this new API writing the new workflow is really simple: 

For example for Kaplan-Meier Analysis, we could write a new workflow like this: 

```
class KM(WF):
    def __init__(self,
                 min_clients: int,
                 output_path: str):
        self.output_path = output_path
        self.min_clients = min_clients
        self.num_rounds = 1
        self.flare_comm = Communicator()
        self.flare_comm.init(self)

    def run(self):
        results = self.start_km_analysis()
        global_res = self.aggr_km_result(results)
        self.save(global_res, self.output_path)

```

The base class ```WF``` is define as

```
class WF(ABC):

    @abstractmethod
    def run(self):
        raise NotImplemented
```
is mainly make sure user define ```run()``` method

for kM analysis, it literal involves

* start the analysis --> ask all clients to perform local KM analysis, then wait for results 
* then aggregate the result to obtain gloabl results
* save the result

We only need to one_round trip from server --> client, client --> server  

```
    def run(self):
        results = self.start_km_analysis()
        global_res = self.aggr_km_result(results)
        self.save(global_res, self.output_path)

```

Let's define the start_km_analysis()

```
    def start_km_analysis(self):
        msg_payload = {"min_responses": self.min_clients}
        results = self.flare_comm.broadcast(msg_payload)
        return results
```

looks like to simply call send broadcast command, then just get the results.  
**self.flare_comm.broadcast(msg_payload)**
