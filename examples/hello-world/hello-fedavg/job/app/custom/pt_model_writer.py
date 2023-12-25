
from nvflare.app_common.abstract.fl_model import FLModel

from nvflare.fuel.utils.import_utils import optional_import


def pt_save_mode(self, model: FLModel, file_path: str):
    torch, import_flag = optional_import("torch")
    if import_flag:
        self.logger.info(f"save best model to {file_path} \n")
        m = model.params
        torch.save(m, file_path)
