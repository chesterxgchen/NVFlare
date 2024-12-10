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


import threading
from abc import abstractmethod
from typing import Optional, Dict

from nvflare.apis.fl_context import FLContext
from nvflare.app_common.abstract.init_final_component import InitFinalComponent
from nvflare.app_common.agent.agent_api import AgentAPI
from nvflare.app_common.agent.agent_consts import AGENT_STOP, AGENT_QUERY, AGENT_QUERY_METADATA, AGENT_TOPIC_SESSION, \
    AGENT_GENERAL_TOPIC_CHANNEL
from nvflare.app_common.agent.agent_pipeline import AgentPipeline


class Agent(AgentAPI, InitFinalComponent):

    def __init__(self, pipeline_id: Optional[str] = None, check_period=0.01):
        super().__init__()
        self.fl_ctx: Optional[FLContext] = None
        self.agent_pipeline: Optional[AgentPipeline] = None
        self.agent_thread: Optional[threading.Thread] = None
        self.check_period: float = check_period
        self.pipeline_id: str = pipeline_id

       # Event for stopping the loop
        self.stop_event = threading.Event()

    def initialize(self, fl_ctx: FLContext):
        if self.pipeline_id and fl_ctx:
            self.agent_pipeline: AgentPipeline = fl_ctx.get_engine().get_component(self.pipeline_id)
            if not self.agent_pipeline:
                ValueError("initialization error, agent_pipeline is not provided")

        engine = fl_ctx.get_engine()
        engine.register_app_command(topic=AGENT_GENERAL_TOPIC_CHANNEL, cmd_func=self.receive_query)


    def finalize(self, fl_ctx: FLContext):
        pass

    def process_and_generate(self, query:str, meta: Dict) -> Dict:
        return self.agent_pipeline.execute(query, meta)

    def receive_query(self, topic: str, query_data: Dict, fl_ctx: FLContext) -> Dict:
        query = query_data.get(AGENT_QUERY, "")
        meta  = query_data.get(AGENT_QUERY_METADATA, {})
        if meta.get(AGENT_STOP, ""):
            self.stop_event.set()

        return self.process_and_generate(query, meta)


