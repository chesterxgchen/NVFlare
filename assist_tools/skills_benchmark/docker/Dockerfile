ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.11.19
ARG NODE_IMAGE=node:22.16.0-bookworm-slim
ARG BENCHMARK_DOCKER_AGENT=codex
ARG BENCHMARK_AGENT_HOME=/workspace/.codex
ARG CODEX_CLI_VERSION=0.137.0
ARG CLAUDE_CLI_VERSION=latest

FROM ${UV_IMAGE} AS uv_source

FROM ${NODE_IMAGE} AS base
ARG UV_IMAGE
ARG NODE_IMAGE
ARG BENCHMARK_DOCKER_AGENT
ARG BENCHMARK_AGENT_HOME
ARG CODEX_CLI_VERSION
ARG CLAUDE_CLI_VERSION

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    ca-certificates \
    git \
    python3 \
    findutils \
    coreutils \
    tree \
    && rm -rf /var/lib/apt/lists/*

RUN if [ "${BENCHMARK_DOCKER_AGENT}" = "codex" ]; then \
        npm install -g "@openai/codex@${CODEX_CLI_VERSION}" && codex --version; \
    elif [ "${BENCHMARK_DOCKER_AGENT}" = "claude" ]; then \
        npm install -g "@anthropic-ai/claude-code@${CLAUDE_CLI_VERSION}" && claude --version; \
    else \
        echo "Unsupported BENCHMARK_DOCKER_AGENT=${BENCHMARK_DOCKER_AGENT}" >&2; \
        exit 2; \
    fi

COPY --from=uv_source /uv /uvx /usr/local/bin/
RUN uv --version

ENV BENCHMARK_DOCKER_AGENT=${BENCHMARK_DOCKER_AGENT}
ENV BENCHMARK_AGENT_HOME=${BENCHMARK_AGENT_HOME}
ENV JOB_INPUT_DIR=/workspace/input
ENV TRAINING_CODE=/workspace/input
ENV RECORDS_DIR=/tmp/nvflare/records

WORKDIR /workspace
RUN mkdir -p /workspace/.codex /workspace/.claude "${BENCHMARK_AGENT_HOME}" /workspace/prompts && \
    uv venv --seed /workspace/venv

ENV VIRTUAL_ENV=/workspace/venv
ENV PATH="/workspace/venv/bin:/usr/local/bin:${PATH}"

# Codex tool commands use `bash -lc`; Debian /etc/profile resets PATH for login shells.
RUN printf '%s\n' \
    'export VIRTUAL_ENV=/workspace/venv' \
    'case ":$PATH:" in *:/workspace/venv/bin:*) ;; *) export PATH="/workspace/venv/bin:$PATH" ;; esac' \
    > /etc/profile.d/99-nvflare-venv.sh && \
    /bin/bash -lc 'command -v python && python --version && python -m pip --version && pip --version'

RUN python --version && \
    python -m pip --version && \
    pip --version && \
    tree --version && \
    python -c "import json, os, pathlib, subprocess; agent=os.environ.get('BENCHMARK_DOCKER_AGENT', 'codex'); cli='codex' if agent == 'codex' else 'claude'; home=pathlib.Path(os.environ.get('BENCHMARK_AGENT_HOME', '/workspace/.codex')); home.mkdir(parents=True, exist_ok=True); home.joinpath('build_metadata.json').write_text(json.dumps({'agent': agent, 'agent_cli': cli, 'agent_cli_install_source': 'npm_global_runtime_base', 'agent_cli_version': subprocess.check_output([cli, '--version'], text=True).strip(), 'apt_package_policy': 'Debian apt packages are intentionally not exact-version pinned; rebuild comparability is tracked through the pinned base image/build args and recorded package/tool versions.', 'claude_cli_version_arg': os.environ.get('CLAUDE_CLI_VERSION'), 'codex_cli_version_arg': os.environ.get('CODEX_CLI_VERSION'), 'node_image': os.environ.get('NODE_IMAGE'), 'node_version': subprocess.check_output(['node', '--version'], text=True).strip(), 'nvflare_agent_skills_install_expected_source': 'local_nvflare_wheel', 'nvflare_agent_skills_install_network_proof': 'not_enforced_by_dockerfile', 'tree_version': subprocess.check_output(['tree', '--version'], text=True).splitlines()[0], 'uv_image': os.environ.get('UV_IMAGE'), 'uv_version': subprocess.check_output(['uv', '--version'], text=True).strip(), 'virtual_env': os.environ.get('VIRTUAL_ENV')}, indent=2, sort_keys=True) + '\n')"

COPY assist_tools/ /workspace/assist_tools/
CMD ["bash"]

FROM base AS skills

# Install NVFLARE from the staged local wheel that packages agent skills.
COPY dist/skills/*.whl dist/skills/nvflare_wheel_metadata.json /tmp/wheels/
RUN python -c "import sys; from pathlib import Path; wheels=sorted(Path('/tmp/wheels').glob('nvflare*.whl')); len(wheels) == 1 or sys.exit(f'Expected exactly one staged NVFLARE skills wheel in /tmp/wheels, found {len(wheels)}: {[p.name for p in wheels]}'); Path('/tmp/selected_nvflare_wheel').write_text(str(wheels[0]))" && \
    wheel="$(cat /tmp/selected_nvflare_wheel)" && \
    uv pip install --python /workspace/venv/bin/python "${wheel}" && \
    cp /tmp/wheels/nvflare_wheel_metadata.json "${BENCHMARK_AGENT_HOME}/nvflare_wheel_metadata.json" && \
    python -c "import json, os, sys; from pathlib import Path; meta=json.loads((Path(os.environ['BENCHMARK_AGENT_HOME']) / 'nvflare_wheel_metadata.json').read_text()); meta.get('nvflare_package_agent_skills') == '1' or sys.exit(f'Expected skills wheel metadata nvflare_package_agent_skills=1, got {meta.get(\"nvflare_package_agent_skills\")}')" && \
    rm -rf /tmp/wheels /tmp/selected_nvflare_wheel && \
    nvflare --version && \
    python -c "import nvflare" && \
    /bin/bash -lc 'command -v python && command -v nvflare && nvflare --version && python -c "import nvflare; print(nvflare.__version__)"'

# Preinstall skills from the local NVFLARE wheel so benchmark runs measure agent behavior, not skill install time.
# The Dockerfile records this expectation but does not enforce network isolation; run docker build with egress controls to audit hermeticity.
RUN python -c "import json, os, pathlib; home=pathlib.Path(os.environ['BENCHMARK_AGENT_HOME']); agent=os.environ['BENCHMARK_DOCKER_AGENT']; home.joinpath('nvflare_skills_build_metadata.json').write_text(json.dumps({'agent': agent, 'command': f'nvflare --format json agent skills install --agent {agent} --target {home / \"skills\"}', 'expected_source': 'local_nvflare_wheel', 'network_isolation_enforced': False, 'note': 'The build expects skills to come from the installed local NVFLARE wheel. The command is not wrapped by a Dockerfile-level network block.'}, indent=2, sort_keys=True) + '\n')" && \
    nvflare --format json agent skills install --agent "${BENCHMARK_DOCKER_AGENT}" --target "${BENCHMARK_AGENT_HOME}/skills" > "${BENCHMARK_AGENT_HOME}/nvflare_skills_build_install.json" && \
    nvflare --format json agent skills list --agent "${BENCHMARK_DOCKER_AGENT}" --target "${BENCHMARK_AGENT_HOME}/skills" > "${BENCHMARK_AGENT_HOME}/nvflare_skills_list.json" && \
    nvflare --format json agent skills list --agent "${BENCHMARK_DOCKER_AGENT}" --target "${BENCHMARK_AGENT_HOME}/skills"

FROM base AS baseline

# Baseline image: install NVFLARE from the staged local wheel built without packaged agent skills.
COPY dist/no_skills/*.whl dist/no_skills/nvflare_wheel_metadata.json /tmp/wheels/
RUN python -c "import sys; from pathlib import Path; wheels=sorted(Path('/tmp/wheels').glob('nvflare*.whl')); len(wheels) == 1 or sys.exit(f'Expected exactly one staged NVFLARE no-skills wheel in /tmp/wheels, found {len(wheels)}: {[p.name for p in wheels]}'); Path('/tmp/selected_nvflare_wheel').write_text(str(wheels[0]))" && \
    wheel="$(cat /tmp/selected_nvflare_wheel)" && \
    uv pip install --python /workspace/venv/bin/python "${wheel}" && \
    cp /tmp/wheels/nvflare_wheel_metadata.json "${BENCHMARK_AGENT_HOME}/nvflare_wheel_metadata.json" && \
    python -c "import json, os, sys; from pathlib import Path; meta=json.loads((Path(os.environ['BENCHMARK_AGENT_HOME']) / 'nvflare_wheel_metadata.json').read_text()); meta.get('nvflare_package_agent_skills') == '0' or sys.exit(f'Expected no-skills wheel metadata nvflare_package_agent_skills=0, got {meta.get(\"nvflare_package_agent_skills\")}')" && \
    rm -rf /tmp/wheels /tmp/selected_nvflare_wheel && \
    nvflare --version && \
    python -c "import nvflare" && \
    /bin/bash -lc 'command -v python && command -v nvflare && nvflare --version && python -c "import nvflare; print(nvflare.__version__)"' && \
    python -c "import json, os, pathlib; root=pathlib.Path(os.environ['BENCHMARK_AGENT_HOME']); agent=os.environ['BENCHMARK_DOCKER_AGENT']; reason=f'local no-skills wheel does not package {agent} skills'; (root / 'nvflare_skills_build_install.json').write_text(json.dumps({'status': 'skipped', 'agent': agent, 'reason': reason}, sort_keys=True) + '\n'); (root / 'nvflare_skills_list.json').write_text(json.dumps({'status': 'skipped', 'agent': agent, 'installed': [], 'reason': reason}, sort_keys=True) + '\n')"
