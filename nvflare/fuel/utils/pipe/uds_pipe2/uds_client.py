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
import socket
import os
from typing import Any
from nvflare.fuel.utils import fobs


class UDSClient:
    def __init__(self,
                 socket_path: str,
                 buffer_size = 1024):
        self.client = None
        self.socket_path = socket_path
        self.buffer_size = buffer_size

    def open(self):
        # Create the Unix socket client
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.client = client
        # Connect to the server
        print("socket_path=", self.socket_path)
        try:
            client.connect(self.socket_path)
        except FileNotFoundError as e:
            raise RuntimeError(f"{self.socket_path} is not found" + str(e))

    def clear(self):
        pass

    def send(self, msg: Any, timeout=None):
        # Send a message to the server
        print("msg =", msg)
        msg_bytes = fobs.dumps(msg)
        print("msg_bytes =", msg_bytes)
        if self.client:
            self.client.sendall(msg_bytes)

    def receive(self, timeout=None):
        # # Receive a response from the server
        response = self.client.recv_bytes(self.buffer_size)
        msg = fobs.loads(response)
        print(f'Received response: {msg}')
        return msg

    def close(self):
        # Close the connection
        if self.client:
            self.client.close()
