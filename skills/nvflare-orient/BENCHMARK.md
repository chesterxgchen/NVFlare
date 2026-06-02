# Benchmark Summary

Status: draft/internal pending Milestone 11 runtime evaluation.

Skill version: 0.1.0
FLARE version: 2.8.0 minimum

## Initial Checks

| Check | Status | Notes |
| --- | --- | --- |
| Positive trigger | Draft | `orient-ambiguous-project` defines the initial routing prompt. |
| Adjacent negative trigger | Draft | PyTorch conversion routes to `nvflare-convert-pytorch`. |
| Global negative trigger | Draft | Non-FLARE web-app prompt routes to no skill. |
| Mandatory behavior | Draft | Behavior IDs cover inspect-first, read-only routing, and single lead skill. |
| Prohibited behavior | Draft | Behavior IDs prohibit file edits and production actions. |

## Known Gaps

- Runtime agent-performance scoring has not been run yet.
- `nvflare-diagnose-job` is intentionally deferred from this seed pass.
- Orientation routing will need new adjacent negatives as more workflow skills
  are added.
