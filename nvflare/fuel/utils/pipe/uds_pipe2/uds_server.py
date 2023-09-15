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
import socket
from typing import Any

from nvflare.fuel.utils import fobs


class UDSServer:

    def __init__(self,
                 socket_path: str,
                 num_clients: int = 1,
                 buffer_size: int = 1024):
        # Set the path for the Unix socket
        self.connection = None
        self.num_clients = num_clients
        self.buffer_size = buffer_size
        self.socket_path = socket_path

    def open(self):
        print('remove socket...')
        self.remove_socket_file(self.socket_path)
        print('create server')
        server = self.create_server(self.socket_path, self.num_clients)
        # accept connections
        print('Server is listening for incoming connections...')
        connection, client_address = server.accept()
        self.connection = connection
        return connection

    def clear(self):
        if self.socket_path:
            self.remove_socket_file(self.socket_path)

    def send(self, msg: Any, timeout=None) -> bool:
        if self.connection:
            msg_bytes = fobs.dumps(msg)
            self.connection.sendall(msg_bytes)

    def receive(self, timeout=None):
        if not self.connection:
            raise ValueError("connection must be established first")

        print("connection=", self.connection)
        print('Connection from', str(self.connection).split(", ")[0][-4:])

        # receive data from the client
        data_bytes = self.connection.recv(self.buffer_size)
        print("data_bytes=", data_bytes)
        data = fobs.loads(data_bytes)
        print("data=", data)
        return data

    def close(self):
        # close the connection
        if self.connection:
            self.connection.close()
            self.remove_socket_file(self.socket_path)

    def create_server(self, socket_path, num_clients):
        # Create the Unix socket server
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        # Bind the socket to the path
        server.bind(socket_path)
        # Listen for incoming connections
        server.listen(num_clients)
        return server

    def remove_socket_file(self, socket_path):
        try:
            os.unlink(socket_path)
        except OSError:
            if os.path.exists(socket_path):
                os.remove(socket_path)

