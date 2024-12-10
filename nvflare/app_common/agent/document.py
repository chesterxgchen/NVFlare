# Copyright (c) 2024, NVIDIA CORPORATION.  All rights reserved.
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
from typing import List, Optional

import numpy as np


class Document:

    def __init__(
        self,
        id: str,
        text: str,
        title: Optional[str] = None,
        source: Optional[str] = None,
        url: Optional[str] = None,
        author: Optional[str] = None,
        date: Optional[str] = None,
        score: Optional[float] = None,
        embedding: Optional[np.ndarray] = None,
        summary: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ):
        self.id = id
        self.text = text
        self.title = title
        self.source = source
        self.url = url
        self.author = author
        self.date = date
        self.score = score
        self.embedding = embedding
        self.summary = summary
        self.tags = tags

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "text": self.text,
            "title": self.title,
            "source": self.source,
            "url": self.url,
            "author": self.author,
            "date": self.date,
            "score": self.score,
            "embedding": self.embedding.tolist() if self.embedding is not None else None,
            "summary": self.summary,
            "tags": self.tags,
        }
