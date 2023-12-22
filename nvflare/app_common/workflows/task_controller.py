import time
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from typing import Union, Dict, Tuple, List

from nvflare.apis.client import Client
from nvflare.apis.controller_spec import SendOrder, Task, ClientTask
from nvflare.apis.dxo import from_shareable
from nvflare.apis.event_type import EventType
from nvflare.apis.fl_constant import ReturnCode
from nvflare.apis.fl_context import FLContext
from nvflare.apis.shareable import Shareable
from nvflare.apis.signal import Signal
from nvflare.app_common.workflows.error_handling_controller import ErrorHandlingController
from nvflare.app_common.workflows.flare_ctrl.wf_spec import WF
from nvflare.fuel.utils import class_utils


class TaskController(ErrorHandlingController):

    def __init__(self,
                 task_name: str,
                 wf_class_path: str,
                 wf_args: Dict,
                 task_check_period: float = 0.2):
        super().__init__(task_check_period)
        self.task_name = task_name
        self.ctrl_msg_check_interval = 0.5
        self._thread_pool_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=self.__class__.__name__)
        self.wf_class_path = wf_class_path
        self.wf_args = wf_args
        self.ctrl_msg_queue = Queue()
        self.result_queue = Queue()

        self.wf: WF = class_utils.instantiate_class(self.wf_class_path, self.wf_args)

        self.engine = None
        self.fl_ctx = None

        if not hasattr(self.wf, "flare_comm"):
            raise ValueError(f"required attribute 'flare_ctrl' is not set on class {self.wf_class_path}")

    def start_controller(self, fl_ctx: FLContext):
        self.fl_ctx = fl_ctx
        self.log_info(fl_ctx, "Initializing controller workflow.")
        self.engine = self.fl_ctx.get_engine()

        # dynamic add queues to the flare_ctrl object instance
        self.wf.flare_comm.set_queues(task_queue=self.ctrl_msg_queue, result_queue=self.result_queue)

    def control_flow(self, abort_signal: Signal, fl_ctx: FLContext):
        try:
            future1 = self._thread_pool_executor.submit(self.ctrl_msg_loop, fl_ctx=fl_ctx, abort_signal=abort_signal)
            self.wait_for_wf_result(abort_signal, fl_ctx)
            future1.result()
        except Exception as e:
            self.log_error(fl_ctx, f"{e}")
            self.system_panic(f"{e}", fl_ctx=fl_ctx)

    def wait_for_wf_result(self, abort_signal, fl_ctx):
        try:
            self.log_info(fl_ctx, "wait_for_wf_result")
            future2 = self._thread_pool_executor.submit(self.wf.run())
            future2.result()
        except Exception as wf_e:
            self.stop_msg_queue(f"failed due to {wf_e}", abort_signal, fl_ctx)
            self.log_error(fl_ctx, f"{wf_e}")
            self.system_panic(f"{wf_e}", fl_ctx=fl_ctx)

    def stop_msg_queue(self, stop_message, abort_signal, fl_ctx):
        self.ctrl_msg_queue.put({"command": "STOP", "payload": {}})
        abort_signal.trigger(f"{stop_message}")
        # wait for the the message loop to stop
        time.sleep(self.ctrl_msg_check_interval + 0.1)

    def stop_controller(self, fl_ctx: FLContext):

        if self._thread_pool_executor:
            self._thread_pool_executor.shutdown()

    def process_result_of_unknown_task(self, client: Client, task_name: str, client_task_id: str, result: Shareable,
                                       fl_ctx: FLContext):
        pass

    def ctrl_msg_loop(self, fl_ctx: FLContext, abort_signal: Signal):

        if self.ctrl_msg_queue is None:
            return

        while True:
            if abort_signal.triggered:
                break
            item = self.ctrl_msg_queue.get()
            if item:
                cmd = item.get("command", None)
                if cmd is None:
                    msg = "Invalid message format, expecting 'command'"
                    self.log_error(fl_ctx, msg)
                    abort_signal.trigger(msg)
                    break
                elif cmd == "STOP":
                    self.log_info(fl_ctx, "receive STOP command")
                    break
                elif cmd == "BROADCAST":
                    print("------------------ item = ", item)
                    pay_load = item.get("payload")
                    print("\n ********************pay_load=", pay_load)
                    task, targets, min_responses = self.get_payload_task(pay_load)
                    self.broadcast_and_wait(task, fl_ctx, targets, min_responses, 0, abort_signal)
                elif cmd == "SEND":
                    pay_load = item.get("payload")
                    task, targets, _ = self.get_payload_task(pay_load)
                    self.send_and_wait(task, fl_ctx, targets, SendOrder.SEQUENTIAL, 0, abort_signal)
                else:
                    abort_signal.trigger(f"Unknown command '{cmd}'")
                    raise ValueError(f"Unknown command '{cmd}'")
            else:
                time.sleep(self.ctrl_msg_check_interval)

    def get_payload_task(self, pay_load) -> Tuple[Task, Union[List[str], None], int]:
        data = Shareable()
        print("=================== payload =", pay_load)
        task = Task(name=self.task_name, data=data,result_received_cb= self.result_received_cb)
        return task, ["site-1", "site-2"], 0

    def result_received_cb(self, client_task: ClientTask, fl_ctx: FLContext):
        client_name = client_task.client.name
        task_name = client_task.task.name
        result = client_task.result
        rc = result.get_return_code()
        results = {"status": rc}
        if rc == ReturnCode.OK:
            self.log_info(fl_ctx, f"Received result entries from client:{client_name}, " f"for task {task_name}")
            dxo = from_shareable(result)
            client_result = dxo.data
            results["result"] = {client_name: client_result}
        elif rc in self.abort_job_in_error.keys():
            self.handle_client_errors(rc, client_task, fl_ctx)
            results["result"] = {client_name: {}}

        self.result_queue.put({task_name: results})
        # Cleanup task result
        client_task.result = None

    def handle_event(self, event_type: str, fl_ctx: FLContext):
        super().handle_event(event_type, fl_ctx)
        if event_type == EventType.END_RUN:
            self.ctrl_msg_queue.put({"command": "STOP", "payload": {}})
            results = {"status": ReturnCode.TASK_ABORTED, "result": {}}
            self.result_queue.put(results)

