# Agent Skill Packaging Smoke Checklist

Use this checklist in a fresh environment when validating the real installed
NVFLARE skill path. This is intentionally outside normal unit pytest because it
depends on an installed wheel or editable source environment.

## Install From Source Or Wheel

```bash
uv pip install -e .
```

or install the built wheel for release validation:

```bash
uv pip install dist/<nvflare-wheel>.whl
```

## List Bundled Skills

```bash
nvflare --format json agent skills list --agent codex
nvflare --format json agent skills list --agent claude
```

Confirm that these skills are available:

- `nvflare-orient`
- `nvflare-convert-pytorch`
- `nvflare-diagnose-job`

Confirm `_shared` is not listed as an installable skill.

## Dry-Run Install

```bash
nvflare --format json agent skills install --agent codex --dry-run
nvflare --format json agent skills install --agent claude --dry-run
```

Confirm the dry-run plan includes the three seed skills and no filesystem
changes are made.

## Install Into Temporary Agent Homes

```bash
CODEX_HOME=/tmp/nvflare-codex-test nvflare --format json agent skills install --agent codex
HOME=/tmp/nvflare-claude-test nvflare --format json agent skills install --agent claude
```

## Inspect Installed Files

```bash
find /tmp/nvflare-codex-test/skills -maxdepth 3 -type f | sort
find /tmp/nvflare-claude-test/.claude/skills -maxdepth 3 -type f | sort
```

Confirm that `nvflare-diagnose-job` includes:

- `SKILL.md`
- `references/evidence-collection.md`
- `references/failure-patterns.md`
- `evals/evals.json`
- `evals/files/poc_component_not_authorized.log`
- `evals/files/simulation_import_error.log`
- `evals/files/transfer_progress_timeout.log`

