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

"""Best-effort quality signals derived from job instructions and final output."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

FLOAT_PATTERN = r"(?<![A-Za-z0-9_])([0-9]+\.[0-9]+)(?![A-Za-z0-9_])"
METRIC_ALIAS_PATTERNS = {
    "AUROC": r"\b(?:AUROC|AUC)\b|\b(?:valid|validation)[_-]?auroc\b",
    "accuracy": r"\baccuracy\b|\b(?:valid|validation)[_-]?accuracy\b|\bacc\b",
}


def canonical_metric_name(name: Any) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", str(name or "").strip()).strip("_")
    aliases = {
        "auroc": "AUROC",
        "auc": "AUROC",
        "valid_auroc": "AUROC",
        "validation_auroc": "AUROC",
        "accuracy": "accuracy",
        "acc": "accuracy",
        "valid_accuracy": "accuracy",
        "validation_accuracy": "accuracy",
    }
    return aliases.get(normalized.lower(), normalized)


def first_float(pattern: str, text: str) -> float | None:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return None
    try:
        return float(match.group(1))
    except (TypeError, ValueError):
        return None


def parse_float(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def line_value_after_metric(line: str, match: re.Match[str]) -> float | None:
    tail = line[match.end() :]
    delimiter = re.search(r"[,;]", tail)
    if delimiter:
        tail = tail[: delimiter.start()]
    value_match = re.search(FLOAT_PATTERN, tail)
    return parse_float(value_match.group(1)) if value_match else None


def label_from_metric_line(line: str) -> str | None:
    match = re.match(r"\s*[-*]?\s*`?([^`:]+?)`?\s*:", line)
    if not match:
        return None
    label = match.group(1).strip("` ")
    return label or None


def metric_value_entry(value: float, label: str | None = None) -> dict[str, Any]:
    entry: dict[str, Any] = {"value": value}
    if label:
        entry["label"] = label
    return entry


def following_line_values(lines: list[str], start_index: int, metric_pattern: str, limit: int = 8) -> list[float]:
    entries, _consumed = following_line_value_entries(lines, start_index, metric_pattern, limit)
    return [entry["value"] for entry in entries]


def line_metric_entries(line: str, metric_pattern: str) -> list[dict[str, Any]]:
    label = label_from_metric_line(line)
    entries: list[dict[str, Any]] = []
    for match in re.finditer(metric_pattern, line, flags=re.IGNORECASE):
        value = line_value_after_metric(line, match)
        if value is not None:
            entries.append(metric_value_entry(value, label))
    return entries


def single_unlabeled_metric_entry(line: str) -> dict[str, Any] | None:
    label = label_from_metric_line(line)
    matches = list(re.finditer(FLOAT_PATTERN, line))
    if len(matches) != 1:
        return None
    value = parse_float(matches[0].group(1))
    return metric_value_entry(value, label) if value is not None else None


def following_line_value_entries(
    lines: list[str],
    start_index: int,
    metric_pattern: str,
    limit: int = 8,
) -> tuple[list[dict[str, Any]], set[int]]:
    entries: list[dict[str, Any]] = []
    consumed: set[int] = set()
    for index in range(start_index + 1, min(len(lines), start_index + 1 + limit)):
        line = lines[index]
        stripped = line.strip()
        if not stripped:
            if entries:
                break
            continue
        if entries and not stripped.startswith(("-", "*", "`")) and ":" not in stripped:
            break
        line_entries = line_metric_entries(line, metric_pattern)
        if not line_entries:
            entry = single_unlabeled_metric_entry(line)
            line_entries = [entry] if entry else []
        if line_entries:
            entries.extend(line_entries)
            consumed.add(index)
        if entries and not stripped.startswith(("-", "*", "`")):
            break
    return entries, consumed


def metric_values(metric_name: str, text: str) -> list[float]:
    return [entry["value"] for entry in metric_value_entries(metric_name, text)]


def metric_value_entries(metric_name: str, text: str) -> list[dict[str, Any]]:
    canonical = canonical_metric_name(metric_name)
    pattern = METRIC_ALIAS_PATTERNS.get(canonical)
    if not pattern:
        pattern = rf"\b{re.escape(canonical)}\b"
    lines = text.splitlines()
    entries: list[dict[str, Any]] = []
    consumed_lines: set[int] = set()
    for index, line in enumerate(lines):
        if index in consumed_lines:
            continue
        matches = list(re.finditer(pattern, line, flags=re.IGNORECASE))
        if not matches:
            continue
        line_entries = line_metric_entries(line, pattern)
        if line_entries:
            entries.extend(line_entries)
            continue
        following_entries, consumed = following_line_value_entries(lines, index, pattern)
        entries.extend(following_entries)
        consumed_lines.update(consumed)
    return entries


def metric_mentioned(metric_name: str, text: str) -> bool:
    canonical = canonical_metric_name(metric_name)
    pattern = METRIC_ALIAS_PATTERNS.get(canonical, rf"\b{re.escape(canonical)}\b")
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def is_site_label(label: Any) -> bool:
    return re.search(r"\bsite[-_ ]?\d+\b", str(label or ""), flags=re.IGNORECASE) is not None


def reported_metric_payload(name: str, entries: list[dict[str, Any]]) -> dict[str, Any]:
    values = [entry["value"] for entry in entries if isinstance(entry.get("value"), (int, float))]
    labels = [entry.get("label") for entry in entries]
    has_single_value = len(values) == 1
    has_site_labels = bool(values) and all(is_site_label(label) for label in labels)
    if has_single_value:
        value_scope = "reported_scalar"
    elif has_site_labels:
        value_scope = "site_values_only"
    elif values:
        value_scope = "reported_values_only"
    else:
        value_scope = "not_available"
    return {
        "name": canonical_metric_name(name),
        "value": values[0] if has_single_value else None,
        "reported_values": values,
        "reported_value_labels": labels,
        "reported_value_entries": entries,
        "site_values": values if has_site_labels else [],
        "site_value_labels": labels if has_site_labels else [],
        "site_value_count": len(values) if has_site_labels else 0,
        "value_scope": value_scope,
        "source": "codex_last_message",
    }


def primary_metric_from_readme(readme_text: str) -> str | None:
    patterns = [
        r"^\s*[-*]?\s*([A-Za-z][A-Za-z0-9_./ -]{0,40}?)\s+is\s+the\s+main\s+metric\b",
        r"\bmain\s+metric\s+(?:to\s+watch\s+)?(?:is|:)\s*([A-Za-z][A-Za-z0-9_./ -]{0,40})",
        r"\bprimary\s+(?:validation\s+)?metric\s+(?:is|:)\s*([A-Za-z][A-Za-z0-9_./ -]{0,40})",
    ]
    for pattern in patterns:
        match = re.search(pattern, readme_text, flags=re.IGNORECASE | re.MULTILINE)
        if match:
            metric = re.split(r"[,.;\n]", match.group(1).strip(), maxsplit=1)[0].strip()
            metric = canonical_metric_name(metric)
            if metric:
                return metric
    return None


def reported_validation_metric(last_message: str, expected_metric: str | None) -> dict[str, Any]:
    detected = []
    for name in ("AUROC", "accuracy"):
        entries = metric_value_entries(name, last_message)
        if entries or metric_mentioned(name, last_message):
            detected.append(reported_metric_payload(name, entries))
    generic_value = first_float(
        r"(?:best )?(?:validation metric|global best validation metric)[^0-9`]*`?([0-9]+\.[0-9]+)`?",
        last_message,
    )
    if generic_value is not None:
        detected.append(
            {
                "name": "validation metric",
                "value": generic_value,
                "reported_values": [generic_value],
                "reported_value_labels": [None],
                "reported_value_entries": [{"value": generic_value}],
                "site_values": [],
                "site_value_labels": [],
                "site_value_count": 0,
                "value_scope": "reported_scalar",
                "source": "codex_last_message",
            }
        )
    if expected_metric and metric_mentioned(expected_metric, last_message):
        entries = metric_value_entries(expected_metric, last_message)
        return reported_metric_payload(expected_metric, entries)
    if detected:
        return detected[0]
    return {
        "name": None,
        "value": None,
        "reported_values": [],
        "reported_value_labels": [],
        "reported_value_entries": [],
        "site_values": [],
        "site_value_labels": [],
        "site_value_count": 0,
        "value_scope": "not_available",
        "source": "codex_last_message",
    }


def metric_signal(readme_path: Path | None, readme_text: str, final_message: str) -> dict[str, Any]:
    expected = primary_metric_from_readme(readme_text)
    reported = reported_validation_metric(final_message, expected)
    signal: dict[str, Any] = {
        "source": str(readme_path) if readme_path is not None else None,
        "expected_primary_metric": expected,
        "reported_validation_metric": reported,
        "available": bool(expected),
    }
    if not expected:
        signal["status"] = "not_available"
        return signal

    value = reported.get("value")
    reported_values = reported.get("reported_values")
    if not isinstance(reported_values, list):
        reported_values = []
    site_values = reported.get("site_values")
    if not isinstance(site_values, list):
        site_values = []
    has_value = isinstance(value, (int, float)) and not isinstance(value, bool)
    aligned = has_value and canonical_metric_name(reported.get("name")) == canonical_metric_name(expected)
    if aligned:
        status = "pass"
        evidence = (
            f"README declares {expected} as the primary metric, and the final response reported "
            f"{reported.get('name')} {value:.4f}."
        )
    elif reported.get("name") and has_value:
        status = "fail"
        evidence = (
            f"README declares {expected} as the primary metric, but the final response reported "
            f"{reported.get('name')}" + (f" {value:.4f}." if isinstance(value, float) else ".")
        )
    elif reported.get("name"):
        status = "missing"
        if site_values:
            evidence = (
                f"README declares {expected} as the primary metric, and the final response reported "
                f"{len(site_values)} site-level {reported.get('name')} values but no single FL-level value."
            )
        elif reported_values:
            evidence = (
                f"README declares {expected} as the primary metric, and the final response reported "
                f"{len(reported_values)} {reported.get('name')} values but no single FL-level value."
            )
        else:
            evidence = (
                f"README declares {expected} as the primary metric, and the final response mentioned "
                f"{reported.get('name')} but did not report a numeric value."
            )
    else:
        status = "missing"
        evidence = f"README declares {expected} as the primary metric, but the final response did not report it."

    signal.update(
        {
            "status": status,
            "evidence": evidence,
            "metric_value_available": has_value,
            "aligned_with_readme": aligned,
            "mismatch": not aligned,
        }
    )
    return signal


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("readme", type=Path)
    parser.add_argument("final_message", type=Path)
    args = parser.parse_args()
    readme_text = args.readme.read_text(encoding="utf-8", errors="replace") if args.readme.is_file() else ""
    final_text = (
        args.final_message.read_text(encoding="utf-8", errors="replace") if args.final_message.is_file() else ""
    )
    print(json.dumps(metric_signal(args.readme if args.readme.is_file() else None, readme_text, final_text), indent=2))


if __name__ == "__main__":
    main()
