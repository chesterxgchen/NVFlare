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
import multiprocessing as mp
import time

from nvflare.fuel.utils.pipe.shared_mem_pipe import SharedMemPipe


class TestSharedMemPipe:

    def test_count(self):
        name = "foo"
        left = SharedMemPipe()
        right = SharedMemPipe()
        try:
            left.open(name=name)
            right.open(name=name)
            count = 100
            for i in range(count):
                right.send({i: i})
            assert len(left.shared_dict) == count
            data = {}
            left.receive(data)
            assert len(data) == count
            assert len(left.shared_dict) == 0
            assert len(right.shared_dict) == 0
        finally:
            left.close()
            pass

    def send(self, name, count):
        right = SharedMemPipe()
        right.open(name=name)
        for i in range(count):
            right.send({i: i})

    def recieve(self, name, count):
        left = SharedMemPipe()
        try:
            left.open(name=name)
            assert len(left.shared_dict) == count
            data = {}
            left.receive(data)
            assert len(data) == count
            assert len(left.shared_dict) == 0
        finally:
            left.close()

    def multi_recieve(self, num_sites, count):
        left = SharedMemPipe()
        try:
            for i in num_sites:
                name = f"site-{i}"
                left.open(name=name)
                assert len(left.shared_dict) == count
                data = {}
                left.receive(data)
                assert len(data) == count
                assert len(left.shared_dict) == 0
        finally:
            left.close()

    def test_inter_processes_send_receive(self):
        count = 100
        receive_proc = mp.Process(target=self.recieve, args=("foo", count))
        receive_proc.start()
        receive_proc.join()

        send_proc = mp.Process(target=self.send, args=("foo", count))
        send_proc.start()
        send_proc.join()

    def test_multi_senders_with_one_receiver(self):
        num_sites = 10
        count = 100
        receive_proc = mp.Process(target=self.multi_recieve, args=(num_sites, count))
        receive_proc.start()
        receive_proc.join()

        for i in range(num_sites):
            name = f"site-{i}"
            send_proc = mp.Process(target=self.send, args=(name, count))
            send_proc.start()
            send_proc.join()

    def test_nested_dicts(self):
        name = "foo"
        left = SharedMemPipe()
        right = SharedMemPipe()
        try:
            left.open(name=name)
            right.open(name=name)
            count = 100
            send_data = {}
            for i in range(count):
                ms = time.time_ns()
                send_data.update({ms: {"step": i, "value": 0.123, "key": "accuracy"}})
            right.send(send_data)

            assert len(left.shared_dict) == count
            data = {}
            left.receive(data)
            assert len(data) == count
            assert len(left.shared_dict) == 0
            assert len(right.shared_dict) == 0
            assert data == send_data

            # send again, but one item a time
            for k, v in send_data.items():
                right.send({k: v})

            assert len(left.shared_dict) == count
            data = {}
            left.receive(data)
            assert len(data) == count
            assert len(left.shared_dict) == 0
            assert len(right.shared_dict) == 0
            assert data == send_data

        finally:
            left.close()
