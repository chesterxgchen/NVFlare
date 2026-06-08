# Copyright (c) 2026, NVIDIA CORPORATION.  All rights reserved.
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

"""Codex-specific event normalization and metadata helpers."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


def codex_event_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def normalize_codex_event(raw_line: str) -> dict[str, Any] | None:
    stripped = raw_line.rstrip("\n")
    if not stripped:
        return None
    timestamp = codex_event_timestamp()
    try:
        event = json.loads(stripped)
    except json.JSONDecodeError:
        event = {"type": "harness.unparsed_event", "raw": stripped}
    if isinstance(event, dict):
        event.setdefault("timestamp", timestamp)
        event["harness_timestamp"] = timestamp
        return event
    return {
        "type": "harness.non_object_event",
        "timestamp": timestamp,
        "harness_timestamp": timestamp,
        "value": event,
    }
