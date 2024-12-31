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
import csv
from typing import Dict, List, Optional

import pandas as pd

from nvflare.app_opt.statistics.df.df_core_statistics import DFStatisticsCore


class DFStatistics(DFStatisticsCore):
    def __init__(self, data_root_dir: str):
        super().__init__()
        self.data_root_dir = data_root_dir
        self.data: Optional[Dict[str, pd.DataFrame]] = None
        self.data_features = None

    def initialize(self):
        self.data_features = self.load_features()

    def load_features(self) -> List:
        client_name = self.get_site_name()
        try:
            data_path = f"{self.data_root_dir}/{client_name}_header.csv"

            features = []
            with open(data_path, "r") as file:
                # Create a CSV reader object
                csv_reader = csv.reader(file)
                line_list = next(csv_reader)
                features = line_list
            return features
        except Exception as e:
            raise Exception(f"Load header for client {client_name} failed! {e}")

    def load_data(self) -> Dict[str, pd.DataFrame]:
        client_name = self.get_site_name()
        try:
            data_path = f"{self.data_root_dir}/{client_name}.csv"
            # example of load data from CSV
            df: pd.DataFrame = pd.read_csv(
                data_path, names=self.data_features, sep=r"\s*,\s*", engine="python", na_values="?"
            )
            self.data = {"train": df}
        except Exception as e:
            raise Exception(f"Load data for client {client_name} failed! {e}")
