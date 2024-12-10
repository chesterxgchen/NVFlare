# Copyright (c) 2024, NVIDIA CORPORATION.  All rights reserved.
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
from time import sleep

from nvflare.apis.fl_context import FLContext
from nvflare.apis.impl.controller import Controller
from nvflare.apis.signal import Signal
from nvflare.app_common.agent.agent_consts import AGENT_CTRL_DATA, AGENT_STOP
from nvflare.app_common.workflows.agent.orchestrator import Orchestrator
from nvflare.fuel.data_event.data_bus import DataBus
from nvflare.fuel.data_event.event_manager import EventManager


class AgentController(Controller):

    def __init__(self, orchestrator_id: str, task_check_period=0.01):
        super().__init__(task_check_period)
        self.abort_signal = None
        self.orchestrator = None
        self.fl_ctx = None
        self.event_manager = EventManager(DataBus())
        self.orchestrator_id = orchestrator_id
        if not orchestrator_id:
            raise ValueError("valid orchestrator_id must be provided")

    def start_controller(self, fl_ctx: FLContext):
        self.fl_ctx = fl_ctx
        self.orchestrator: Orchestrator = fl_ctx.get_engine().get_component(self.orchestrator_id)
        if not isinstance(self.orchestrator, Orchestrator):
            raise ValueError("orchestrator agent must be type Orchestrator")
        self.event_manager.data_bus.put_data(key=AGENT_CTRL_DATA, datum=self)
        self.orchestrator.initialize(fl_ctx)

    def control_flow(self, abort_signal: Signal, fl_ctx: FLContext):

        while not abort_signal.triggered and not self.orchestrator.stop_event.is_set():
            sleep(self.orchestrator.check_period)

    def stop_controller(self, fl_ctx: FLContext):
        self.event_manager.data_bus.publish(topics=[AGENT_STOP], datum="stop controller")
