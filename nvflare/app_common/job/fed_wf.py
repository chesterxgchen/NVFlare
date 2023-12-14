from nvflare.apis.fl_constant import SiteType
from nvflare.app_common.job.ml_framework import MLFramework
from nvflare.app_common.workflows.model_controller import ModelController


class FedWF:

    def __init__(self,
                 fl_algo: ModelController,
                 custom_dir: str = None,
                 id: str = "train_wf",
                 app_name:str = "app",
                 ml_framework: MLFramework = MLFramework.PYTORCH):
        self.site_type = None
        self.custom_dir = custom_dir
        self.site_name = None
        self.fl_algo = fl_algo
        self.id = id
        print(f"{app_name=}")
        self.app_name = app_name
        self.ml_framework = ml_framework if ml_framework else MLFramework.PYTORCH

    @property
    def get_algo(self):
        return self.fl_algo

    def set_site_name(self, site_name: str, site_type: SiteType = SiteType.SERVER):
        self.site_name = site_name
        self.site_type = site_type if site_type else SiteType.SERVER

