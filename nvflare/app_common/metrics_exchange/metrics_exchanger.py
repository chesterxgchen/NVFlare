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
from datetime import datetime
from typing import Any, Optional

from nvflare.app_common.abstract.fl_model import MetaKey

from nvflare.apis.analytix import AnalyticsDataType
from nvflare.app_common.tracking.tracker_types import TrackConst, LogWriterName
from nvflare.fuel.utils.pipe.shared_mem_pipe import SharedMemPipe


class MetricData:
    def __init__(self, key, value, data_type: AnalyticsDataType, extra_args=None):
        self.data = {TrackConst.TRACK_KEY: key, TrackConst.TRACK_VALUE: value, TrackConst.DATA_TYPE_KEY: data_type}
        if extra_args:
            for k in extra_args:
                self.data[k] = extra_args[k]


class Metrics:
    def __init__(
            self,
            key: str,
            value,
            data_type: AnalyticsDataType,
            sender: LogWriterName = LogWriterName.TORCH_TB,
            **kwargs,
    ):

        self._validate_data_types(data_type, key, value, **kwargs)
        self.tag = key
        self.value = value
        self.data_type = data_type
        self.kwargs = kwargs
        self.sender = sender
        self.step = kwargs.get(TrackConst.GLOBAL_STEP_KEY, None)
        self.path = kwargs.get(TrackConst.PATH_KEY, None)

    def _validate_data_types(
            self,
            data_type: AnalyticsDataType,
            key: str,
            value: any,
            **kwargs,
    ):
        if not isinstance(key, str):
            raise TypeError("expect tag to be an instance of str, but got {}.".format(type(key)))
        if not isinstance(data_type, AnalyticsDataType):
            raise TypeError(
                "expect data_type to be an instance of AnalyticsDataType, but got {}.".format(type(data_type))
            )
        if kwargs and not isinstance(kwargs, dict):
            raise TypeError("expect kwargs to be an instance of dict, but got {}.".format(type(kwargs)))
        step = kwargs.get(TrackConst.GLOBAL_STEP_KEY, None)
        if step:
            if not isinstance(step, int):
                raise TypeError("expect step to be an instance of int, but got {}.".format(type(step)))
            if step < 0:
                raise ValueError("expect step to be non-negative int, but got {}.".format(step))
        path = kwargs.get(TrackConst.PATH_KEY, None)

        if path and not isinstance(path, str):
            raise TypeError("expect path to be an instance of str, but got {}.".format(type(step)))

        if data_type in [AnalyticsDataType.SCALAR, AnalyticsDataType.METRIC] and not isinstance(value, float):
            raise TypeError(f"expect '{key}' value to be an instance of float, but got '{type(value)}'.")
        elif data_type in [
            AnalyticsDataType.METRICS,
            AnalyticsDataType.PARAMETERS,
            AnalyticsDataType.SCALARS,
        ] and not isinstance(value, dict):
            raise TypeError(f"expect '{key}' value to be an instance of dict, but got '{type(value)}'.")
        elif data_type == AnalyticsDataType.TEXT and not isinstance(value, str):
            raise TypeError(f"expect '{key}' value to be an instance of str, but got '{type(value)}'.")
        elif data_type == AnalyticsDataType.TAGS and not isinstance(value, dict):
            raise TypeError(
                f"expect '{key}' data type expects value to be an instance of dict, but got '{type(value)}'"
            )


class MetricsExchanger:
    def __init__(self, pipe_name: Optional[str] = None):
        self.pipe_name = pipe_name
        self.pipe = None
        self.send_count = 0

        if self.pipe_name is None or not self.pipe_name.strip(""):
            self.pipe_name = self._get_pipe_name()

    def open_pipe(self):
        self.pipe = SharedMemPipe()
        print("\n **************** exchanger pipe_name=", self.pipe_name)
        self.pipe.open(self.pipe_name)

    def log(self, key: str, value: Any, data_type: AnalyticsDataType, **kwargs):
        metric = MetricData(key=key, value=value, data_type=data_type, extra_args=kwargs)
        dt = str(datetime.now())
        if self.pipe:
            self.send_count += 1
            self.pipe.send({dt: metric.data})
        else:
            raise RuntimeError("self.pipe is None")

        if self.send_count % 1000 == 0:
            print(f"************************ send count = {self.send_count}, {self.pipe_name=}, {self.pipe.name=}")

    def close_pipe(self):
        self.pipe.clear()
        self.pipe.close()

    def _get_pipe_name(self):
        # prefix = TrackConst.PIPE_NAME_PREFIX
        # site_name = os.environ[MetaKey.SITE_NAME]
        # job_id = os.environ[MetaKey.JOB_ID]
        # name = f"{prefix}_{site_name}"
        # job_name_length = SharedMemPipe.MAX_LENGTH - len(name)
        # return f"{name}_{job_id[:job_name_length-1]}" if job_id else name
        return os.environ[MetaKey.METRICS_PIPE_NAME]


