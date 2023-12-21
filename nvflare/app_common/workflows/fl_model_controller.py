from typing import Union, Dict, Callable

from nvflare.apis.client import Client
from nvflare.apis.fl_context import FLContext
from nvflare.apis.impl.controller import Controller
from nvflare.apis.shareable import Shareable
from nvflare.apis.signal import Signal
from nvflare.app_common.workflows.error_handling_controller import ErrorHandlingController
from nvflare.app_common.workflows.flare_ctrl.ctrl_api import Ctrl
from nvflare.fuel.utils import class_utils


class FLModelController(Controller):

    def __init__(self,
                 ctrl_config: Union[str, Dict],
                 ctrl_task_class_path: str,
                 ctrl_task_args: Dict,
                 task_check_period: float = 0.2):
        super().__init__(task_check_period)
        self.ctrl_task_args = ctrl_task_args
        self.ctrl_task = None
        self.ctrl_api = None
        self.engine = None
        self.fl_ctx = None
        self.ctrl_config = ctrl_config
        self.ctrl_task_class_path = ctrl_task_class_path

    def start_controller(self, fl_ctx: FLContext):
        self.fl_ctx = fl_ctx
        self.log_info(fl_ctx, "Initializing controller workflow.")
        self.engine = self.fl_ctx.get_engine()
        self.ctrl_task = class_utils.instantiate_class(self.ctrl_task_class_path, self.ctrl_task_args)

    def control_flow(self, abort_signal: Signal, fl_ctx: FLContext):
        pass

    def stop_controller(self, fl_ctx: FLContext):
        pass

    def process_result_of_unknown_task(self, client: Client, task_name: str, client_task_id: str, result: Shareable,
                                       fl_ctx: FLContext):
        pass