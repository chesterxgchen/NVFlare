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
from typing import Dict, List, Optional

from nvflare.apis.fl_context import FLContext
from nvflare.apis.shareable import Shareable
from nvflare.app_common.agent.agent import Agent
from nvflare.app_common.agent.agent_consts import AGENT_CTRL_DATA, AGENT_QUERY, AGENT_QUERY_METADATA, \
    AGENT_GENERAL_TOPIC_CHANNEL
from nvflare.fuel.data_event.data_bus import DataBus
from nvflare.fuel.data_event.event_manager import EventManager


class Orchestrator(Agent):

    def __init__(self, pipeline_id: Optional[str] = None, check_period=0.01):
        super().__init__(pipeline_id, check_period)
        self.cmd_timeout = None
        self.event_manager = EventManager(DataBus())
        self.fl_ctx : Optional[FLContext]= None
        self.agent_controller = None

    def initialize(self, fl_ctx: FLContext):
        self.fl_ctx = fl_ctx
        agent_controller = self.event_manager.data_bus.get_data(AGENT_CTRL_DATA)
        if not agent_controller:
            raise ValueError("agent controller is not available")
        self.agent_controller = agent_controller
        super().initialize(fl_ctx)

    def route_request(self, query: input, meta: dict) -> dict:
        engine = self.fl_ctx.get_engine()
        sites = engine.get_clients()
        reqs = self.prepare_site_data(meta, query, sites)

        replies = engine.multicast_aux_requests(
            topic=AGENT_GENERAL_TOPIC_CHANNEL,
            target_requests=reqs,
            timeout=self.cmd_timeout,
            fl_ctx=self.fl_ctx,
        )
        result = {}
        if replies:
            for k, s in replies.items():
                assert isinstance(s, Shareable)
                result[k] = s.get("data", {})
        return result

    def prepare_site_data(self, meta, query, sites):
        reqs = {}
        for c in sites:
            r = Shareable()
            r["data"] = {AGENT_QUERY: query, AGENT_QUERY_METADATA: meta}
            reqs[c.name] = r
        return reqs

    def process_and_generate(self, query:str, meta: Dict) -> Dict:
        """
            process input query and based on the meta data direction
            the agent will either direct process the query or route/broadcast to other agents to handle the query
            the input error or processing error should not stop the process. all error be can result and response
        Returns:
        """
        try:
            agent_contexts: Dict = self.route_request(query, meta)
            self.agent_pipeline.execute()
            # response = self.coordinate_pipeline(agent_contexts)

            return response

        except Exception as e:
            self.log_error(self.fl_ctx, str(e))
            return {}
