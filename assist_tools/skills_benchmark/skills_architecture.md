# FLARE Agent Skill Architecture

This is a picture of what is implemented today for the `nvflare agent` skill
system: the agent-facing CLI, the packaged skills, the install/list/reporting
paths, and the benchmark harness that measures skill impact.

## High-Level System View

```mermaid
flowchart TB
    Authoring["Skill Authoring Source: skills, references, eval contracts"] --> Lint["Engineering Lint Tool: module CLI plus pytest-covered checks"]
    Lint --> Package["Python Packaging Hook: setup.py and bundled_skills manifest"]
    Package --> Install["Skill Install CLI: nvflare agent skills install and list"]
    Install --> AgentHome["Agent Skill Home: Codex or Claude skill directory"]

    AgentHome --> AgentRuntime["Agent Runtime: Codex or Claude loads SKILL.md"]
    AgentRuntime --> AgentCLI["Agent-Facing NVFLARE CLI: info, inspect, doctor, skills"]
    AgentRuntime --> NVFLAREWork["NVFLARE Workflows: recipes, job.py, simulator, job CLI"]

    EvalHarness["Evaluation Harness: assist_tools/skills_benchmark"] --> AgentRuntime
    AgentRuntime --> Evidence["Run Evidence: events, usage, workspace delta, records"]
    Evidence --> Reporting["Reporting: skill performance, benchmark, scenario report"]
    Reporting --> Authoring
```

## System Layers

| Layer | Implemented pieces | Purpose |
| --- | --- | --- |
| Authoring source | `skills/`, `SKILL.md`, `references/`, `evals/evals.json`, `BENCHMARK.md` | Human-readable skill instructions and supporting evidence. |
| Engineering lint tool | `nvflare.tool.agent_skill_checks`, `python -m nvflare.tool.agent_skill_checks`, pytest coverage | Deterministic admission checks for frontmatter, triggers, command drift, policy coverage, fixtures, process metrics, and doc links. The check itself is a CLI/library tool; pytest validates the tool behavior. |
| Python packaging hook | `setup.py`, `nvflare.tool.agent.bundled_skills`, `manifest.json` | Standard wheel-build hook that copies released skills into the NVFLARE package or writes an empty bundle for no-skill builds. |
| Skill install CLI | `nvflare agent skills install/list`, `skill_manager.py` | CLI copy/install tool that installs managed skills into Codex or Claude target directories with hashes, locks, backups, and symlink checks. |
| Runtime agent surface | Codex/Claude skill loading, `nvflare agent inspect`, `nvflare agent doctor`, recipe/job CLI | The agent reads skill instructions and uses NVFLARE commands to inspect, convert, validate, or diagnose. |
| Evaluation and reporting | `assist_tools/skills_benchmark`, `skill_performance.py`, `skill_benchmark.py` | Runs with-skill vs no-skill comparisons and summarizes runtime evidence. |

## Implemented Architecture

```mermaid
flowchart LR
    User["User / Benchmark Prompt"] --> Agent["Codex or Claude CLI"]

    Agent --> InstalledSkills["Agent Skill Directory: Codex CODEX_HOME skills or Claude launch add-dir"]

    NVCLI["nvflare agent CLI"] --> Info["info"]
    NVCLI --> Inspect["inspect: static AST scan"]
    NVCLI --> Doctor["doctor: readiness check"]
    NVCLI --> SkillOps["skills install/list"]
    NVCLI --> Perf["skills performance"]
    NVCLI --> Bench["skills benchmark"]

    SkillSource["repo-root skills: editable checkout"] --> SkillOps
    WheelBundle["nvflare.tool.agent.bundled_skills: wheel package bundle"] --> SkillOps
    SkillOps --> InstalledSkills

    Agent -->|follows SKILL.md| Inspect
    Agent -->|readiness| Doctor
    Agent -->|normal NVFLARE work| Recipes["NVFLARE recipes / job.py / simulator / CLI"]

    Inspect --> Project["Local training code / FLARE job artifacts"]
    Doctor --> Env["Local NVFLARE install, startup kits, optional deps, POC workspace"]
```

## Skill Source And Install Flow

```mermaid
flowchart TD
    SkillsRoot["repo-root skills/"] --> SkillDirs["nvflare-orient, nvflare-convert-pytorch, nvflare-diagnose-job, shared references"]

    SkillDirs --> ManifestBuild["build_skill_manifest: frontmatter validation and source hash"]
    ManifestBuild --> Editable["Editable source manifest"]

    SkillsRoot --> SetupPy["setup.py build_py"]
    SetupPy --> Bundle["wheel bundled_skills + manifest.json"]
    SetupPy --> EmptyBundle["empty bundled_skills manifest"]

    Editable --> FindSource["find_skill_source"]
    Bundle --> FindSource

    FindSource --> Install["nvflare agent skills install"]
    Install --> Target["Agent target skill dir"]
    Target --> InstallManifest[".nvflare_skill_install.json with managed_by, source_hash, skill_version"]

    Install --> Safety["symlink checks, lock dir, atomic staging, backup on replace, local modification detection"]
```

## What The Skills Actually Do

```mermaid
flowchart LR
    Orient["nvflare-orient: read-only router"] --> InspectCmd["nvflare agent inspect"]
    Orient --> DoctorCmd["nvflare agent doctor"]
    Orient --> Recommend["Recommend next skill"]

    Convert["nvflare-convert-pytorch: edits files"] --> InspectCmd
    Convert --> RecipeList["nvflare recipe list"]
    Convert --> ClientAPI["Generate client.py/model.py/job.py with FLModel exchange"]
    Convert --> Validate["python job.py and export job"]

    Diagnose["nvflare-diagnose-job: read-only"] --> InspectCmd
    Diagnose --> Logs["Bounded logs / job evidence"]
    Diagnose --> Patterns["Packaged failure-pattern references"]
    Diagnose --> Cause["Likely cause + next action"]
```

## Benchmark Harness

```mermaid
flowchart TD
    Host["assist_tools/skills_benchmark/bin/run.sh"] --> Plan["scenario / run_plan"]
    Plan --> Docker["Docker run"]

    Docker --> Baseline["baseline image: NVFLARE wheel without skills"]
    Docker --> Skills["skills image: NVFLARE wheel with packaged skills"]

    Skills --> Preinstall["nvflare agent skills install into agent home"]
    Preinstall --> AgentRun["Run Codex/Claude with same prompt + input"]
    Baseline --> AgentRun

    AgentRun --> Events["agent_events.jsonl"]
    AgentRun --> Usage["agent_usage.json"]
    AgentRun --> Delta["workspace_delta"]
    AgentRun --> Records["process records / run_summary"]
    Records --> Reports["scenario report, skill performance, skill benchmark"]
```

## Key Implementation Points

- Public skill source: `/Users/chesterc/projects/NVFlare/skills`
- Implemented skills:
  - `nvflare-orient`
  - `nvflare-convert-pytorch`
  - `nvflare-diagnose-job`
- Agent-facing CLI: `/Users/chesterc/projects/NVFlare/nvflare/tool/agent/agent_cli.py`
- Skill install/list logic: `/Users/chesterc/projects/NVFlare/nvflare/tool/agent/skill_manager.py`
- Static inspection: `/Users/chesterc/projects/NVFlare/nvflare/tool/agent/inspector.py`
- Readiness checks: `/Users/chesterc/projects/NVFlare/nvflare/tool/agent/doctor.py`
- Packaging hook: `/Users/chesterc/projects/NVFlare/setup.py:116`
- Benchmark runtime: `/Users/chesterc/projects/NVFlare/assist_tools/skills_benchmark`

The important boundary: NVFLARE does not run a custom agent runtime for these
skills. It packages, installs, validates, and measures skill files that
Codex/Claude then load through their own skill mechanisms.
