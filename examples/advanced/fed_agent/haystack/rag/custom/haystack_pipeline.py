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
import os
from getpass import getpass

from datasets import load_dataset
from haystack import Document, Pipeline
from haystack.components.builders import PromptBuilder
from haystack.components.embedders import SentenceTransformersDocumentEmbedder
from haystack.components.generators import OpenAIGenerator
from haystack.document_stores.in_memory import InMemoryDocumentStore
from haystack.components.retrievers.in_memory import InMemoryEmbeddingRetriever


from nvflare.app_common.agent.agent_pipeline import AgentPipeline


class HaystackPipeline(AgentPipeline):
    def __init__(self):
        self.retriever = None
        self.rag_pipline = None
        self.generator = None
        self.document_store = None
        self.doc_embedder = None
        self.docs = None
        self.dataset = None

    def execute(self, query: str, meta: dict):
        self.document_store = InMemoryDocumentStore()
        self.retriever = InMemoryEmbeddingRetriever(self.document_store)
        self.load_data()
        self.init_embedder()
        self.index_and_save_data()

        self.rag_pipline = self.define_pipeline()
        response = self.rag_pipline.run({"text_embedder": {"text": query}, "prompt_builder": {"question": query}})
        print(response["llm"]["replies"][0])

    def define_pipeline(self):
        basic_rag_pipeline = Pipeline()
        # Add components to your pipeline
        basic_rag_pipeline.add_component("text_embedder", self.doc_embedder)
        basic_rag_pipeline.add_component("retriever", self.retriever)
        basic_rag_pipeline.add_component("prompt_builder", self.get_prompt_builder())
        basic_rag_pipeline.add_component("llm", self.generator)

        # Now, connect the components to each other
        basic_rag_pipeline.connect("text_embedder.embedding", "retriever.query_embedding")
        basic_rag_pipeline.connect("retriever", "prompt_builder.documents")
        basic_rag_pipeline.connect("prompt_builder", "llm")
        return basic_rag_pipeline

    def init_embedder(self):
        self.doc_embedder = SentenceTransformersDocumentEmbedder(model="sentence-transformers/all-MiniLM-L6-v2")
        self.doc_embedder.warm_up()

    def load_data(self):
        self.dataset = load_dataset("bilgeyucel/seven-wonders", split="train")
        self.docs = [Document(content=doc["content"], meta=doc["meta"]) for doc in dataset]

    def index_and_save_data(self):
        docs_with_embeddings = self.doc_embedder.run(self.docs)
        self.document_store.write_documents(docs_with_embeddings["documents"])

    def get_template(self):
        template = """
        Given the following information, answer the question.

        Context:
        {% for document in documents %}
            {{ document.content }}
        {% endfor %}
        
        Question: {{question}}
        Answer:
        """
        return template

    def get_prompt_builder(self):
        prompt_builder = PromptBuilder(template=self.get_template())
        return prompt_builder

    def init_generator(self):

        if "OPENAI_API_KEY" not in os.environ:
            os.environ["OPENAI_API_KEY"] = getpass("Enter OpenAI API key:")
        self.generator = OpenAIGenerator(model="gpt-4o-mini")
