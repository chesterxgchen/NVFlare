# Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
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
import random
import time
from threading import Thread
from typing import Tuple, List

from nvflare.apis.analytix import AnalyticsDataType
from nvflare.app_common.metrics_exchange.metrics_exchanger import MetricsExchanger
from nvflare.app_common.metrics_exchange.metrics_retriever import MetricsRetriever
from nvflare.app_common.tracking.tracker_types import TrackConst

count = 0


def _send_data_to_event(data, data_type, key, value):
    global count
    count += 1
    print("add one count = ", count)


class TestMetricsExchange:

    def receive_metrics(self, client_name):
        receiver = MetricsRetriever()
        receiver._send_data_to_event = _send_data_to_event
        try:
            pipe_name = receiver.get_pipe_name(client_name)
            print(f"{pipe_name=}")
            # simulate ABOUT_TO_START_RUN event
            receiver.open_pipe(pipe_name)
            # receiver._receive_thread.start()
            receiver._receive_metrics()
            print("job finished size = ", len(receiver.messages))

        finally:
            # simulate ABOUT_TO_END_RUN event
            receiver.stop_receive()
            receiver.close_pipe()

    def send_metrics(self,
                     client_name):
        pipe_name = f"{TrackConst.PIPE_NAME_PREFIX}_{client_name}"
        sender = MetricsExchanger(pipe_name)
        sender.start()
        n = 10

        def generate_random_metrics() -> List[Tuple]:
            k = "accuracy"
            results = []
            for i in range(n):
                v = 0.0002 * i
                dt = AnalyticsDataType.METRIC
                st = i
                pth = None if i // 2 == 0 else "/tmp"
                delay = 0.001 * random.randint(1, 10)
                print(f"sleep for {delay} second")
                results.append((k, v, dt, st, pth, delay))

            return results

        try:
            for ds in generate_random_metrics():
                key, value, data_type, step, path, delay_sec = ds
                time.sleep(delay_sec)
                sender.log(key=key, value=value, data_type=data_type, global_step=step, path=path)
        finally:
            print("send count = ", sender.send_count)
            print(f"{sender.pipe.shared_dict=}")
            print(f"{sender.pipe.name=}")
            print(f"{sender.pipe.shared_dict.name=}")
            # try:
            #     sender.close()
            # except FileNotFoundError as ignore:
            #     pass

    def test_send_receive_metrics(self):
        client_names = ["site-1"]
        for client_name in client_names:
            self.send_metrics(client_name)

        for client_name in client_names:
            self.receive_metrics(client_name)

        assert count == 10

    # def test_send_receive_metrics_multi_processes(self):
    #
    #     client_names = ["site-1", "site-2"]
    #
    #     for client_name in client_names:
    #         sender_proc = mp.Process(target=self.send_metrics, args=(client_name,))
    #         sender_proc.start()
    #         sender_proc.join()
    #
    #     for client_name in client_names:
    #         receive_proc = mp.Process(target=self.receive_metrics, args=(client_name,))
    #         receive_proc.start()
    #         receive_proc.join()
