from nvflare.app_common.workflows.inference.fed_agent.generative_api import GenerativeAPI
from nvflare.app_common.workflows.inference.fed_agent.input_preprocess_api import InputPreprocessorAPI
from nvflare.app_common.workflows.inference.fed_agent.retrieval_api import RetrievalAPI


class RAGSystem:
    def __init__(self, preprocessor: InputPreprocessorAPI, retriever: RetrievalAPI, generator: GenerativeAPI):
        self.preprocessor = preprocessor
        self.retriever = retriever
        self.generator = generator

    def query(self, user_input: str) -> str:
        parsed_query = self.preprocessor.parse_query(user_input)
        documents = self.retriever.retrieve_documents(parsed_query["text"])
        response = self.generator.generate_response(parsed_query["text"], documents)
        return response
