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

"""Benchmark case metadata extraction shared by report generators."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ARTIFACT_TEXT_SUFFIXES = {".cfg", ".ini", ".json", ".md", ".py", ".toml", ".txt", ".yaml", ".yml"}
ARTIFACT_TEXT_KEYS = ("changed_files", "runtime_artifacts")


def first_dict(*values: Any) -> dict[str, Any]:
    for value in values:
        if isinstance(value, dict):
            return value
    return {}


def find_nested_value(obj: Any, keys: set[str]) -> Any:
    if isinstance(obj, dict):
        for key, value in obj.items():
            if str(key).lower() in keys and value not in (None, ""):
                return value
            found = find_nested_value(value, keys)
            if found not in (None, ""):
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = find_nested_value(value, keys)
            if found not in (None, ""):
                return found
    return None


def first_int_from_text(patterns: list[str], texts: list[str]) -> int | None:
    for text in texts:
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                try:
                    return int(match.group(1))
                except (TypeError, ValueError):
                    pass
    return None


def first_text_match(patterns: list[str], texts: list[str]) -> str | None:
    for text in texts:
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return match.group(1).strip()
    return None


def normalize_algorithm(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip().strip("`'\".,)")
    lowered = re.sub(r"[^a-z0-9]+", "", text.lower())
    aliases = {
        "fedavg": "FedAvg",
        "fedaverage": "FedAvg",
        "federatedaveraging": "FedAvg",
        "fedprox": "FedProx",
        "fedopt": "FedOpt",
        "fedadam": "FedAdam",
        "fedyogi": "FedYogi",
        "fedavgm": "FedAvgM",
        "fednova": "FedNova",
        "fedsgd": "FedSGD",
        "fedbn": "FedBN",
        "fedbuff": "FedBuff",
        "scaffold": "SCAFFOLD",
        "scoffold": "SCAFFOLD",
        "ditto": "Ditto",
    }
    if lowered in {"federated", "federation", "federal"}:
        return None
    for alias, canonical in aliases.items():
        if alias in lowered:
            return canonical
    return text or None


def first_algorithm_match(text: str) -> str | None:
    patterns = [
        r"\b(FedAvgM|FedAvg|FedProx|FedOpt|FedAdam|FedYogi|FedNova|FedSGD|FedBN|FedBuff|SCAFFOLD|Ditto)\b",
        r"\b(fed\s+avgm|fed\s+avg|fed\s+prox|fed\s+opt|fed\s+adam|fed\s+yogi|fed\s+nova|fed\s+sgd|fed\s+bn|fed\s+buff)\b",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            algorithm = normalize_algorithm(match.group(1))
            if algorithm == "SCAFFOLD" and _is_data_scaffold_context(text, match.start(), match.end()):
                continue
            if algorithm:
                return algorithm
    return None


def _is_data_scaffold_context(text: str, start: int, end: int) -> bool:
    """Return True when "scaffold" refers to molecular data splitting, not FL SCAFFOLD."""

    window = text[max(0, start - 120) : min(len(text), end + 120)].lower()
    data_split_phrases = (
        "scaffold split",
        "scaffold splitting",
        "split is scaffold",
        "split performance",
        "chemical scaffold",
        "molecular scaffold",
        "by scaffold",
        "random split",
        "data split",
    )
    if any(phrase in window for phrase in data_split_phrases):
        return True
    return bool(re.search(r"\bscaffold\b.{0,40}\b(?:split|splitting|fallback|random)\b", window))


def load_generated_artifact_text(
    run_dir: str | Path,
    manifest: dict[str, Any],
    *,
    max_files: int = 40,
    max_bytes: int = 256 * 1024,
) -> str:
    """Load bounded generated/conversion artifact text for report-only metadata inference."""

    if not isinstance(manifest, dict):
        return ""
    run_dir = Path(run_dir)
    delta_root = run_dir / "workspace_delta"
    chunks: list[str] = []
    captured_files = 0
    captured_bytes = 0
    for key in ARTIFACT_TEXT_KEYS:
        entries = manifest.get(key)
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if captured_files >= max_files or captured_bytes >= max_bytes:
                return "\n".join(chunks)
            if not isinstance(entry, dict):
                continue
            artifact_path = entry.get("artifact_path")
            if not isinstance(artifact_path, str) or not artifact_path:
                continue
            source_name = str(entry.get("path") or artifact_path)
            if Path(source_name).suffix.lower() not in ARTIFACT_TEXT_SUFFIXES:
                continue
            path = delta_root / artifact_path
            if not path.is_file() or path.is_symlink():
                continue
            remaining = max_bytes - captured_bytes
            if remaining <= 0:
                return "\n".join(chunks)
            try:
                raw = path.read_bytes()[:remaining]
            except OSError:
                continue
            captured_files += 1
            captured_bytes += len(raw)
            chunks.append(f"\n# generated artifact: {source_name}\n{raw.decode('utf-8', errors='replace')}")
    return "\n".join(chunks)


def case_text_sources(run: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[str]]:
    summary = first_dict(run.get("summary"), run.get("run"))
    record = first_dict(run.get("process_record"), run.get("record"))
    runtime_image = first_dict(run.get("runtime_image"))
    prompt_text = str(run.get("prompt_text") or "")
    last_message_text = str(run.get("last_message_text") or run.get("last_message") or "")
    generated_artifact_text = str(run.get("generated_artifact_text") or "")
    json_texts = [json.dumps(value, sort_keys=True, default=str) for value in (summary, record, runtime_image)]
    return (
        summary,
        record,
        runtime_image,
        [generated_artifact_text, last_message_text, "\n".join(json_texts), prompt_text],
    )


def algorithm_signal(run: dict[str, Any]) -> dict[str, str | None]:
    summary, record, _runtime_image, texts = case_text_sources(run)
    metadata_value = find_nested_value(
        [summary, record],
        {"algorithm", "fl_algorithm", "fed_algorithm", "aggregation_algorithm", "server_algorithm", "recipe"},
    )
    algorithm = normalize_algorithm(metadata_value)
    if algorithm:
        return {"algorithm": algorithm, "source": "record/summary metadata"}

    source_texts = [
        ("prompt/request text", texts[3]),
    ]
    for source, text in source_texts:
        algorithm = first_algorithm_match(text)
        if algorithm:
            return {"algorithm": algorithm, "source": source}
    return {"algorithm": None, "source": None}


def algorithm_consensus(runs: dict[str, dict[str, Any]], modes: list[str]) -> str:
    algorithms: list[str] = []
    for mode in modes:
        signal = runs[mode].get("algorithm_signal")
        signal = signal if isinstance(signal, dict) else algorithm_signal(runs[mode])
        algorithm = signal.get("algorithm")
        if algorithm and algorithm not in algorithms:
            algorithms.append(str(algorithm))
    if not algorithms:
        return "not detected"
    if len(algorithms) == 1:
        return algorithms[0]
    return "mixed: " + ", ".join(algorithms)


def benchmark_case_metadata(run: dict[str, Any]) -> dict[str, Any]:
    summary, record, runtime_image, texts = case_text_sources(run)

    client_count = find_nested_value(
        [summary, record],
        {"num_clients", "number_of_clients", "client_count", "num_sites", "site_count", "sites"},
    )
    if not isinstance(client_count, (int, float)) or isinstance(client_count, bool):
        client_count = first_int_from_text(
            [
                r"\b(\d+)\s+(?:simulated\s+)?(?:sites?|clients?)\b",
                r"\b(?:sites?|clients?)\s*[:=]\s*(\d+)\b",
            ],
            texts,
        )

    round_count = find_nested_value([summary, record], {"num_rounds", "round_count", "rounds"})
    if not isinstance(round_count, (int, float)) or isinstance(round_count, bool):
        round_count = first_int_from_text(
            [
                r"\b(\d+)\s+(?:fedavg\s+|fedprox\s+|training\s+)?rounds?\b",
                r"\brounds?\s*[:=]\s*(\d+)\b",
            ],
            texts,
        )

    algorithm = algorithm_signal(run).get("algorithm")

    job_name = find_nested_value([summary, record], {"job_name", "nvflare_job_name"})
    if not isinstance(job_name, str) or not job_name.strip():
        job_name = (
            first_text_match([r"job_config/([A-Za-z0-9_.-]+)"], texts)
            or first_text_match([r"Exported job:\s*(?:-\s*)?`[^`]*?/([A-Za-z0-9_.-]+)`"], texts)
            or first_text_match([r"workspace/([A-Za-z0-9_.-]+)/(?:server|client_outputs|simulate_job)"], texts)
        )

    agent_model = (
        summary.get("agent_model")
        or record.get("agent_model")
        or runtime_image.get("agent_model")
        or runtime_image.get("codex_model")
        or "unknown"
    )
    agent = (
        summary.get("agent")
        or record.get("agent")
        or runtime_image.get("agent")
        or runtime_image.get("benchmark_agent")
        or "unknown"
    )

    if isinstance(job_name, str):
        job_name = job_name.strip().strip("`'\".,)")

    return {
        "run": run.get("name"),
        "clients": (
            int(client_count) if isinstance(client_count, (int, float)) and not isinstance(client_count, bool) else None
        ),
        "algorithm": algorithm,
        "rounds": (
            int(round_count) if isinstance(round_count, (int, float)) and not isinstance(round_count, bool) else None
        ),
        "job_name": job_name if isinstance(job_name, str) and job_name else None,
        "agent": agent,
        "agent_model": agent_model,
    }
