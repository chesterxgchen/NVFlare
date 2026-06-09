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

import json
import os

import pytest

from nvflare.tool.agent import skill_performance
from nvflare.tool.agent.skill_manager import SkillSource


def test_load_records_enforces_file_cap(monkeypatch, tmp_path):
    monkeypatch.setattr(skill_performance, "MAX_RECORD_FILES", 1)
    for index in range(2):
        (tmp_path / f"record-{index}.json").write_text(
            json.dumps({"schema_version": "1", "skill": "nvflare-test-skill"}),
            encoding="utf-8",
        )

    with pytest.raises(skill_performance.SkillPerformanceError) as exc:
        skill_performance._load_records(tmp_path)

    assert exc.value.code == "PROCESS_RECORD_FILE_LIMIT_EXCEEDED"


def test_load_records_missing_path_uses_structured_error(tmp_path):
    missing = tmp_path / "missing"

    with pytest.raises(skill_performance.SkillPerformanceError) as exc:
        skill_performance._load_records(missing)

    assert exc.value.code == "PROCESS_RECORDS_PATH_NOT_FOUND"


def test_read_record_file_invalid_jsonl_uses_structured_error(tmp_path):
    record_path = tmp_path / "record.jsonl"
    record_path.write_text("{not json}\n", encoding="utf-8")

    with pytest.raises(skill_performance.SkillPerformanceError) as exc:
        skill_performance._read_record_file(record_path)

    assert exc.value.code == "INVALID_PROCESS_RECORD_JSONL"


def test_read_record_file_invalid_json_uses_structured_error(tmp_path):
    record_path = tmp_path / "record.json"
    record_path.write_text("{not json}\n", encoding="utf-8")

    with pytest.raises(skill_performance.SkillPerformanceError) as exc:
        skill_performance._read_record_file(record_path)

    assert exc.value.code == "INVALID_PROCESS_RECORD_JSON"


def test_read_record_file_unreadable_json_uses_structured_error(tmp_path):
    record_path = tmp_path / "record.json"
    record_path.write_bytes(b'{"schema_version": "1", "skill": "\xff"}')

    with pytest.raises(skill_performance.SkillPerformanceError) as exc:
        skill_performance._read_record_file(record_path)

    assert exc.value.code == "PROCESS_RECORD_FILE_UNREADABLE"


def test_read_record_file_read_os_error_uses_structured_error(monkeypatch, tmp_path):
    record_path = tmp_path / "record.json"
    record_path.write_text('{"schema_version": "1", "skill": "nvflare-test-skill"}\n', encoding="utf-8")
    original_read_text = type(record_path).read_text

    def fail_read_text(self, *args, **kwargs):
        if self == record_path:
            raise OSError("record disappeared")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(type(record_path), "read_text", fail_read_text)

    with pytest.raises(skill_performance.SkillPerformanceError) as exc:
        skill_performance._read_record_file(record_path)

    assert exc.value.code == "PROCESS_RECORD_FILE_UNREADABLE"


def test_read_record_file_jsonl_replaces_invalid_utf8_bytes(tmp_path):
    record_path = tmp_path / "record.jsonl"
    record_path.write_bytes(b'{"schema_version": "1", "skill": "nvflare-test-skill", "case_id": "bad-\xff"}\n')

    records = skill_performance._read_record_file(record_path)

    assert records[0]["case_id"] == "bad-\ufffd"


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlinks are not supported on this platform")
def test_load_records_does_not_traverse_symlinked_directories(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    outside.joinpath("record.json").write_text(
        json.dumps({"schema_version": "1", "skill": "nvflare-test-skill", "case_id": "outside"}),
        encoding="utf-8",
    )
    records_root = tmp_path / "records"
    records_root.mkdir()
    records_root.joinpath("external").symlink_to(outside, target_is_directory=True)

    records, _status = skill_performance._load_records(records_root)

    assert records == []


def test_read_record_file_rejects_oversized_file_before_json_load(monkeypatch, tmp_path):
    record_path = tmp_path / "record.json"
    record_path.write_text('{"schema_version": "1", "skill": "nvflare-test-skill"}\n', encoding="utf-8")
    monkeypatch.setattr(skill_performance, "MAX_RECORD_BYTES", 10)

    with pytest.raises(skill_performance.SkillPerformanceError) as exc:
        skill_performance._read_record_file(record_path)

    assert exc.value.code == "PROCESS_RECORD_FILE_TOO_LARGE"
    assert "NVFLARE_AGENT_MAX_RECORD_BYTES" in exc.value.hint


def test_summaries_ignore_non_finite_metric_values():
    summaries = skill_performance._summaries(
        [
            {
                "schema_version": "1",
                "skill": "nvflare-test-skill",
                "case_id": "case-1",
                "process_metrics": {
                    "elapsed_seconds": "inf",
                    "token_count": "nan",
                    "conversion_quality": "1.0",
                },
            }
        ],
        [],
    )

    assert summaries[0]["elapsed_seconds"] == {"avg": None, "available": 0, "unavailable": 1}
    assert summaries[0]["token_count"] == {"avg": None, "available": 0, "unavailable": 1}
    assert summaries[0]["conversion_quality"] == {"avg": 1.0, "available": 1, "unavailable": 0}


def test_load_records_sorts_mixed_timestamps_by_time_not_string(tmp_path):
    old_fallback = tmp_path / "record.json"
    old_fallback.write_text(
        json.dumps({"schema_version": "1", "skill": "nvflare-test-skill", "case_id": "fallback"}),
        encoding="utf-8",
    )
    old_ns = 946684800 * 1_000_000_000
    os.utime(old_fallback, ns=(old_ns, old_ns))
    iso_record = tmp_path / "iso.json"
    iso_record.write_text(
        json.dumps(
            {
                "schema_version": "1",
                "skill": "nvflare-test-skill",
                "case_id": "iso",
                "timestamp": "2026-01-01T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )

    records, _status = skill_performance._load_records(tmp_path)

    assert [record["case_id"] for record in records] == ["iso", "fallback"]
    assert "_sort_timestamp" not in records[0]


def test_record_sort_timestamp_uses_negative_sentinel_for_stat_failure(tmp_path):
    assert skill_performance._record_sort_timestamp({}, tmp_path / "missing.json") == -1


def test_summary_key_preserves_group_dimensions():
    assert skill_performance._summary_key("skill", "1.0", "case", "with_skills", "abc123") == (
        "skill",
        "1.0",
        "case",
        "with_skills",
        "abc123",
    )


def test_empty_manifest_surfaces_record_matching_warning(tmp_path):
    record_path = tmp_path / "record.json"
    record_path.write_text(
        json.dumps({"schema_version": "1", "skill": "nvflare-test-skill", "case_id": "case-1"}),
        encoding="utf-8",
    )
    source = SkillSource(source_type="editable", root=tmp_path, manifest={"skills": []})

    data = skill_performance.summarize_skill_performance(records_path=record_path, source=source)

    assert data["records"] == []
    assert data["record_warnings"]
    assert "No packaged skill names" in data["record_warnings"][0]
