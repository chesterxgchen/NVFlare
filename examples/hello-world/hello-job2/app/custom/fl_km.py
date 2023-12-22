import time

from nvflare.app_common.workflows.flare_ctrl.communicator import Communicator
from nvflare.app_common.workflows.flare_ctrl.wf_spec import WF

# Server controller


class KM(WF):
    def __init__(self, min_clients: int):
        self.min_clients = min_clients
        self.num_rounds = 1
        self.flare_comm = Communicator()
        self.flare_comm.init(self)
        print("sleep for 2 send to let pipe setup")
        time.sleep(2)

    def run(self):
        print("init_fn()")
        time.sleep(2)
        results = self.init_fn()
        print("after init_fn()")
        global_res = self.aggregate_fn(results)
        print("after aggregate_fn()")
        self.persist_fn(global_res, "/tmp/km/result")
        print("after persist_fn()")

    def init_fn(self):
        msg_payload = {"survival": "calculate local survival rate: return time, count and survival rate"}
        results = self.flare_comm.broadcast(msg_payload)
        return results

    def aggregate_fn(self, result: dict):
        print("calculating the global count, survival rate for given times")
        return result

    def persist_fn(self, result: dict, path: str):
        print(f"save the result to {path}")
