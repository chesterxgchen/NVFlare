import logging
import time
from queue import Queue
from typing import Dict, Optional

from nvflare.apis.fl_constant import ReturnCode
from nvflare.app_common.workflows.flare_ctrl.wf_queue import WFQueue
from nvflare.app_common.workflows.flare_ctrl.wf_spec import WF

SITE_NAMES = "site_names"
CMD_SEND = "SEND"
CMD_STOP = "STOP"
CMD_BROADCAST = "BROADCAST"


class WFComm:
    def __init__(self, result_check_interval: int = 2):
        self.result_check_interval = result_check_interval
        self.wf_queue: WFQueue = None
        self.meta = {SITE_NAMES: []}
        self.logger = logging.getLogger(self.__class__.__name__)

    def init(self, wf: WF):
        if wf:
            wf.flare_comm = self

    def set_queue(self, wf_queue: WFQueue):
        self.wf_queue = wf_queue

    def broadcast_and_wait(self, msg_payload: Dict):
        self.logger.info(f"broadcast_and_wait with payload= {msg_payload} ")
        self.broadcast(msg_payload)
        min_responses = msg_payload.get("min_responses", 0)
        return self.wait(min_responses)

    def broadcast(self, msg_payload):
        self._check_wf_queue()
        message = {
            "command": CMD_BROADCAST,
            "payload": msg_payload,
        }
        self.logger.info(f"broadcast message {message} ")
        self.wf_queue.put_ctrl_msg(message)

    def send(self, msg_payload: Dict):
        self._check_wf_queue()
        message = {
            "command": CMD_SEND,
            "payload": msg_payload,
        }
        self.wf_queue.put_ctrl_msg(message)

    def send_and_wait(self, msg_payload: Dict):
        self.send(msg_payload)
        min_responses = msg_payload.get("min_responses", 0)
        return self.wait(min_responses)

    def get_site_names(self):
        return self.meta.get(SITE_NAMES)

    def wait(self, min_responses):
        all_results = None
        while True:
            if self.wf_queue.has_result():
                self.logger.info(f" getting result")
                all_results = self._get_items_from_result_queue(min_responses, all_results)
                self.logger.info(f" all_results= {all_results}")
                if all_results is not None:
                    return all_results
            else:
                self.logger.info(f"no result available, sleep {self.result_check_interval} sec")
                time.sleep(self.result_check_interval)

    def _get_items_from_result_queue(self, min_responses: int, all_results: Optional[Dict] = None):
        item_size = self.wf_queue.result_size()
        self.logger.info(f"item_size= {item_size} \n")
        for i in range(item_size):
            self.logger.info(f"i= {i} \n")
            task_result = self.wf_queue.get_result()
            self.logger.info(f"task_result= {task_result} \n")

            all_results = all_results if all_results else {}
            for task, result_env in task_result.items():
                task_result = all_results.get(task, {})

                rc = result_env.get("status")
                if rc == ReturnCode.OK:
                    result = result_env.get("result", {})
                    task_result.update(result)
                    all_results[task] = task_result
                else:
                    raise RuntimeError(f"task {task} failed with '{rc}' status")

        self.logger.info(f"combine task_result\n \n")
        cond_result = all(len(task_result) >= min_responses for task, task_result in all_results.items())
        if cond_result:
            return all_results
        else:
            return None

    def _check_wf_queue(self):
        if self.wf_queue is None:
            raise RuntimeError("missing WFQueue")
