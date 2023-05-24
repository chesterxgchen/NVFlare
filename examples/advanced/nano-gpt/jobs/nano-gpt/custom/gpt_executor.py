# Copyright (c) 2021, NVIDIA CORPORATION.  All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from typing import Any

import torch

from nvflare.apis.dxo import from_shareable, DXO
from nvflare.apis.executor import Executor
from nvflare.apis.fl_constant import ReturnCode
from nvflare.apis.fl_context import FLContext
from nvflare.apis.shareable import Shareable, make_reply
from nvflare.apis.signal import Signal
from nvflare.app_common.app_constant import AppConstants
from nvflare.security.logging import secure_format_exception


class PTProcessExecutor(Executor):

    def __init__(
            self,
            out_dir="/tmp/nvflare/gpt/global/checkpoint",
            train_task=AppConstants.TASK_TRAIN,
            submit_model_task=AppConstants.TASK_SUBMIT_MODEL,
            validate_task=AppConstants.TASK_VALIDATION,
    ):
        """Key component to run learner on clients.

        Args:
            train_task (str, optional): task name for train. Defaults to AppConstants.TASK_TRAIN.
            submit_model_task (str, optional): task name for submit model. Defaults to AppConstants.TASK_SUBMIT_MODEL.
            validate_task (str, optional): task name for validation. Defaults to AppConstants.TASK_VALIDATION.
        """
        super().__init__()
        self.train_task = train_task
        self.submit_model_task = submit_model_task
        self.out_dir = out_dir
        # todo make fifopipe

    def execute(self, task_name: str, shareable: Shareable, fl_ctx: FLContext, abort_signal: Signal) -> Shareable:
        """Typical training task pipeline
          Get global model weights (potentially with HE)
          Local training
          Return updated weights (model_diff)
          """
        if abort_signal.triggered:
            return make_reply(ReturnCode.TASK_ABORTED)

        # get round information
        current_round = shareable.get_header(AppConstants.CURRENT_ROUND)
        total_rounds = shareable.get_header(AppConstants.NUM_ROUNDS)
        self.log_info(fl_ctx, f"Current/Total Round: {current_round + 1}/{total_rounds}")
        self.log_info(fl_ctx, f"Client identity: {fl_ctx.get_identity_name()}")

        # update local model weights with received weights
        dxo = from_shareable(shareable)
        global_weights = dxo.data
        self.save_checkpoint(self.out_dir, global_weights)
        #     todo create a process to run train.py -f config/xyf.conf
        return self.get_model_sharable(fl_ctx, abort_signal)

    def save_checkpoint(self, out_dir, global_weights):
        checkpoint = {
            "model": global_weights["model"].state_dict(),
            "optimizer": global_weights["optimizer"].state_dict(),
            "model_args": global_weights["model_args"],
            "iter_num": global_weights["iter_num"],
            "best_val_loss": global_weights["best_val_loss"],
            "config": global_weights["config"],
        }
        print(f"saving checkpoint to {out_dir}")
        torch.save(checkpoint, os.path.join(out_dir, "ckpt.pt"))

    def get_model_sharable(self, fl_ctx: FLContext, abort_signal: Signal):

        # Checking abort signal
        if abort_signal.triggered:
            return make_reply(ReturnCode.TASK_ABORTED)

        np_data = self.load_checkpoint()
        return self.covert_model_to_shareable(fl_ctx, np_data)

    def covert_model_to_shareable(self, fl_ctx, np_data):
        # Create DXO and shareable from model data.
        model_shareable = Shareable()
        if np_data:
            outgoing_dxo = DXO(data_kind=DataKind.WEIGHTS, data=np_data)
            model_shareable = outgoing_dxo.to_shareable()
        else:
            # Set return code.
            self.log_error(fl_ctx, "local model not found.")
            model_shareable.set_return_code(ReturnCode.EXECUTION_RESULT_ERROR)
        return model_shareable


    def load_checkpoint(self):
        checkpoint: Any = None
        return checkpoint
