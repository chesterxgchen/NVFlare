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
from typing import List

from nvflare.app_common.workflows.inference.fed_agent.agent import Agent
from nvflare.app_common.workflows.inference.fed_agent.generative_api import GenerativeAPI
from nvflare.app_common.workflows.inference.fed_agent.input_preprocess_api import InputPreprocessorAPI
from nvflare.app_common.workflows.inference.fed_agent.retrieval_api import RetrievalAPI


class RAGAgent(Agent):

    def __init__(self, preprocessor: InputPreprocessorAPI, retriever: RetrievalAPI, generator: GenerativeAPI):
        super().__init__(preprocessor, retriever, generator)


    def query(self, user_input: str) -> str:
        parsed_query = self.preprocessor.parse_query(user_input)
        documents = self.retriever.retrieve_documents(parsed_query["text"], top_k=5)
        context = self.context_from_documents(documents)
        response = self.generator.generate_response(parsed_query["text"], context)
        return response

    def context_from_documents(self, documents) -> List[str]:
        pass