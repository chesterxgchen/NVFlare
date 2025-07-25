# Copyright (c) 2025, NVIDIA CORPORATION.  All rights reserved.
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

from abc import ABC, abstractmethod
from typing import Optional, Callable
from typing import Union, List

from pydantic import BaseModel, validator

from nvflare import FedJob
from nvflare.app_common.workflows.cyclic import Cyclic
from nvflare.job_config.exec_env import ExecEnv, SimEnv
from nvflare.job_config.script_runner import FrameworkType


class JobRecipe(ABC, BaseModel):
    name: str
    framework: FrameworkType = FrameworkType.PYTORCH

    @validator('name')
    def check_name(cls, v):
        if not v:
            raise ValueError('Name must not be empty')
        return v

    @abstractmethod
    def get_job(self, env: ExecEnv) -> FedJob:
        pass

    def execute(self,
                env: Optional[ExecEnv] = None,
                clients: Union[int, List[str]] = None,
                gpus: Union[int, List[int]] = None,
                workspace_dir: str = None,
                ):

        if env is None:
            env = SimEnv(clients=clients, gpus=gpus, workspace_dir=workspace_dir)

        if isinstance(env, SimEnv):
            job: FedJob = self.get_job(env)
            job.export_job("/tmp/nvflare/jobs/job_config")
            job.simulator_run(workspace=env.workspace_dir, gpu="0")

        pass


class FedAvgRecipe(JobRecipe):
    def __init__(self,
                 min_clients: Optional[int] = None,
                 num_rounds: Optional[int] = None,
                 client_script: Optional[str] = None,
                 model=None,
                 client_script_args: str = "",
                 aggregate_fn: Optional[Callable] = None,
                 name: str = "fed_avg",
                 framework=FrameworkType.PYTORCH
                 ):
        super().__init__(name=name, framework=framework)
        self.min_clients = min_clients
        self.num_rounds = num_rounds
        self.client_script = client_script
        self.client_script_args = client_script_args
        self.aggregate_fn = aggregate_fn
        self.recipe_name = name
        self.model = model

    def load_model(self):
        if self.model is None:
            # todo controller.load_model()
            # if self.__getattribute__("load_model") and isinstance(self.load_model, Callable):
            # find out if the controller has persistor, if yes, use it otherwise, try find the load_model() method
            # self.model = self.load_model()
            # todo:
            return None
        return self.model

    def get_job(self, env: ExecEnv) -> FedJob:
        # todo: get rid of this if else. 
        job = None
        job = FedAvgJob(
            name=self.recipe_name,
            n_clients=self.min_clients,
            num_rounds=self.num_rounds,
            initial_model=self.model,
        )

        # Add clients
        for client_name in env.client_names:
            executor = ScriptRunner(
                script=self.client_script,
                script_args=self.client_script_args
            )
            job.to(executor, client_name)

        return job


class CyclicRecipe(JobRecipe):
    def __init__(self,
                 min_clients: int,
                 num_rounds: int,
                 client_script: str,
                 model=None,
                 client_script_args="",
                 aggregate_fn: Optional[Callable] = None,
                 framework: Optional[FrameworkType] = FrameworkType.TENSORFLOW,
                 name="cyclic",
                 metrics=["accuracy"]
                 ):
        self.n_clients = min_clients
        self.num_rounds = num_rounds
        self.client_script = client_script
        self.model = model
        self.client_script_args = client_script_args
        self.aggregate_fn = aggregate_fn
        self.recipe_name = name
        self.framework = framework
        self.metrics = metrics  # todo use this

    def get_job(self, env: ExecEnv) -> FedJob:
        job = FedJob(name=self.recipe_name)
        # Define the controller workflow and send to server
        controller = Cyclic(
            num_clients=self.n_clients,
            num_rounds=self.num_rounds,
        )
        job.to(controller, "server")

        # Define the initial global model and send to server
        job.to(self.model, "server")

        # Add clients
        for client_name in env.client_names:
            executor = ScriptRunner(
                script=self.client_script,
                script_args=self.client_script_args,
                framework=self.framework,
            )
            job.to(executor, client_name)
        return job
