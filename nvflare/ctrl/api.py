from typing import List, Optional, Dict

from nvflare.apis.controller_spec import Task
from nvflare.apis.fl_context import FLContext
from nvflare.apis.impl.task_controller import TaskController
from nvflare.apis.shareable import Shareable
from nvflare.apis.signal import Signal
from nvflare.app_common.abstract.fl_model import FLModel


task_ctrl = TaskController()


def init(config=None):
    config = config if config else {}
    fl_ctx = FLContext()
    task_ctrl.start_controller(fl_ctx=fl_ctx)


def broadcast(model: FLModel,
              sites: List[str],
              min_sites:int,
              props: Optional[Dict] = None):
    task_name = "task"
    inputs = Shareable()
    inputs["input"] = model
    fl_ctx = FLContext()
    targets = sites
    abort_signal = Signal()
    task = Task(name=task_name, data=inputs, result_received_cb=results_cb, props=props)
    task_ctrl.broadcast_and_wait(task, fl_ctx, targets, min_sites, 0, abort_signal)


    return self.results


def send():
    pass


def receive():
    pass
