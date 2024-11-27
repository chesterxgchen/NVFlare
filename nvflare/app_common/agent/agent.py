import threading
from abc import ABC, abstractmethod
from time import sleep

from nvflare.app_common.agent.generative_api import GenerativeAPI
from nvflare.app_common.agent.input_preprocess_api import InputPreprocessorAPI
from nvflare.app_common.agent.retrieval_api import RetrievalAPI


class Agent(ABC):
    def __init__(self,
                 preprocessor: InputPreprocessorAPI,
                 retriever: RetrievalAPI,
                 generator: GenerativeAPI,
                 check_period=0.01):
        self.check_period = check_period
        self.preprocessor = preprocessor
        self.retriever = retriever
        self.generator = generator
        self.stop_agent = threading.Event()
        self.agent_thread = threading.Thread(target=self.start_agent)

    def start(self):
        self.agent_thread.start()

    def start_agent(self):
        # Run forever
        while not self.stop_agent.is_set():
            self.run()
            sleep(self.check_period)

    @abstractmethod
    def run(self):
        pass

    def stop(self, reason: str = ""):
        if reason:
            print(f"{reason=}")

        self.stop_agent.set()

        if self.agent_thread:
            self.agent_thread.join()
