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
import logging
import time
from threading import Event, Thread

from nvflare.apis.event_type import EventType
from nvflare.apis.fl_component import FLComponent
from nvflare.apis.fl_context import FLContext
from nvflare.app_common.tracking.tracker_types import LogWriterName, TrackConst
from nvflare.app_common.widgets.streaming import ANALYTIC_EVENT_TYPE, AnalyticsSender
from nvflare.fuel.utils.class_utils import full_classname
from nvflare.fuel.utils.pipe.shared_mem_pipe import SharedMemPipe


class MetricsRetriever(FLComponent):
    def __init__(
            self,
            event_type=ANALYTIC_EVENT_TYPE,
            writer_name=LogWriterName.TORCH_TB,
            get_poll_interval: float = 0.005,
            buffer_size=100 * 1024
    ):
        """Metrics retriever.

        Args:
            event_type (str): event type to fire (defaults to "analytix_log_stats").
            writer_name: the log writer for syntax information (defaults to LogWriterName.TORCH_TB)
        """
        super().__init__()
        self.analytic_sender = AnalyticsSender(event_type=event_type, writer_name=writer_name)
        self.buffer_size = buffer_size

        self._get_poll_interval = get_poll_interval
        self.stop = Event()
        self._receive_thread = Thread(target=self.receive_data)
        self.fl_ctx = None
        self.pipe = None
        self.pipe_name = None
        self.pipe_name_prefix = TrackConst.PIPE_NAME_PREFIX
        self.logger = logging.getLogger(full_classname(self))
        self.metrics_count = 0
        self.messages = []

    def get_pipe_name(self, client_name):
        return f"{self.pipe_name_prefix}_{client_name}"

    def open_pipe(self, pipe_name: str):
        if pipe_name is None:
            raise ValueError("pipe name is None")

        # self.pipe = SharedMemPipe(size=self.buffer_size)
        self.pipe = SharedMemPipe()
        self.pipe.open(pipe_name)
        self.pipe_name = pipe_name

    def close_pipe(self):
        if self.pipe_name:
            # clear out anything remaining
            self._receive_metrics()
            pipe = self.pipe
            self.pipe = None
            pipe.close()

        self.pipe_name = None

    def handle_event(self, event_type: str, fl_ctx: FLContext):
        if event_type == EventType.ABOUT_TO_START_RUN:
            client_name = fl_ctx.get_identity_name()
            self.open_pipe(self.get_pipe_name(client_name))
            self.analytic_sender.handle_event(event_type, fl_ctx)
            self.fl_ctx = fl_ctx
            self._receive_thread.start()
        elif event_type == EventType.ABOUT_TO_END_RUN:
            self.stop.set()
            self._receive_thread.join()
            self.close_pipe()

    def stop_receive(self, close_pipe=False):
        self.stop.set()
        if self.pipe_name and self.pipe and close_pipe:
            self.close_pipe()

    def receive_data(self):
        """Receives data and sends with AnalyticsSender."""
        while True:
            if self.stop.is_set():
                break
            self._receive_metrics()
            print(f"sleep for {self._get_poll_interval} seconds")
            time.sleep(self._get_poll_interval)

    def _receive_metrics(self):
        if self.pipe is None:
            return

        pipe: SharedMemPipe = self.pipe
        msg = {}
        pipe.receive(msg)
        if not msg:
            return

        print(f"{len(msg)=}")
        self.metrics_count += len(msg)

        for tms, data in msg.items():
            self.messages.append(data)
            key = data.pop(TrackConst.TRACK_KEY, None)
            value = data.pop(TrackConst.TRACK_VALUE, None)
            data_type = data.pop(TrackConst.DATA_TYPE_KEY, None)

            if key is not None and value is not None and data_type is not None:
                print(f"{self.metrics_count=}")
                self._send_data_to_event(data, data_type, key, value)
            else:
                print(f"{TrackConst.TRACK_KEY}, {TrackConst.TRACK_VALUE} and {TrackConst.DATA_TYPE_KEY}"
                      f"all should have valid values, but got the followings {key=}, {value=}, "
                      f"{data_type=}")
                self.logger.warning(f"{TrackConst.TRACK_KEY}, {TrackConst.TRACK_VALUE} and {TrackConst.DATA_TYPE_KEY}"
                                    f"all should have valid values, but got the followings {key=}, {value=}, "
                                    f"{data_type=}")

    def _send_data_to_event(self, data, data_type, key, value):
        self.analytic_sender.add(tag=key,
                                 value=value,
                                 data_type=data_type,
                                 **data)
