# Copyright (c) 2024, NVIDIA CORPORATION.  All rights reserved.
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
from typing import Dict

from nvflare.job_config.stats_job import StatsJob
from df_statistics import DFStatistics

export_config = False

statistic_configs = {
    "count": {},
    "mean": {},
    "sum": {},
    "stddev": {},
    "histogram": {"*": {"bins": 20}},
    "Age": {"bins": 20, "range": [0, 10]},
}
# define local stats generator
df_stats_generator = DFStatistics(data_root_dir="/tmp/nvflare/df_stats/data", filename="data.csv")

job = StatsJob(
    job_name="stats_df",
    statistic_configs=statistic_configs,
    stats_generator=df_stats_generator,
    output_path="statistics/adults_stats.json",
)

n_clients = 2
sites = [f"site-{i + 1}" for i in range(n_clients)]
job.setup_clients(sites)

# job.export_job("/tmp/nvflare/jobs/df_stats")
job.simulator_run("/tmp/nvflare/stats/workdir")
