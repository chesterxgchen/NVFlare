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

import numpy as np

from nvflare.app_common.workflows.inference.fed_agent.document import Document


class RetrievalAPI(ABC):

    @abstractmethod
    def retrieve_documents(self, query: str, top_k: int) -> List[Document]:
        pass

    @abstractmethod
    def rank_documents(self, query: str, documents: List[Document]) -> List[Document]:
        """Ranks the retrieved documents by relevance."""
        pass

    @abstractmethod
    def search_database(
        self, query: str, top_k: int = 5, search_type: str = "hybrid", filters: dict = None
    ) -> List[Document]:
        pass

    @abstractmethod
    def get_embeddings(self, text: str, model_name: str = "default") -> np.array:
        # Generate embeddings using a pre-trained model
        pass
