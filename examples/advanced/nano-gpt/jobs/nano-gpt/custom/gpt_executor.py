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
import os
import subprocess
from typing import Any, Optional, List

import torch

from nvflare.apis.dxo import from_shareable, DXO, DataKind
from nvflare.apis.executor import Executor
from nvflare.apis.fl_constant import ReturnCode
from nvflare.apis.fl_context import FLContext
from nvflare.apis.shareable import Shareable, make_reply
from nvflare.apis.signal import Signal
from nvflare.app_common.abstract.model import ModelLearnableKey
from nvflare.app_common.app_constant import AppConstants


class PTProcessExecutor(Executor):

    def __init__(
            self,
            cmd: str = "python -m train.py ../config/train_shakespeare_char.conf ",
            out_dir="/tmp/nvflare/gpt/global/checkpoint",
            model_filename="model.pt"
    ):
        """Key component to run learner on clients.

        Args:
            train_task (str, optional): task name for train. Defaults to AppConstants.TASK_TRAIN.
            submit_model_task (str, optional): task name for submit model. Defaults to AppConstants.TASK_SUBMIT_MODEL.
            validate_task (str, optional): task name for validation. Defaults to AppConstants.TASK_VALIDATION.
        """
        super().__init__()
        self.out_dir = out_dir
        self.cmd = cmd
        self.model_filename = model_filename

    def get_command(self, current_round: int):
        return f"{self.cmd} -i {self.model_filename} -c current_round={current_round}"

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
        model_data = dxo.data
        self.save_model(self.out_dir, model_data)
        self.start_local_train(current_round)
        return self.get_model(fl_ctx, abort_signal)

    def save_model(self, out_dir, model_data):
        model_info = {
            "model": model_data[ModelLearnableKey.WEIGHTS].state_dict(),
            "current_round": model_data[AppConstants.CURRENT_ROUND]
        }
        torch.save(model_info, os.path.join(out_dir, self.model_filename))

    def get_model(self, fl_ctx: FLContext, abort_signal: Signal):
        # Checking abort signal
        if abort_signal.triggered:
            return make_reply(ReturnCode.TASK_ABORTED)

        model_data = self.read_model()
        return self.covert_model_to_shareable(fl_ctx, model_data)

    def covert_model_to_shareable(self, fl_ctx, model_data):
        # Create DXO and shareable from model data.
        model_shareable = Shareable()
        if model_data:
            outgoing_dxo = DXO(data_kind=DataKind.WEIGHTS, data=model_data["model"])
            outgoing_dxo.set_meta_prop("loss",  model_data["loss"])
            model_shareable = outgoing_dxo.to_shareable()
        else:
            # Set return code.
            self.log_error(fl_ctx, "local model not found.")
            model_shareable.set_return_code(ReturnCode.EXECUTION_RESULT_ERROR)
        return model_shareable

    def read_model(self):
        model_path = os.path.join(self.out_dir, self.model_filename)
        model_info = None
        if os.path.isfile(model_path):
            model_info = torch.load(model_path, map_location="cpu")
        return model_info

    def start_local_train(self, current_round):
        my_env = os.environ.copy()
        cmd = get_command(current_round)
        subprocess.Popen(cmd.split(" "), env=my_env)
