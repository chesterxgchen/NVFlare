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

from abc import ABC, abstractmethod
from typing import Dict

from nvflare.apis.fl_context import FLContext
from nvflare.apis.shareable import Shareable


class AgentAPI(ABC):

    @abstractmethod
    def process_and_generate(self, query:str, meta: Dict) -> Dict:
        """
            process input query and based on the metadata direction
            the agent will either direct process the query or route/broadcast to other agents to handle the query
        Args:
            query:
            meta:
        Returns:
        """
        pass

    @abstractmethod
    def receive_query(self, topic: str, query_data: Dict, fl_ctx: FLContext) -> Dict:
        """
        Args:
            topic:
            query_data:
            fl_ctx:
        Returns:
        """
        pass
