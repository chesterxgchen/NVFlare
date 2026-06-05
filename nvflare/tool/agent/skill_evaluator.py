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

"""Checklist-first runtime evaluator for NVFLARE-owned agent skills."""

import json
import os
import tempfile
import time
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from nvflare.tool.agent.skill_manifest import skill_tree_hash
from nvflare.tool.agent.skill_performance import DEFAULT_RECORDS_ROOT, EVALS_FILE

SCHEMA_VERSION = "1"
SCORING_SOURCE = "agent_skill_evaluation:v1"
ALLOWED_STATUSES = {"pass", "fail", "missing", "not_applicable", "non_scoring_note"}
AGENT_CHOICES = {"codex", "claude", "other", "unknown"}
RUN_MODE_CHOICES = {"without_skill", "with_skill", "with_skill_forced"}
STANDARD_PROCESS_METRICS = {
    "elapsed_seconds",
    "token_count",
    "turns_to_acceptable",
    "user_correction_count",
    "agent_self_correction_count",
    "layout_violations",
    "workflow_violations",
    "evidence_gap_violations",
    "validation_commands_run",
    "unnecessary_files_created",
    "conversion_quality",
}
INTEGER_PROCESS_METRICS = {
    "token_count",
    "turns_to_acceptable",
    "user_correction_count",
    "agent_self_correction_count",
    "layout_violations",
    "workflow_violations",
    "evidence_gap_violations",
    "validation_commands_run",
    "unnecessary_files_created",
    "conversion_quality",
}
RUNTIME_FIELDS = {
    "eval_passed",
    "score",
    "evaluation",
    "source_hash",
    "source_commit",
    "skill_version",
    "agent",
    "run_mode",
}
RATIONALE_TEMPLATES = {
    5: "One-shot correct; required evidence present; no user or agent correction recorded.",
    4: "Accepted first pass with no user correction; agent self-correction or harmless issue recorded.",
    3: "Functional result accepted, but user correction or missing mandatory evidence capped the score.",
    2: "Runnable or partially useful result, but validation/prohibited/significant-violation cap applied.",
    1: "Failed, unsafe, wrong-trigger, or incomplete result.",
}


class SkillEvaluationError(ValueError):
    """Input or write error that should be returned as a JSON error envelope."""

    def __init__(self, code: str, message: str, hint: str = "", detail: str = ""):
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint
        self.detail = detail


def evaluate_skill_run(
    *,
    skill_name: str,
    case_id: Optional[str],
    agent: str = "unknown",
    run_mode: Optional[str] = None,
    skill_version: Optional[str] = None,
    artifacts_path: Optional[Path | str] = None,
    checklist_path: Optional[Path | str] = None,
    records_path: Optional[Path | str] = None,
    source=None,
) -> dict:
    """Evaluate one runtime skill run and write a process record."""
    start_time = time.monotonic()
    if not case_id:
        raise SkillEvaluationError("CASE_REQUIRED", "--case is required.", "Pass --case <eval-id>.")
    if agent not in AGENT_CHOICES:
        raise SkillEvaluationError("CHECKLIST_SCHEMA_INVALID", f"unsupported agent value: {agent}")
    if run_mode is not None and run_mode not in RUN_MODE_CHOICES:
        raise SkillEvaluationError("CHECKLIST_SCHEMA_INVALID", f"unsupported run_mode value: {run_mode}")
    if artifacts_path is None and checklist_path is None:
        raise SkillEvaluationError(
            "EVIDENCE_REQUIRED",
            "Runtime evaluation requires --artifacts or --checklist.",
            "Pass a structured artifact directory or reviewer checklist JSON.",
        )

    from nvflare.tool.agent import skill_manager

    source = source or skill_manager.find_skill_source()
    skill = _select_skill(source.manifest.get("skills") or [], skill_name)
    skill_dir = source.root / skill["relative_path"]
    eval_case = _load_eval_case(skill_dir, case_id)
    behavior_spec = _behavior_spec(eval_case)
    nvflare_spec = eval_case.get("nvflare") or {}
    declared_process_metrics = _declared_process_metrics(eval_case)

    artifact_data = _load_artifacts(artifacts_path) if artifacts_path else {}
    checklist_data = _load_checklist(checklist_path, skill_name=skill_name, case_id=case_id) if checklist_path else {}
    merged = _merge_inputs([artifact_data, checklist_data])
    _reject_runtime_supplied_fields(checklist_data)
    _reject_runtime_supplied_fields(artifact_data.get("evidence", {}))

    behavior_maps = _normalize_behavior_maps(merged.get("behavior_evidence") or {}, behavior_spec)
    first_pass = _validate_first_pass(merged.get("first_pass"))
    final_result = _validate_final_result(merged.get("final_result"))
    process_metrics = _validate_process_metrics(
        merged.get("process_metrics") or {}, declared_process_metrics=declared_process_metrics
    )
    skill_selection = _validate_skill_selection(
        merged.get("skill_selection") or {}, nvflare_spec=nvflare_spec, require=_requires_skill_selection(behavior_spec)
    )
    significant_violations = _validate_significant_violations(merged.get("significant_violations") or [])
    skill_improvements = _bounded_string_list(
        merged.get("skill_improvements") or [], field="skill_improvements", required=False
    )
    prompt_summary = _bounded_optional_string(merged.get("prompt_summary"), "prompt_summary")

    _validate_evidence_required(behavior_maps, behavior_spec, skill_selection, first_pass, final_result)

    if agent == "unknown" and merged.get("agent"):
        agent = merged["agent"]
    if run_mode is None and merged.get("run_mode"):
        run_mode = merged["run_mode"]
    if agent not in AGENT_CHOICES:
        raise SkillEvaluationError("CHECKLIST_SCHEMA_INVALID", f"unsupported agent value: {agent}")
    if run_mode is not None and run_mode not in RUN_MODE_CHOICES:
        raise SkillEvaluationError("CHECKLIST_SCHEMA_INVALID", f"unsupported run_mode value: {run_mode}")

    if skill_version is None:
        skill_version = _first_non_empty(skill.get("skill_version"), merged.get("skill_version"))

    try:
        source_hash = skill_tree_hash(skill_dir)
    except ValueError as e:
        raise SkillEvaluationError(
            "CHECKLIST_SCHEMA_INVALID", str(e), "Remove symlinks from the selected skill."
        ) from e

    eval_passed = _eval_passed(
        behavior_maps=behavior_maps,
        final_result=final_result,
        skill_selection=skill_selection,
        significant_violations=significant_violations,
        require_skill_selection=_requires_skill_selection(behavior_spec),
    )
    score_value, rationale = _score(
        eval_passed=eval_passed,
        behavior_maps=behavior_maps,
        first_pass=first_pass,
        final_result=final_result,
        process_metrics=process_metrics,
        skill_selection=skill_selection,
        significant_violations=significant_violations,
        trigger_only=_requires_skill_selection(behavior_spec),
    )

    evaluation_elapsed = round(time.monotonic() - start_time, 3)
    record = {
        "schema_version": SCHEMA_VERSION,
        "skill": skill_name,
        "skill_version": skill_version,
        "case_id": case_id,
        "agent": agent,
        "run_mode": run_mode,
        "source_hash": source_hash,
        "source_commit": merged.get("source_commit"),
        "prompt_summary": prompt_summary,
        "mandatory_behavior": behavior_maps["mandatory_behavior"],
        "prohibited_behavior": behavior_maps["prohibited_behavior"],
        "optional_behavior": behavior_maps["optional_behavior"],
        "first_pass": first_pass,
        "final_result": final_result,
        "skill_selection": skill_selection,
        "eval_passed": eval_passed,
        "process_metrics": process_metrics,
        "significant_violations": significant_violations,
        "score": {"value": score_value, "max": 5, "rationale": rationale},
        "skill_improvements": skill_improvements,
        "evaluation": {
            "mode": "on",
            "elapsed_seconds": evaluation_elapsed,
            "token_count": 0,
            "scoring_source": SCORING_SOURCE,
        },
    }

    records_root = Path(records_path).expanduser() if records_path else DEFAULT_RECORDS_ROOT
    record_path = _write_record(records_root, skill_name, case_id, record)
    return {"record_path": str(record_path), "eval_passed": eval_passed, "record": record}


def _select_skill(skills: list[dict], skill_name: str) -> dict:
    for skill in skills:
        if skill.get("name") == skill_name:
            return skill
    raise SkillEvaluationError("UNKNOWN_SKILL", f"NVFLARE skill not found: {skill_name}")


def _load_eval_case(skill_dir: Path, case_id: str) -> dict:
    evals_path = skill_dir / EVALS_FILE
    if not evals_path.is_file():
        raise SkillEvaluationError("UNKNOWN_CASE", f"skill has no evals/evals.json: {skill_dir.name}")
    data = _read_json(evals_path, "UNKNOWN_CASE")
    for eval_case in data.get("evals") or []:
        if isinstance(eval_case, dict) and eval_case.get("id") == case_id:
            return eval_case
    raise SkillEvaluationError("UNKNOWN_CASE", f"NVFLARE eval case not found: {case_id}")


def _behavior_spec(eval_case: dict) -> dict:
    nvflare_spec = eval_case.get("nvflare") or {}
    return {
        "mandatory_behavior": _behavior_ids(nvflare_spec.get("mandatory_behavior") or []),
        "prohibited_behavior": _behavior_ids(nvflare_spec.get("prohibited_behavior") or []),
        "optional_behavior": _behavior_ids(nvflare_spec.get("optional_behavior") or []),
    }


def _declared_process_metrics(eval_case: dict) -> set[str]:
    nvflare_spec = eval_case.get("nvflare") or {}
    process_evaluation = nvflare_spec.get("process_evaluation") or {}
    return {
        metric.get("id")
        for metric in process_evaluation.get("metrics") or []
        if isinstance(metric, dict) and metric.get("id")
    }


def _behavior_ids(items: list) -> set[str]:
    return {item.get("id") for item in items if isinstance(item, dict) and item.get("id")}


def _requires_skill_selection(behavior_spec: dict) -> bool:
    return not behavior_spec["mandatory_behavior"] and not behavior_spec["prohibited_behavior"]


def _load_artifacts(path: Path | str) -> dict:
    root = Path(path).expanduser()
    if not root.exists():
        raise SkillEvaluationError("ARTIFACT_NOT_FOUND", f"artifact path does not exist: {root}")
    if not root.is_dir():
        raise SkillEvaluationError("ARTIFACT_NOT_FOUND", f"artifact path is not a directory: {root}")

    result = {}
    run_path = root / "run.json"
    evidence_path = root / "evidence.json"
    if run_path.is_file():
        run_data = _read_json(run_path, "CHECKLIST_SCHEMA_INVALID")
        result = _merge_inputs([result, _normalize_run_json(run_data)])
    if evidence_path.is_file():
        evidence = _read_json(evidence_path, "CHECKLIST_SCHEMA_INVALID")
        result["evidence"] = evidence
        result = _merge_inputs([result, evidence])
    return result


def _normalize_run_json(data: dict) -> dict:
    if not isinstance(data, dict):
        raise SkillEvaluationError("CHECKLIST_SCHEMA_INVALID", "run.json must be a JSON object.")
    result = {}
    process_metrics = {}
    for key in ("elapsed_seconds", "token_count"):
        if key in data:
            process_metrics[key] = data[key]
    if isinstance(data.get("process_metrics"), dict):
        process_metrics.update(data["process_metrics"])
    if process_metrics:
        result["process_metrics"] = process_metrics
    for key in (
        "agent",
        "run_mode",
        "source_commit",
        "skill_version",
        "prompt_summary",
        "first_pass",
        "final_result",
        "skill_selection",
    ):
        if key in data:
            result[key] = data[key]
    return result


def _load_checklist(path: Path | str, *, skill_name: str, case_id: str) -> dict:
    checklist_path = Path(path).expanduser()
    if not checklist_path.is_file():
        raise SkillEvaluationError("ARTIFACT_NOT_FOUND", f"checklist path does not exist: {checklist_path}")
    data = _read_json(checklist_path, "CHECKLIST_SCHEMA_INVALID")
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
        raise SkillEvaluationError("CHECKLIST_SCHEMA_INVALID", 'checklist must contain schema_version "1".')
    if data.get("skill") != skill_name or data.get("case_id") != case_id:
        raise SkillEvaluationError("CHECKLIST_MISMATCH", "checklist skill or case_id does not match selected inputs.")
    return data


def _read_json(path: Path, code: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise SkillEvaluationError(code, f"invalid JSON file: {path}", detail=str(e)) from e


def _reject_runtime_supplied_fields(data: dict) -> None:
    if not isinstance(data, dict):
        return
    for field in RUNTIME_FIELDS:
        if field in data:
            raise SkillEvaluationError("CHECKLIST_SCHEMA_INVALID", f"runtime-computed field is not allowed: {field}")


def _merge_inputs(sources: list[dict]) -> dict:
    merged = {}
    for source in sources:
        if not source:
            continue
        for key, value in source.items():
            if key in {"schema_version", "skill", "case_id", "evidence"}:
                continue
            if key == "behavior_evidence":
                merged[key] = _merge_behavior_evidence(merged.get(key, {}), value or {})
            elif key in {"first_pass", "final_result", "process_metrics", "skill_selection"}:
                merged[key] = _merge_scalar_dicts(merged.get(key, {}), value or {}, key)
            elif key in {"significant_violations", "skill_improvements"}:
                merged[key] = _merge_lists(merged.get(key, []), value or [])
            else:
                merged[key] = _merge_scalar(merged.get(key), value, key)
    return merged


def _merge_behavior_evidence(left: dict, right: dict) -> dict:
    if not isinstance(left, dict) or not isinstance(right, dict):
        raise SkillEvaluationError("CHECKLIST_SCHEMA_INVALID", "behavior_evidence must be a JSON object.")
    result = deepcopy(left)
    for category in ("mandatory_behavior", "prohibited_behavior", "optional_behavior"):
        result.setdefault(category, {})
        for behavior_id, entry in (right.get(category) or {}).items():
            if behavior_id not in result[category]:
                result[category][behavior_id] = deepcopy(entry)
                continue
            result[category][behavior_id] = _merge_behavior_entry(
                result[category][behavior_id], entry, f"behavior_evidence.{category}.{behavior_id}"
            )
    return result


def _merge_behavior_entry(left: dict, right: dict, field: str) -> dict:
    if not isinstance(left, dict) or not isinstance(right, dict):
        raise SkillEvaluationError("CHECKLIST_SCHEMA_INVALID", f"{field} must be a JSON object.")
    result = dict(left)
    if left.get("status") != right.get("status"):
        raise SkillEvaluationError("CONFLICTING_EVIDENCE", f"conflicting behavior status for {field}")
    for key in ("evidence",):
        result[key] = _merge_lists(left.get(key, []), right.get(key, []))
    result["notes"] = _merge_scalar(left.get("notes"), right.get("notes"), f"{field}.notes")
    return result


def _merge_scalar_dicts(left: dict, right: dict, field: str) -> dict:
    if not isinstance(right, dict):
        raise SkillEvaluationError("CHECKLIST_SCHEMA_INVALID", f"{field} must be a JSON object.")
    result = dict(left or {})
    for key, value in right.items():
        if key in {"violations"}:
            result[key] = _merge_lists(result.get(key, []), value or [])
        else:
            result[key] = _merge_scalar(result.get(key), value, f"{field}.{key}")
    return result


def _merge_scalar(left: Any, right: Any, field: str) -> Any:
    if left is None:
        return deepcopy(right)
    if right is None:
        return left
    if left != right:
        raise SkillEvaluationError("CONFLICTING_EVIDENCE", f"conflicting values for {field}")
    return left


def _merge_lists(left: list, right: list) -> list:
    if not isinstance(left, list) or not isinstance(right, list):
        raise SkillEvaluationError("CHECKLIST_SCHEMA_INVALID", "list-valued evidence field must be a list.")
    result = []
    seen = set()
    for item in list(left) + list(right):
        key = json.dumps(item, sort_keys=True) if isinstance(item, (dict, list)) else str(item)
        normalized = key.strip()
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append(item)
    return result


def _normalize_behavior_maps(input_maps: dict, spec: dict) -> dict:
    result = {"mandatory_behavior": {}, "prohibited_behavior": {}, "optional_behavior": {}}
    all_canonical = spec["mandatory_behavior"] | spec["prohibited_behavior"] | spec["optional_behavior"]
    for category in result:
        entries = input_maps.get(category) or {}
        if not isinstance(entries, dict):
            raise SkillEvaluationError("CHECKLIST_SCHEMA_INVALID", f"{category} must be a JSON object.")
        for behavior_id, entry in entries.items():
            if behavior_id not in spec[category]:
                if category == "optional_behavior" and _entry_status(entry) == "non_scoring_note":
                    if behavior_id in all_canonical:
                        raise SkillEvaluationError(
                            "INVALID_STATUS", "non_scoring_note is invalid for canonical behavior IDs."
                        )
                    result[category][behavior_id] = _validate_behavior_entry(entry, category)
                    continue
                raise SkillEvaluationError("INVALID_BEHAVIOR_ID", f"unsupported behavior ID: {behavior_id}")
            result[category][behavior_id] = _validate_behavior_entry(entry, category)

    for behavior_id in spec["optional_behavior"]:
        result["optional_behavior"].setdefault(behavior_id, {"status": "missing", "evidence": [], "notes": ""})
    return result


def _entry_status(entry: Any) -> Optional[str]:
    return entry.get("status") if isinstance(entry, dict) else None


def _validate_behavior_entry(entry: Any, category: str) -> dict:
    if not isinstance(entry, dict):
        raise SkillEvaluationError("CHECKLIST_SCHEMA_INVALID", "behavior entry must be a JSON object.")
    status = entry.get("status")
    if status not in ALLOWED_STATUSES:
        raise SkillEvaluationError("INVALID_STATUS", f"unsupported behavior status: {status}")
    if category in {"mandatory_behavior", "prohibited_behavior"} and status in {
        "not_applicable",
        "non_scoring_note",
    }:
        raise SkillEvaluationError("INVALID_STATUS", f"{status} is invalid for {category}")
    if status == "not_applicable" and category != "optional_behavior":
        raise SkillEvaluationError("INVALID_STATUS", "not_applicable is valid only for optional behavior.")
    return {
        "status": status,
        "evidence": _bounded_string_list(entry.get("evidence") or [], field="evidence", required=False),
        "notes": _bounded_optional_string(entry.get("notes", ""), "notes") or "",
    }


def _validate_first_pass(data: Any) -> dict:
    if not isinstance(data, dict):
        raise SkillEvaluationError("EVIDENCE_REQUIRED", "first_pass evidence is required.")
    accepted = data.get("accepted")
    if not isinstance(accepted, bool):
        raise SkillEvaluationError("CHECKLIST_SCHEMA_INVALID", "first_pass.accepted must be boolean.")
    return {
        "accepted": accepted,
        "violations": _bounded_string_list(data.get("violations") or [], field="first_pass.violations", required=False),
    }


def _validate_final_result(data: Any) -> dict:
    if not isinstance(data, dict):
        raise SkillEvaluationError("EVIDENCE_REQUIRED", "final_result evidence is required.")
    accepted = data.get("accepted")
    if not isinstance(accepted, bool):
        raise SkillEvaluationError("CHECKLIST_SCHEMA_INVALID", "final_result.accepted must be boolean.")
    result = {"accepted": accepted}
    for key in ("validation_passed", "simulation_passed"):
        value = data.get(key)
        if value is not None and not isinstance(value, bool):
            raise SkillEvaluationError("CHECKLIST_SCHEMA_INVALID", f"final_result.{key} must be boolean or null.")
        result[key] = value
    return result


def _validate_process_metrics(data: dict, *, declared_process_metrics: set[str]) -> dict:
    if not isinstance(data, dict):
        raise SkillEvaluationError("CHECKLIST_SCHEMA_INVALID", "process_metrics must be a JSON object.")
    allowed = STANDARD_PROCESS_METRICS | declared_process_metrics
    result = {metric_id: None for metric_id in sorted(STANDARD_PROCESS_METRICS)}
    for key, value in data.items():
        if key not in allowed:
            raise SkillEvaluationError("CHECKLIST_SCHEMA_INVALID", f"process_metrics.{key} is not declared.")
        if key not in STANDARD_PROCESS_METRICS:
            result[key] = _validate_declared_process_metric(key, value)
            continue
        if isinstance(value, bool):
            raise SkillEvaluationError("CHECKLIST_SCHEMA_INVALID", f"process_metrics.{key} must not be boolean.")
        if value is not None and not isinstance(value, (int, float)):
            raise SkillEvaluationError("CHECKLIST_SCHEMA_INVALID", f"process_metrics.{key} must be numeric or null.")
        if key in INTEGER_PROCESS_METRICS and value is not None and not isinstance(value, int):
            raise SkillEvaluationError("CHECKLIST_SCHEMA_INVALID", f"process_metrics.{key} must be an integer or null.")
        if key == "conversion_quality" and value is not None and not 1 <= int(value) <= 5:
            raise SkillEvaluationError(
                "CHECKLIST_SCHEMA_INVALID", "process_metrics.conversion_quality must be 1-5 or null."
            )
        result[key] = value
    return result


def _validate_declared_process_metric(key: str, value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _bounded_required_string(value, f"process_metrics.{key}")
    raise SkillEvaluationError(
        "CHECKLIST_SCHEMA_INVALID", f"process_metrics.{key} must be a scalar declared metric or null."
    )


def _validate_skill_selection(data: dict, *, nvflare_spec: dict, require: bool) -> dict:
    if not data:
        if require:
            raise SkillEvaluationError("EVIDENCE_REQUIRED", "skill_selection evidence is required.")
        return {}
    selected = data.get("selected_skill")
    expected = data.get("expected_skill", nvflare_spec.get("expected_skill"))
    negative = data.get("negative_for", nvflare_spec.get("negative_for"))
    assertion = data.get("assertion_passed")
    if assertion is not None and not isinstance(assertion, bool):
        raise SkillEvaluationError("CHECKLIST_SCHEMA_INVALID", "skill_selection.assertion_passed must be boolean.")
    if expected is not None and negative is not None and expected == negative:
        raise SkillEvaluationError("CHECKLIST_SCHEMA_INVALID", "expected_skill and negative_for cannot match.")
    computed = _skill_selection_assertion(selected, expected, negative)
    if assertion is not None and assertion != computed:
        raise SkillEvaluationError("CONFLICTING_EVIDENCE", "skill_selection.assertion_passed is inconsistent.")
    return {
        "selected_skill": selected,
        "expected_skill": expected,
        "negative_for": negative,
        "assertion_passed": computed,
    }


def _skill_selection_assertion(selected: Any, expected: Any, negative: Any) -> bool:
    selected_norm = _normalize_skill_name(selected)
    if expected is not None and negative is not None:
        return selected_norm == _normalize_skill_name(expected) and selected_norm != _normalize_skill_name(negative)
    if expected is not None:
        return selected_norm == _normalize_skill_name(expected)
    if negative is not None:
        negative_norm = _normalize_skill_name(negative)
        if negative_norm == "*":
            return selected_norm in {"", "none", "no_skill", "null"}
        return selected_norm != negative_norm
    return True


def _normalize_skill_name(value: Any) -> str:
    if value is None:
        return "none"
    return str(value).strip()


def _validate_significant_violations(items: list) -> list[dict]:
    if not isinstance(items, list):
        raise SkillEvaluationError("CHECKLIST_SCHEMA_INVALID", "significant_violations must be a list.")
    if len(items) > 10:
        raise SkillEvaluationError("CHECKLIST_SCHEMA_INVALID", "significant_violations has too many entries.")
    result = []
    for item in items:
        if not isinstance(item, dict):
            raise SkillEvaluationError("CHECKLIST_SCHEMA_INVALID", "significant_violations entries must be objects.")
        result.append(
            {
                "description": _bounded_required_string(item.get("description"), "significant_violations.description"),
                "evidence_ref": _bounded_required_string(
                    item.get("evidence_ref"), "significant_violations.evidence_ref"
                ),
            }
        )
    return result


def _validate_evidence_required(
    behavior_maps: dict, spec: dict, skill_selection: dict, first_pass: dict, final_result: dict
) -> None:
    del first_pass, final_result
    for category in ("mandatory_behavior", "prohibited_behavior"):
        missing = sorted(spec[category].difference(behavior_maps[category]))
        if missing:
            raise SkillEvaluationError(
                "EVIDENCE_REQUIRED",
                f"{category} status missing for: {', '.join(missing)}",
                "Provide explicit pass/fail/missing behavior evidence.",
            )
    if _requires_skill_selection(spec) and not skill_selection:
        raise SkillEvaluationError("EVIDENCE_REQUIRED", "skill_selection evidence is required.")


def _eval_passed(
    *,
    behavior_maps: dict,
    final_result: dict,
    skill_selection: dict,
    significant_violations: list,
    require_skill_selection: bool,
) -> bool:
    if require_skill_selection and not skill_selection.get("assertion_passed"):
        return False
    if any(entry["status"] != "pass" for entry in behavior_maps["mandatory_behavior"].values()):
        return False
    if any(entry["status"] == "fail" for entry in behavior_maps["prohibited_behavior"].values()):
        return False
    if final_result.get("accepted") is not True:
        return False
    if final_result.get("validation_passed") is False or final_result.get("simulation_passed") is False:
        return False
    if significant_violations:
        return False
    return True


def _score(
    *,
    eval_passed: bool,
    behavior_maps: dict,
    first_pass: dict,
    final_result: dict,
    process_metrics: dict,
    skill_selection: dict,
    significant_violations: list,
    trigger_only: bool,
) -> tuple[int, str]:
    if trigger_only:
        return _trigger_score(skill_selection, first_pass, process_metrics)

    score = 5
    reasons = []
    if not final_result.get("accepted"):
        score = min(score, 1)
        reasons.append("final result not accepted")
    if final_result.get("validation_passed") is False or final_result.get("simulation_passed") is False:
        score = min(score, 2)
        reasons.append("validation or simulation failed")
    if any(entry["status"] != "pass" for entry in behavior_maps["mandatory_behavior"].values()):
        score = min(score, 3)
        reasons.append("mandatory behavior missing or failed")
    if any(entry["status"] == "fail" for entry in behavior_maps["prohibited_behavior"].values()):
        score = min(score, 2)
        reasons.append("prohibited behavior observed")
    if significant_violations:
        score = min(score, 2)
        reasons.append("significant violation recorded")

    user_corrections = process_metrics.get("user_correction_count")
    if user_corrections is None:
        score = min(score, 3)
        reasons.append("user correction count unavailable")
    elif user_corrections > 0:
        score = min(score, 3)
        reasons.append("user correction required")

    if not first_pass.get("accepted"):
        score = min(score, 3)
        reasons.append("first pass rejected")

    violation_fields = ("layout_violations", "workflow_violations", "evidence_gap_violations")
    for field in violation_fields:
        value = process_metrics.get(field)
        if value is None:
            score = min(score, 3)
            reasons.append(f"{field} unavailable")
            break
        if value > 0:
            score = min(score, 3)
            reasons.append(f"{field} recorded")
            break

    agent_self = process_metrics.get("agent_self_correction_count")
    if agent_self is None:
        score = min(score, 4)
        reasons.append("agent self-correction count unavailable")
    elif agent_self > 0:
        score = min(score, 4)
        reasons.append("agent self-correction recorded")

    if not eval_passed and score == 5:
        score = 3
        reasons.append("eval did not pass")
    return score, _rationale(score, reasons)


def _trigger_score(skill_selection: dict, first_pass: dict, process_metrics: dict) -> tuple[int, str]:
    if not skill_selection.get("assertion_passed"):
        return 1, _rationale(1, ["wrong or missing skill selection"])
    user_corrections = process_metrics.get("user_correction_count")
    if user_corrections is None or user_corrections > 0:
        return 3, _rationale(
            3, ["user correction required" if user_corrections else "user correction count unavailable"]
        )
    violation_fields = ("layout_violations", "workflow_violations", "evidence_gap_violations")
    for field in violation_fields:
        value = process_metrics.get(field)
        if value is None:
            return 3, _rationale(3, [f"{field} unavailable"])
        if value > 0:
            return 3, _rationale(3, [f"{field} recorded"])
    if not first_pass.get("accepted"):
        return 4, _rationale(4, ["agent self-correction before final assertion"])
    agent_self = process_metrics.get("agent_self_correction_count")
    if agent_self is None or agent_self > 0:
        return 4, _rationale(4, ["agent self-correction recorded"])
    return 5, _rationale(5, [])


def _rationale(score: int, reasons: list[str]) -> str:
    text = RATIONALE_TEMPLATES[score]
    if reasons:
        text = f"{text} {reasons[0]}."
    return text[:512]


def _write_record(records_root: Path, skill_name: str, case_id: str, record: dict) -> Path:
    target_dir = records_root / skill_name / case_id
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        for _attempt in range(5):
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            target = target_dir / f"{timestamp}.json"
            if target.exists():
                continue
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=target_dir, delete=False) as f:
                temp_path = Path(f.name)
                json.dump(record, f, indent=2, sort_keys=True)
                f.write("\n")
            os.replace(temp_path, target)
            return target
    except Exception as e:
        raise SkillEvaluationError(
            "RECORD_WRITE_FAILED", "failed to write runtime process record", detail=str(e)
        ) from e
    raise SkillEvaluationError("RECORD_WRITE_FAILED", "failed to create a unique runtime process record path")


def _bounded_string_list(items: list, *, field: str, required: bool) -> list[str]:
    if not isinstance(items, list):
        raise SkillEvaluationError("CHECKLIST_SCHEMA_INVALID", f"{field} must be a list.")
    if len(items) > 10:
        raise SkillEvaluationError("CHECKLIST_SCHEMA_INVALID", f"{field} has too many entries.")
    result = []
    for item in items:
        if not isinstance(item, str):
            raise SkillEvaluationError("CHECKLIST_SCHEMA_INVALID", f"{field} entries must be strings.")
        result.append(_bounded_required_string(item, field))
    if required and not result:
        raise SkillEvaluationError("EVIDENCE_REQUIRED", f"{field} is required.")
    return result


def _bounded_optional_string(value: Any, field: str) -> Optional[str]:
    if value is None:
        return None
    return _bounded_required_string(value, field)


def _bounded_required_string(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise SkillEvaluationError("CHECKLIST_SCHEMA_INVALID", f"{field} must be a string.")
    if len(value) > 512:
        raise SkillEvaluationError("CHECKLIST_SCHEMA_INVALID", f"{field} exceeds 512 characters.")
    if _contains_sensitive_text(value):
        raise SkillEvaluationError("CHECKLIST_SCHEMA_INVALID", f"{field} contains sensitive-looking text.")
    return value


def _contains_sensitive_text(value: str) -> bool:
    lowered = value.lower()
    sensitive_markers = ("begin private key", "access_token", "api_key", "password=", "secret=")
    return any(marker in lowered for marker in sensitive_markers)


def _first_non_empty(*values):
    for value in values:
        if value:
            return value
    return None
