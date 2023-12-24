from abc import abstractmethod, ABC


class WF(ABC):
    @abstractmethod
    def run(self):
        raise NotImplemented
