import inspect
import os
import shutil
from typing import Union, List

from pyhocon import ConfigFactory, ConfigTree, HOCONConverter

from nvflare import SimulatorRunner
from nvflare.apis.fl_constant import SiteType
from nvflare.app_common.job.fed_app import FedApp
from nvflare.app_common.job.fed_wf import FedWF
from nvflare.app_common.job.ml_framework import MLFramework
from nvflare.fuel.utils import class_utils
from nvflare.fuel.utils.import_utils import optional_import
from nvflare.utils.cli_utils import save_config


def get_class_path_and_name(clazz_obj):
    algo_fqcn = class_utils.get_fqcn(clazz_obj)
    last_dot_index = algo_fqcn.rindex(".")
    class_path = algo_fqcn[:last_dot_index]
    class_name = algo_fqcn[last_dot_index + 1:]

    last_dot_index = class_path.rindex(".")
    class_file_name = class_path[last_dot_index + 1:]
    return algo_fqcn, class_file_name, class_name, class_path


def remove_pycache_files(target_dir):
    for root, dirs, files in os.walk(target_dir):
        # remove pycache and pyc files
        for d in dirs:
            if d == "__pycache__" or d.endswith(".pyc"):
                shutil.rmtree(os.path.join(root, d))


def copy_tree_content(src, dst):
    # Iterate over the contents of the source directory
    for root, dirs, files in os.walk(src):
        for file in files:
            src_path = os.path.join(root, file)
            relative_path = os.path.relpath(src_path, src)
            dst_path = os.path.join(dst, relative_path)

            # Ensure the destination directory exists
            os.makedirs(os.path.dirname(dst_path), exist_ok=True)

            # Copy the file to the destination directory
            shutil.copy2(src_path, dst_path)


class FLJob:
    def __init__(self,
                 name: str
                 ):
        self.site_apps = []
        self.server_workflows = []
        self.site_workflows = []
        self.name = name

    def to(self,
           deploy_obj: Union[FedWF, FedApp, List[FedWF], List[FedApp]],
           site_name: str,
           site_type=None):

        deploy_objs = deploy_obj if isinstance(deploy_obj, List) else [deploy_obj]
        for obj in deploy_objs:
            obj.set_site_name(site_name, site_type)
            if isinstance(obj, FedWF):
                if obj.site_type == SiteType.SERVER:
                    self.server_workflows.append(obj)
                else:
                    self.site_workflows.append(obj)
            elif isinstance(obj, FedApp):
                self.site_apps.append(obj)
            else:
                raise ValueError(f"unsupported object type:'{type(obj)}'")

    def simulate(self,
                 job_dir: str,
                 workspace: str = None,
                 n_threads: int = None,
                 gpu_ids: List[int] = None,
                 max_clients: int = 100):

        self.export_config(job_dir)

        simulator = SimulatorRunner(
            job_folder=job_dir,
            workspace=workspace,
            clients=",".join([app.site_name for app in self.site_apps]),
            n_clients=len(self.site_apps),
            threads=n_threads if n_threads else len(self.site_apps),
            # gpu=gpu_ids,
            max_clients=max_clients,
        )
        return simulator.run()

    def submit(self):
        pass

    def export_config(self, job_dir: str):
        if not self.server_workflows:
            raise ValueError("server workflow must be defined")
        if not self.site_apps:
            raise ValueError("FLApp must be defined")

        self._prepare_job_dir(job_dir)

        self._gen_job_meta_config(job_dir=job_dir)
        self._gen_server_job_config(job_dir=job_dir, workflows=self.server_workflows)
        self._gen_client_job_config(job_dir=job_dir, executors=self.site_apps)
        # todo: add later
        # self._add_client_workflows_config(job_dir=job_dir, workflows=self.site_workflows)

    def _gen_server_job_config(self, job_dir: str, workflows: List[FedWF]):
        parent_dir = os.path.dirname(__file__)
        config = ConfigFactory.parse_file(os.path.join(parent_dir, "default_server_config.conf"))
        for wf in workflows:
            self._gen_server_workflow_config(config, job_dir, wf)

    def _gen_client_job_config(self, job_dir: str, executors: List[FedApp]):
        parent_dir = os.path.dirname(__file__)
        config = ConfigFactory.parse_file(os.path.join(parent_dir, "default_client_config.conf"))
        apps_with_custom_dir = [app for app in executors if app.custom_dir is not None]
        require_custom_dir = len(apps_with_custom_dir) >= 1
        for app in executors:
            self._gen_client_exec_config(config, job_dir, app, require_custom_dir)
        pass

    def _gen_server_workflow_config(self, config: ConfigTree, job_dir: str, wf: FedWF):
        wf_config: ConfigTree = ConfigFactory.parse_string("{}")
        wf_config.put("id", wf.id)
        algo_fqcn, class_file_name, class_name, class_path = get_class_path_and_name(wf.get_algo)

        app_dir = os.path.join(os.path.abspath(os.path.join(job_dir)), wf.app_name)
        custom_algo_file_path = os.path.join(app_dir, "custom", f"{class_file_name}.py")

        if wf.custom_dir and os.path.isfile(custom_algo_file_path):
            wf_config.put("path", f"{class_file_name}.{class_name}")
        else:
            wf_config.put("path", algo_fqcn)

        args_config = self._get_wf_args_config(class_path, class_name, wf)
        wf_config.put("args", args_config)

        workflows_config = config.get("workflows", [])
        workflows_config.append(wf_config)

        config.put("workflows", workflows_config)
        config_json_str = HOCONConverter.to_json(config)
        print(config_json_str)

        dst_path = os.path.join(app_dir, "config", "config_fed_server.conf")
        save_config(dst_config=config, dst_path=dst_path)

    def _get_wf_args_config(self, class_path, class_name, wf: FedWF) -> ConfigTree:
        module, import_flag = optional_import(module=class_path, name=class_name)
        result = {}
        if import_flag:
            params = inspect.signature(module.__init__).parameters
            for v in params.values():
                if v.name != "self":
                    value = getattr(wf.get_algo, v.name, v.default)
                    if value and not callable(value):
                        result[v.name] = value

        return ConfigFactory.from_dict(result)

    def _prepare_job_dir(self, job_dir):
        job_folder = os.path.abspath(job_dir)
        if os.path.isdir(job_folder):
            shutil.rmtree(job_folder)

        os.makedirs(job_folder, exist_ok=True)
        for wf in self.server_workflows:
            self.prepare_app_dirs(job_folder, wf)

        for wf in self.site_workflows:
            self.prepare_app_dirs(job_folder, wf)

        for app_exec in self.site_apps:
            self.prepare_app_dirs(job_folder, app_exec)

    def prepare_app_dirs(self, job_folder, app):
        app_path = os.path.join(job_folder, app.app_name)
        config_path = os.path.join(app_path, "config")
        if app.custom_dir:
            custom_path = os.path.abspath(os.path.join(app_path, "custom"))
            if not os.path.exists(custom_path):
                shutil.copytree(app.custom_dir, custom_path)
            else:
                copy_tree_content(app.custom_dir, custom_path)

            remove_pycache_files(custom_path)

        os.makedirs(config_path, exist_ok=True)

    def _add_client_workflows_config(self, job_dir, workflows):
        pass

    def _gen_client_exec_config(self, config: ConfigTree, job_dir: str, app: FedApp, require_custom_dir: bool):
        if app.app_name == "app":
            app.app_name = f"{app.site_name}_{app.app_name}"

        if app.ml_framework == MLFramework.PYTORCH:
            parent_dir = os.path.dirname(__file__)
            config = ConfigFactory.parse_file(os.path.join(parent_dir, "pt_client_config.conf"))

        train_fn = app.train_fn

        # Get file name where the function is defined
        file_name = os.path.basename(train_fn.__code__.co_filename)
        print(f"file Name: {file_name}")

        app_dir = os.path.join(os.path.abspath(os.path.join(job_dir)), app.app_name)
        ml_file_path = os.path.join(app_dir, "custom", file_name)
        if os.path.isfile(ml_file_path):
            config.put("app_script", file_name)
            if app.train_config:
                app_conf_str = " ".join([f"--{k} {v}" for k, v in app.train_config.items()])
                config.put("app_config", app_conf_str)

        config_json_str = HOCONConverter.to_json(config)
        print(config_json_str)

        dst_path = os.path.join(app_dir, "config", "config_fed_client.conf")
        save_config(dst_config=config, dst_path=dst_path)

    def _gen_job_meta_config(self, job_dir, min_clients: int = 2):
        meta_config: ConfigTree = ConfigFactory.parse_string("{}")
        meta_config.put("name", self.name)
        deploy_map_config: ConfigTree = ConfigFactory.parse_string("{}")
        for wf in self.server_workflows:
            self.add_to_deploy_map(deploy_map_config, wf)
        for wf in self.site_workflows:
            self.add_to_deploy_map(deploy_map_config, wf)
        for wf in self.site_apps:
            self.add_to_deploy_map(deploy_map_config, wf)

        meta_config.put("deploy_map", deploy_map_config)
        meta_config.put("min_clients", min_clients)

        dst_path = os.path.join(job_dir, "meta.conf")
        save_config(dst_config=meta_config, dst_path=dst_path)

    def add_to_deploy_map(self, deploy_map_config, wf):
        sites = deploy_map_config.get_list(wf.app_name, [])
        sites.append(wf.site_name)
        deploy_map_config.put(wf.app_name, sites)
