import time
from queue import Queue
from typing import Dict, Optional

from nvflare.apis.fl_constant import ReturnCode
from nvflare.app_common.workflows.flare_ctrl.wf_spec import WF


class Communicator:
    def __init__(self):
        self.task_queue = None
        self.result_queue = None
        self.ctrl_config = None

    def init(self, wf: WF, config: Optional[Dict] = None):
        if wf:
            wf.flare_comm = self

        if config:
            if isinstance(config, dict):
                self.ctrl_config = config
            else:
                raise ValueError(f"config should be a dictionary, but get a '{type(config)}'")

    def set_queues(self, task_queue: Queue, result_queue: Queue):
        self.task_queue = task_queue
        self.result_queue = result_queue

    def broadcast(self, msg_payload: Dict):

        if self.task_queue is None:
            raise RuntimeError("missing message queue")
        min_responses = msg_payload.get("min_responses", 0)
        message = {
            "command": "BROADCAST",
            "payload": msg_payload,
        }
        self.task_queue.put(message)

        all_results = None
        while True:
            if not self.result_queue.empty():
                item_size = self.result_queue.qsize()
                print(f"{item_size=}")
                for i in range(item_size):
                    task_result = self.result_queue.get()
                    result = None
                    for task, result_env in task_result.items():
                        rc = result_env.get("status")
                        if rc == ReturnCode.OK:
                            result = result_env.get("result", {})
                            if all_results:
                                all_results.update(result)
                            else:
                                all_results = result
                        else:
                            raise RuntimeError(f"task {task} failed with '{rc}' status")
                print(f"{min_responses=}")
                print(f"{len(all_results)=}")
                print(f"{all_results=}")
                if all_results and len(all_results) >= min_responses:
                    return all_results
            else:
                print("result queue is empty, sleep 2 sec")
                time.sleep(2)

    def send(self, msg_payload: Dict):
        if self.task_queue is None:
            raise RuntimeError("missing task_queue")

        message = {
            "command": "SEND",
            "payload": msg_payload,
        }
        self.task_queue.put(message)

        # wait for result
        return self.result_queue.get()
