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
import time
from threading import Thread

from nvflare.fuel.f3.drivers.uds_driver import UdsDriver
from nvflare.fuel.f3.endpoint import Endpoint
from nvflare.fuel.utils.pipe.uds_pipe.uds_client import UDSClient
from nvflare.fuel.utils.pipe.uds_pipe.uds_server import UDSServer


class TestUDS:

    def test_count(self):
        socket_path = "/tmp/nvflare/socket/mp_site-1_simulate_job"
        app_id = 123
        server_end_pt = Endpoint(name="server")
        server = UDSServer(app_id, server_end_pt, socket_path)

        resources = dict(socket=socket_path)
        _, url = UdsDriver.get_urls("uds", resources)
        client_end_pt = Endpoint(name="client")
        client = UDSClient(app_id, client_end_pt, conn_url=url)
        server_thread = None
        client_thread = None
        try:
            print("trying to open connection for server")
            server_thread = Thread(target=server.open)
            print("trying to open connection for client")
            client_thread = Thread(target=client.open)
            server_thread.start()
            time.sleep(0.5)
            client_thread.start()
            print("send data from client to server (right to left)")
            assert(server is not None)
            assert(client is not None)
            time.sleep(0.1)
            count = 5
            for i in range(count):
                # right.send(Metrics(key="foo", value=0.1, data_type=AnalyticsDataType.SCALAR, ))
                client.send(server_end_pt, "hello from Chester\n")
            # print("receive data from client")

        finally:
            client.close()
            server.close()
            if True:
                assert 1 == 0

            if client_thread:
                client_thread.join()
            if server_thread:
                server_thread.join()

