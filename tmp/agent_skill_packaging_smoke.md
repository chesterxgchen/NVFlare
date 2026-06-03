# Agent Skill Packaging Smoke Checklist

Use this checklist in a fresh environment when validating the real installed
NVFLARE skill path. This is intentionally outside normal unit pytest because it
depends on an installed wheel or editable source environment.

## What To Verify

1. Build/install package from branch:

```bash
uv pip install -e .
```

Or build a wheel and install it into a clean env if you want stronger coverage:

```bash
uv pip install dist/<nvflare-wheel>.whl
```

2. Check bundled skill manifest:

```bash
nvflare --format json agent skills list --agent codex
nvflare --format json agent skills list --agent claude
```

Confirm that these skills are available:

- `nvflare-orient`
- `nvflare-convert-pytorch`
- `nvflare-diagnose-job`

Confirm `_shared` is not listed as an installable skill.

3. Dry-run install:

```bash
nvflare --format json agent skills install --agent codex --dry-run
nvflare --format json agent skills install --agent claude --dry-run
```

Confirm the dry-run plan includes the three seed skills and no filesystem
changes are made.

4. Install into temporary homes, not your real agent dirs.

Use `CODEX_HOME` for Codex. For Claude, if the CLI only resolves
`~/.claude/skills`, use a temporary `HOME`.

```bash
CODEX_HOME=/tmp/nvflare-codex-test nvflare --format json agent skills install --agent codex
HOME=/tmp/nvflare-claude-test nvflare --format json agent skills install --agent claude
```

5. Verify installed skills:

```bash
find /tmp/nvflare-codex-test/skills -maxdepth 2 -type f
find /tmp/nvflare-claude-test/.claude/skills -maxdepth 2 -type f
```

Confirm that `nvflare-diagnose-job` includes:

- `SKILL.md`
- `references/evidence-collection.md`
- `references/failure-patterns.md`
- `evals/evals.json`
- `evals/files/poc_component_not_authorized.log`
- `evals/files/simulation_import_error.log`
- `evals/files/transfer_progress_timeout.log`
