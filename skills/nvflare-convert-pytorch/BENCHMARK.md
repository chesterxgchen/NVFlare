# Benchmark Summary

Status: draft/internal pending Milestone 11 runtime evaluation.

Skill version: 0.1.0
FLARE version: 2.8.0 minimum

## Initial Checks

| Check | Status | Notes |
| --- | --- | --- |
| Positive trigger | Draft | `pytorch-convert-basic` covers standard PyTorch training conversion. |
| Adjacent negative trigger | Draft | Lightning prompt routes away from this skill. |
| Global negative trigger | Draft | Kubernetes deployment prompt routes away from this skill. |
| Mandatory behavior | Draft | Behavior IDs cover inspect-first, recipe discovery, recipe selection from FL intent, scoped edits, Client API exchange, and local validation. |
| Prohibited behavior | Draft | Behavior IDs prohibit production submit, private data copying, and CLI-wrapper Python. |

## Known Gaps

- Runtime agent-performance scoring has not been run yet.
- The seed skill targets standard PyTorch loops only, not Lightning,
  Hugging Face Trainer, TensorFlow, XGBoost, sklearn, or custom NumPy loops.
- Export validation uses FedJob system arguments; no job-local export argument
  definition is required.
- `nvflare-diagnose-job` is intentionally deferred from this seed pass.
