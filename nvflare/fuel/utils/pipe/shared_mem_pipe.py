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
from typing import Dict

from UltraDict import UltraDict

from nvflare.fuel.utils.class_utils import full_classname


class SharedMemPipe:
    # note: in Mac the max length for shared memory is 31.
    MAX_LENGTH = 25

    def __init__(self, size=20 * 1024 * 1024):
        self.shared_dict = None
        self.buffer_size = size
        self.name = None
        self.logger = logging.getLogger(full_classname(self))

    def open(self, name: str):
        # self._check_pipe_name(name)

        if self.shared_dict is None:
            self.name = name
            if name:
                self.shared_dict = UltraDict( name=name, buffer_size=self.buffer_size)
            else:
                self.shared_dict = UltraDict(buffer_size=self.buffer_size)
                self.name = self.shared_dict.name

    def clear(self):
        if self.shared_dict:
            self.shared_dict.dump()

    def send(self, msg: Dict) -> bool:
        for k, v in msg.items():
            self.shared_dict[k] = v
        return True

    def receive(self, data: Dict):
        if data is None:
            data = {}

        for k, v in self.shared_dict.data.items():
            data[k] = v

        for k in data:
            self.shared_dict.pop(k)
            # del self.shared_dict[k]

        return data

    def close(self):
        try:
            if self.shared_dict:
                if self.logger.isEnabledFor(level=logging.DEBUG):
                    self.shared_dict.print_status()
                self.shared_dict.close()
                self.shared_dict.unlink()
        except UltraDict.Exceptions.AlreadyClosed as e:
            self.shared_dict = None

        self.name = None

    def _check_pipe_name(self, name):
        if not name:
            raise ValueError("invalid pipe name")

        if len(name) > SharedMemPipe.MAX_LENGTH:
            raise ValueError("name is too long")
