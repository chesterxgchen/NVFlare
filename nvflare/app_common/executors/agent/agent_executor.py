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
from typing import Optional

from nvflare.apis.event_type import EventType
from nvflare.apis.executor import Executor
from nvflare.apis.fl_constant import ReturnCode
from nvflare.apis.fl_context import FLContext
from nvflare.apis.shareable import Shareable, make_reply
from nvflare.apis.signal import Signal
from nvflare.app_common.agent.agent import Agent
from nvflare.app_common.agent.agent_consts import AGENT_STOP, AGENT_QUERY, AGENT_QUERY_METADATA
from nvflare.fuel.data_event.data_bus import DataBus
from nvflare.fuel.data_event.event_manager import EventManager


class AgentExecutor(Executor):
    def __init__(self, agent_id: str):
        super().__init__()
        self.init_status_ok = True
        self.init_failure = {"abort_job": None, "fail_client": None}
        self.agent_comp_id = agent_id
        self.agent_site_name = None
        self.agent: Optional[Agent] = None
        self.event_manager = EventManager(DataBus())
        self.agent_started = False

    def handle_event(self, event_type: str, fl_ctx: FLContext):
        if event_type == EventType.START_RUN:
            self.initialize(fl_ctx)
        elif event_type == EventType.END_RUN:
            self.finalize(fl_ctx)

    def initialize(self, fl_ctx: FLContext):
        try:
            self.agent_site_name = fl_ctx.get_identity_name()
            self.agent = fl_ctx.get_engine().get_component(self.agent_comp_id)
            engine = fl_ctx.get_engine()
            # todo: add dynamic topic registration -- user can create a session
            engine.register_aux_message_handler(topic="topic-session", message_handle_func=self.agent.receive_query)

        except TypeError as te:
            self.log_exception(fl_ctx, f"{self.__class__.__name__} initialize failed.")
            self.init_status_ok = False
            self.init_failure = {"abort_job": te}
        except Exception as e:
            self.log_exception(fl_ctx, f"{self.__class__.__name__} initialize failed.")
            self.init_status_ok = False
            self.init_failure = {"fail_client": e}

    def execute(self, task_name: str, shareable: Shareable, fl_ctx: FLContext, abort_signal: Signal) -> Shareable:
        init_rc = self._check_init_status(fl_ctx)
        if init_rc:
            return make_reply(init_rc)

        if abort_signal.triggered:
            self.event_manager.data_bus.publish(topics=[AGENT_STOP], datum="abort triggered")
            return make_reply(ReturnCode.TASK_ABORTED)

        if not self.agent_started:
            self.agent.start()

        self.event_manager.data_bus.put_data("data", shareable)
    def finalize(self, fl_ctx: FLContext):
        self.event_manager.data_bus.publish(topics=[AGENT_STOP], datum="job end")
        pass

    def _check_init_status(self, fl_ctx: FLContext):
        if not self.init_status_ok:
            for fail_key in self.init_failure:
                reason = self.init_failure[fail_key]
                if fail_key == "abort_job":
                    return ReturnCode.EXECUTION_EXCEPTION
                self.system_panic(reason, fl_ctx)
                return ReturnCode.EXECUTION_RESULT_ERROR
        return None
