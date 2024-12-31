# Copyright (c) 2023, NVIDIA CORPORATION.  All rights reserved.
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
import os

import pandas as pd

from nvflare.app_opt.statistics.df.df_core_statistics import DFStatisticsCore


class DFStatistics(DFStatisticsCore):

    def __init__(self, data_root_dir: str, filename:str):
        super().__init__()
        self.data_root_dir = data_root_dir
        self.filename = filename
        self.data_features = [
            "Age",
            "Workclass",
            "fnlwgt",
            "Education",
            "Education-Num",
            "Marital Status",
            "Occupation",
            "Relationship",
            "Race",
            "Sex",
            "Capital Gain",
            "Capital Loss",
            "Hours per week",
            "Country",
            "Target",
        ]

        # the original dataset has no header,
        # we will use the adult.train dataset for site-1, the adult.test dataset for site-2
        # the adult.test dataset has incorrect formatted row at 1st line, we will skip it.
        self.skip_rows = {
            "site-1": [],
            "site-2": [0],
        }

    def initialize(self):
        pass

    def load_data(self):
        data_path = os.path.join(self.data_root_dir, self.site_name, self.filename)
        print(f"\n\nload data for data_path='{data_path}', site-name = {self.site_name}\n")
        try:
            # example of load data from CSV
            df: pd.DataFrame = pd.read_csv(
                data_path, names=self.data_features, sep=r"\s*,\s*", skiprows=self.skip_rows, engine="python", na_values="?"
            )
            train = df.sample(frac=0.8, random_state=200)  # random state is a seed value
            test = df.drop(train.index).sample(frac=1.0)

            print(f"load data done for data_path='{data_path}'")
            self.data = {"train": train, "test": test}

        except Exception as e:
            raise Exception(f"Load data data_path='{data_path}' failed! {e}")
