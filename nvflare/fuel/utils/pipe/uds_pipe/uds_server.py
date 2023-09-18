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
import os.path
from pathlib import Path
from typing import Any

from nvflare.fuel.f3.communicator import Communicator
from nvflare.fuel.f3.connection import Connection
from nvflare.fuel.f3.endpoint import Endpoint
from nvflare.fuel.f3.message import Message, MessageReceiver

log = logging.getLogger(__name__)


class UDSServer(MessageReceiver):

    def __init__(self,
                 app_id: int,
                 server_end_point: str,
                 socket_path: str,
                 socket_prefix: str = "/tmp/nvflare",
                 ):
        self.app_id = app_id
        self.server_end_point = Endpoint(name=server_end_point)
        self.connection = None
        self.socket_path = socket_path
        self.conn_scheme = "uds"
        self.conn_url = None
        self.comm = None
        self.socket_path = socket_path
        self.socket_prefix = socket_prefix

        parent_path = Path(socket_path).parent
        if not os.path.exists(str(parent_path)):
            os.makedirs(parent_path)

    def open(self):
        comm = self.create_server()
        resources = dict(socket=self.socket_path, socket_prefix=self.socket_prefix)
        handle, url = comm.start_listener("uds", resources)
        self.conn_url = url
        print("server side url = ", url)
        self.comm = comm
        comm.start()

    def send(self, end_point: str, msg: Any, timeout=None):
        self.comm.send(Endpoint(end_point), self.app_id, Message({}, msg.encode("utf-8")))

    def close(self):
        if self.comm:
            self.comm.stop()

    def create_server(self):
        local_endpoint = self.server_end_point
        comm = Communicator(local_endpoint)
        comm.register_message_receiver(self.app_id, self)
        return comm

    def process_message(self, endpoint: Endpoint, connection: Connection, app_id: int, message: Message):
        # if endpoint.name == "client":
        text = message.payload.decode("utf-8")
        print(text)


#       todo buffer message


def main():
    socket_path = "/tmp/nvflare/socket/mp_site-1"
    app_id = 123
    server = UDSServer(app_id, "server", socket_path)
    print("trying to open connection for server")
    try:
        server.open()
    except KeyboardInterrupt as e:
        server.close()
    finally:
        server.close()


if __name__ == "__main__":
    main()
