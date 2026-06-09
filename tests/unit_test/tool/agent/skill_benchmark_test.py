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
from pathlib import Path

import pytest

from nvflare.tool.agent import skill_benchmark
from nvflare.tool.agent.skill_benchmark import SkillBenchmarkError, render_skill_benchmark
from nvflare.tool.agent.skill_manager import SkillSource
from nvflare.tool.agent.skill_manifest import build_skill_manifest


def test_render_skill_benchmark_dry_run_does_not_write_default_output(tmp_path):
    source = _skill_source(tmp_path)
    records = _write_records(tmp_path)

    data = render_skill_benchmark(
        skill_name="nvflare-test-skill",
        records_path=records,
        dry_run=True,
        source=source,
    )

    benchmark_path = source.root / "nvflare-test-skill" / "BENCHMARK.md"
    assert data["written"] is False
    assert data["output_path"] == str(benchmark_path)
    assert "# Agent Skill Benchmark" in data["content"]
    assert "| nvflare-test-skill | case-1 |" in data["content"]
    assert not benchmark_path.exists()


def test_render_skill_benchmark_writes_explicit_output(tmp_path):
    source = _skill_source(tmp_path)
    records = _write_records(tmp_path)
    output = tmp_path / "out" / "BENCHMARK.md"

    data = render_skill_benchmark(
        skill_name="nvflare-test-skill",
        records_path=records,
        output_path=output,
        source=source,
    )

    assert data["written"] is True
    assert data["output_path"] == str(output)
    assert output.read_text(encoding="utf-8") == data["content"]


def test_render_skill_benchmark_requires_skill_name(tmp_path):
    source = _skill_source(tmp_path)

    with pytest.raises(SkillBenchmarkError) as exc:
        render_skill_benchmark(skill_name=None, source=source)

    assert exc.value.code == "BENCHMARK_SKILL_REQUIRED"


def test_write_text_atomic_removes_temp_file_on_replace_failure(tmp_path, monkeypatch):
    captured = {}

    def fail_replace(src, dst):
        captured["src"] = Path(src)
        assert captured["src"].is_file()
        raise OSError("replace failed")

    monkeypatch.setattr(skill_benchmark.os, "replace", fail_replace)

    with pytest.raises(SkillBenchmarkError) as exc:
        skill_benchmark._write_text_atomic(tmp_path / "BENCHMARK.md", "content\n")

    assert exc.value.code == "BENCHMARK_WRITE_FAILED"
    assert captured["src"].exists() is False


def _skill_source(tmp_path) -> SkillSource:
    root = tmp_path / "skills"
    skill_dir = root / "nvflare-test-skill"
    skill_dir.mkdir(parents=True)
    skill_dir.joinpath("SKILL.md").write_text(
        "---\n"
        "name: nvflare-test-skill\n"
        "description: Test skill fixture.\n"
        'min_flare_version: "2.8.0"\n'
        "blast_radius: read_only\n"
        "---\n"
        "\n"
        "# Test Skill\n",
        encoding="utf-8",
    )
    evals_dir = skill_dir / "evals"
    evals_dir.mkdir()
    evals_dir.joinpath("evals.json").write_text(
        json.dumps(
            {
                "skill_name": "nvflare-test-skill",
                "evals": [
                    {
                        "id": "case-1",
                        "prompt": "Run test skill.",
                        "nvflare": {
                            "process_metrics": [
                                {"id": "elapsed_seconds", "description": "elapsed time"},
                                {"id": "token_count", "description": "tokens"},
                            ]
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return SkillSource(
        source_type="editable",
        root=root,
        manifest=build_skill_manifest(root, source_type="editable", nvflare_version="2.8.0"),
    )


def _write_records(tmp_path):
    records = tmp_path / "records.json"
    records.write_text(
        json.dumps(
            {
                "schema_version": "1",
                "skill": "nvflare-test-skill",
                "case_id": "case-1",
                "timestamp": "2026-06-08T00:00:00Z",
                "process_metrics": {"elapsed_seconds": 12, "token_count": 100},
            }
        ),
        encoding="utf-8",
    )
    return records
