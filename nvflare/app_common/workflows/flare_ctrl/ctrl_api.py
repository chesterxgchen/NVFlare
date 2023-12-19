from typing import Dict, Union

from nvflare.app_common.workflows.flare_ctrl.ctrl_config import CtrlConfig


class Ctrl:

    def init(self, config: Union[str, Dict]) -> CtrlConfig:
        if isinstance(config, str):
            ctrl_config = None  # from_file(config_file=config)
        elif isinstance(config, dict):
            ctrl_config = CtrlConfig(config)
        else:
            raise ValueError("config should be either a string or dictionary.")
        return ctrl_config

    def broadcast(self):
        pass

    def send(self):
        pass
