from typing import List

from nvflare.apis.fl_constant import SiteType
from nvflare.app_common.job.ml_framework import MLFramework


class FedApp:

    def __init__(self,
                 train_fn,
                 train_config: dict,
                 custom_dir: str = None,
                 app_name="app",
                 gpu_ids: List[int] = None,
                 ml_framework: MLFramework = MLFramework.PYTORCH):
        self.site_type = None
        self.site_name = None
        self.train_fn = train_fn
        self.train_config = train_config
        self.custom_dir = custom_dir
        self.app_name = app_name
        self.gpu_ids = gpu_ids
        self.ml_framework = ml_framework if ml_framework else MLFramework.PYTORCH

    def set_site_name(self, site_name: str, site_type: SiteType = SiteType.CLIENT):
        self.site_name = site_name
        self.site_type = site_type if site_type else SiteType.CLIENT
        self.app_name = f"{self.site_name}-{self.app_name}" if self.custom_dir and self.app_name == "app" else self.app_name
