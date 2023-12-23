from abc import abstractmethod, ABC

from nvflare.app_common.workflows.flare_ctrl.wf_comm import WFComm


class WF(ABC):
    def __init__(self):
        self.flare_comm = WFComm()

    @abstractmethod
    def run(self):
        raise NotImplemented
