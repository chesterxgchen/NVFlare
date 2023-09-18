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
from typing import Any

from nvflare.fuel.f3.communicator import Communicator
from nvflare.fuel.f3.connection import Connection
from nvflare.fuel.f3.drivers.uds_driver import UdsDriver
from nvflare.fuel.f3.endpoint import Endpoint
from nvflare.fuel.f3.message import Message, MessageReceiver
from nvflare.fuel.utils.constants import Mode

log = logging.getLogger(__name__)


class UDSClient(MessageReceiver):

    def __init__(self,
                 app_id: int,
                 client_end_point: str,
                 conn_url: str
                 ):
        self.app_id = app_id
        self.client_end_point = Endpoint(name =client_end_point)
        self.connection = None
        self.conn_url = conn_url
        self.comm = None

    def open(self):
        comm = self.create_client()
        print("client side url = ", self.conn_url)
        comm.add_connector(self.conn_url, Mode.ACTIVE)
        self.comm = comm
        comm.start()

    def send(self, end_point: str, msg: Any, timeout=None):
        self.comm.send(Endpoint(end_point), self.app_id, Message({}, msg.encode("utf-8")))

    def close(self):
        if self.comm:
            self.comm.stop()

    def create_client(self):
        local_endpoint = self.client_end_point
        comm = Communicator(local_endpoint)
        comm.register_message_receiver(self.app_id, self)
        return comm

    def process_message(self, endpoint: Endpoint, connection: Connection, app_id: int, message: Message):
        if endpoint.name == "site-1":
            text = message.payload.decode("utf-8")
            print(text)


#             todo buffer message


def main():
    socket_path = "/tmp/nvflare/socket/mp_site-1"
    app_id = 123
    _, url = UdsDriver.get_urls("uds", dict(socket=socket_path))
    client = UDSClient(app_id, "client", conn_url=url)
    print("trying to open connection for client")
    client.open()
    try:
        count = 5
        for i in range(count):
            # right.send(Metrics(key="foo", value=0.1, data_type=AnalyticsDataType.SCALAR, ))
            client.send("server", "hello from Chester\n")
            # print("receive data from client")
    finally:
        client.close()


if __name__ == "__main__":
    main()
