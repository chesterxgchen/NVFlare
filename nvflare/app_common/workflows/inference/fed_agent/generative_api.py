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
from typing import List

from nvflare.app_common.workflows.inference.fed_agent.document import Document


class GenerativeAPI(ABC):

    @abstractmethod
    def generate_response(self, query:str, context: List[str]) -> str:
        pass

    @abstractmethod
    def summarize_documents(self, documents: List[Document]) -> str:
        pass

    @abstractmethod
    def extract_entities(self, documents: List[Document]) -> List[dict]:
        """
            extract specific entities ( eg. names , dates, concepts) from the documents
        Args:
            documents:
        Returns:
        """
        pass
