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

"""Parser registries for YAML-driven benchmark agent adapters."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..events import parse_usage_and_activity_data


def event_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def normalize_jsonl_event(raw_line: str) -> dict[str, Any] | None:
    stripped = raw_line.rstrip("\n")
    if not stripped:
        return None
    timestamp = event_timestamp()
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


EVENT_PARSERS = {
    "codex_jsonl": normalize_jsonl_event,
    "generic_jsonl": normalize_jsonl_event,
}

USAGE_PARSERS = {
    "codex_cumulative_usage": lambda path: parse_usage_and_activity_data(path)[0],
    "generic_cli_usage": lambda path: parse_usage_and_activity_data(path)[0],
}

ACTIVITY_PARSERS = {
    "codex_jsonl_activity": lambda path: parse_usage_and_activity_data(path)[1],
    "generic_jsonl_activity": lambda path: parse_usage_and_activity_data(path)[1],
}


def validate_event_parser(parser_id: str) -> None:
    if parser_id not in EVENT_PARSERS:
        raise ValueError(f"Unknown agent event parser: {parser_id}")


def validate_usage_parser(parser_id: str) -> None:
    if parser_id not in USAGE_PARSERS:
        raise ValueError(f"Unknown agent usage parser: {parser_id}")


def validate_activity_parser(parser_id: str) -> None:
    if parser_id not in ACTIVITY_PARSERS:
        raise ValueError(f"Unknown agent activity parser: {parser_id}")


def normalize_event_with_parser(raw_line: str, parser_id: str) -> dict[str, Any] | None:
    validate_event_parser(parser_id)
    parser = EVENT_PARSERS[parser_id]
    return parser(raw_line)


def parse_usage_from_events(events_path: Path, usage_config: Any) -> dict[str, Any]:
    parser_id = getattr(usage_config, "parser", None) or "generic_cli_usage"
    validate_usage_parser(parser_id)
    parser = USAGE_PARSERS[parser_id]
    usage = parser(events_path)
    usage.setdefault("parser_id", parser_id)
    return usage


def parse_activity_from_events(events_path: Path, activity_config: Any) -> dict[str, Any]:
    parser_id = getattr(activity_config, "parser", None) or "generic_jsonl_activity"
    validate_activity_parser(parser_id)
    parser = ACTIVITY_PARSERS[parser_id]
    activity = parser(events_path)
    activity.setdefault("parser_id", parser_id)
    return activity
