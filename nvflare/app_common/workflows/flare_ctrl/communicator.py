from queue import Queue
from typing import Dict, Optional

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

        message = {
            "command": "BROADCAST",
            "payload": msg_payload,
        }
        self.task_queue.put(message)

        # wait for result
        print("================waiting for result")
        # return self.result_queue.get()
        return {}

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
