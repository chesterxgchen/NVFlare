import threading
import time
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from typing import Dict, Tuple

from nvflare.app_common.abstract.fl_model import FLModel

from nvflare.app_common.utils.fl_model_utils import FLModelUtils

from nvflare.apis.client import Client
from nvflare.apis.controller_spec import SendOrder, Task, ClientTask, TaskOperatorKey, OperatorMethod
from nvflare.apis.dxo import from_shareable, DXO, DataKind
from nvflare.apis.event_type import EventType
from nvflare.apis.fl_constant import ReturnCode
from nvflare.apis.fl_context import FLContext
from nvflare.apis.shareable import Shareable
from nvflare.apis.signal import Signal
from nvflare.app_common.app_constant import AppConstants
from nvflare.app_common.app_event_type import AppEventType
from nvflare.app_common.workflows.error_handling_controller import ErrorHandlingController
from nvflare.app_common.workflows.flare_ctrl.wf_spec import WF
from nvflare.fuel.utils import class_utils


class WFController(ErrorHandlingController):

    def __init__(self,
                 task_name: str,
                 wf_class_path: str,
                 wf_args: Dict,
                 start_round: int = 1,
                 num_rounds: int = 1,
                 task_timeout: int = 0,
                 task_check_period: float = 0.2):
        super().__init__(task_check_period)
        self.clients = None
        self._current_round = None
        self._task_timeout = task_timeout
        self._start_round = start_round
        self._current_round = None
        self._num_rounds = num_rounds
        self.task_name = task_name
        self.ctrl_msg_check_interval = 0.5
        self.wf_class_path = wf_class_path
        self.wf_args = wf_args
        self.ctrl_msg_queue = Queue()
        self.result_queue = Queue()

        self._result_queue_lock = threading.Lock()
        self._thread_pool_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=self.__class__.__name__)
        self._ctrl_msg_loop_future = None

        self.wf: WF = class_utils.instantiate_class(self.wf_class_path, self.wf_args)

        self.engine = None
        self.fl_ctx = None

        if not hasattr(self.wf, "flare_comm"):
            raise ValueError(f"required attribute 'flare_ctrl' is not set on class {self.wf_class_path}")

    def start_controller(self, fl_ctx: FLContext):
        self.fl_ctx = fl_ctx
        self.log_info(fl_ctx, "Initializing controller workflow.")
        self.engine = self.fl_ctx.get_engine()
        self.clients = self.engine.get_clients()

        if self._current_round is None:
            self._current_round = self._start_round

        # dynamic add queues to the flare_ctrl object instance
        self.wf.flare_comm.set_queues(task_queue=self.ctrl_msg_queue, result_queue=self.result_queue)

    def control_flow(self, abort_signal: Signal, fl_ctx: FLContext):
        fl_ctx.set_prop(AppConstants.CURRENT_ROUND, self._current_round, private=True, sticky=True)
        self.fire_event(AppEventType.ROUND_STARTED, fl_ctx)

        try:
            future = self._thread_pool_executor.submit(self.ctrl_msg_loop, fl_ctx=fl_ctx, abort_signal=abort_signal)
            self._ctrl_msg_loop_future = future

            self.wf.run()
        except Exception as e:
            self.log_error(fl_ctx, f"{e}")
            self.system_panic(f"{e}", fl_ctx=fl_ctx)

    def stop_msg_queue(self, stop_message, abort_signal, fl_ctx):
        self.ctrl_msg_queue.put({"command": "STOP", "payload": {}})
        abort_signal.trigger(f"{stop_message}")
        # wait for the message loop to stop
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
                    pay_load = item.get("payload")
                    print("\n ********************pay_load=", pay_load)
                    task, min_responses = self.get_payload_task(pay_load)

                    self.broadcast_and_wait(
                        task=task,
                        min_responses=min_responses,
                        wait_time_after_min_received=0,
                        fl_ctx=fl_ctx,
                        abort_signal=abort_signal,
                    )

                    if abort_signal.triggered:
                        self.log_debug(self.fl_ctx, f"task {self.task_name} aborted")
                        return

                    self.fire_event(AppEventType.ROUND_DONE, fl_ctx)
                    self.log_info(fl_ctx, f"Round {self._current_round} finished.")
                    if self._current_round == self._num_rounds:
                        self.log_info(fl_ctx, f"Finished task '{self.task_name}'.")
                        self.ctrl_msg_queue.put({"command": "STOP", "payload": {}})
                    else:
                        self._current_round += 1
                elif cmd == "SEND":
                    pay_load = item.get("payload")
                    task, min_responses = self.get_payload_task(pay_load)
                    # self.send_and_wait(task, fl_ctx, abort_signal)
                else:
                    abort_signal.trigger(f"Unknown command '{cmd}'")
                    raise ValueError(f"Unknown command '{cmd}'")
            else:
                time.sleep(self.ctrl_msg_check_interval)

    def get_payload_task(self, pay_load) -> Tuple[Task, int]:
        print("=================== payload =", pay_load)
        min_responses = pay_load.get("min_responses")
        current_round = pay_load.get("current_round", None)
        data = pay_load.get("data", None)
        if current_round:
            self._current_round = current_round

        data_shareable = self.get_shareable(data)
        data_shareable.set_header(AppConstants.CURRENT_ROUND, self._current_round)
        data_shareable.set_header(AppConstants.NUM_ROUNDS, self._num_rounds)
        data_shareable.add_cookie(AppConstants.CONTRIBUTION_ROUND, self._current_round)

        operator = {
            TaskOperatorKey.OP_ID: self.task_name,
            TaskOperatorKey.METHOD: OperatorMethod.BROADCAST,
            TaskOperatorKey.TIMEOUT: self._task_timeout,
        }

        task = Task(
            name=self.task_name,
            data=data_shareable,
            operator=operator,
            props={},
            timeout=self._task_timeout,
            before_task_sent_cb=None,
            result_received_cb=self._result_received_cb)

        return task, min_responses

    def get_shareable(self, data):
        if isinstance(data, FLModel):
            data_shareable: Shareable = FLModelUtils.to_shareable(data)
        elif data is None:
            data_shareable = Shareable()
        else:
            dxo = DXO(DataKind.RAW, data=data, meta={})
            data_shareable = dxo.to_shareable()
        return data_shareable

    def _result_received_cb(self, client_task: ClientTask, fl_ctx: FLContext):
        print("\n=================== print_result received =====\n")

        client_name = client_task.client.name
        task_name = client_task.task.name
        result = client_task.result
        rc = result.get_return_code()
        results = {"status": rc}
        print(f"========{client_name=}========{task_name=} ===={result=} \n")
        if rc == ReturnCode.OK:
            self.log_info(fl_ctx, f"Received result entries from client:{client_name}, " f"for task {task_name}")
            dxo = from_shareable(result)
            client_result = dxo.data
            results["result"] = {client_name: client_result}
        elif rc in self.abort_job_in_error.keys():
            self.handle_client_errors(rc, client_task, fl_ctx)
            results["result"] = {client_name: {}}
        self.write_to_result_queue({task_name: results})

        # Cleanup task result
        client_task.result = None

    def handle_event(self, event_type: str, fl_ctx: FLContext):
        super().handle_event(event_type, fl_ctx)
        if event_type == EventType.END_RUN:
            self.ctrl_msg_queue.put({"command": "STOP", "payload": {}})
            results = {"status": ReturnCode.TASK_ABORTED, "result": {}}
            self.result_queue.put(results)
            self.write_to_result_queue(results)

    def write_to_result_queue(self, results):
        try:
            self._result_queue_lock.acquire()
            self.log_debug(self.fl_ctx, "acquired a _result_queue_lock")
            self.result_queue.put(results)
        finally:
            self.log_debug(self.fl_ctx, "released a _result_queue_lock")
            self._result_queue_lock.release()
