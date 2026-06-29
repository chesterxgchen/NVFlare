# POC Workflow Eval Fixtures

These fixtures are synthetic, deterministic examples for NVFLARE POC workflow
skill admission tests. They are intentionally small and contain no private
data, generated benchmark output, real credentials, or runnable training data.

The JSON files model only enough system, doctor, and job-list shape to evaluate
routing, command selection, and safety boundaries. They follow the real
`nvflare ... --format json` envelope contract: a top-level
`{schema_version, status, exit_code, data}` wrapper with the command-specific
payload under `data` (job list `data` is the job array; system status and
doctor `data` are dicts). The process table is a handwritten sample for
orphan-recovery behavior checks, not live process data.
