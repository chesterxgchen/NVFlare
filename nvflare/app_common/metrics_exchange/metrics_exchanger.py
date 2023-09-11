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

from typing import Any

from nvflare.apis.analytix import AnalyticsDataType
from nvflare.app_common.tracking.tracker_types import TrackConst
import time
from nvflare.fuel.utils.pipe.shared_mem_pipe import SharedMemPipe


class MetricData:
    def __init__(self, key, value, data_type: AnalyticsDataType, extra_args=None):
        self.data = {
            TrackConst.TRACK_KEY: key,
            TrackConst.TRACK_VALUE: value,
            TrackConst.DATA_TYPE_KEY: data_type
        }
        if extra_args:
            for k in extra_args:
                self.data[k] = extra_args[k]


class MetricsExchanger:
    def __init__(self, pipe_name: str):
        self.pipe_name = pipe_name
        self.pipe = None
        self.send_count = 0

    def start(self):
        self.pipe = SharedMemPipe()
        self.pipe.open(self.pipe_name)

    def log(self, key: str, value: Any, data_type: AnalyticsDataType, **kwargs):
        metric = MetricData(key=key, value=value, data_type=data_type, extra_args=kwargs)
        ms = time.time_ns()
        if self.pipe:
            self.send_count += 1
            self.pipe.send({ms: metric.data})
        else:
            raise RuntimeError("self.pipe is None")

    def close(self):
        self.pipe.clear()
        self.pipe.close()
