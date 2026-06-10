#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
export PYTHONPATH="${REPO_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"

usage() {
  cat <<EOF
Usage: $(basename "$0") COMMAND --prompt PATH [--training-code PATH] [--results-root PATH] [PATH]

Commands:
  one              Run one benchmark case using MODE/USE_PREINSTALLED_SKILLS env.
  pair             Run paired skills/no-skills benchmark cases.
  scenario         Run a compiled scenario YAML.
  replay           Rebuild parser artifacts and scenario reports from captured results.
  interactive      Start an interactive benchmark container.
  with-skills      Shortcut for: MODE=with_skills USE_PREINSTALLED_SKILLS=true one.
  without-skills   Shortcut for: MODE=without_skills USE_PREINSTALLED_SKILLS=false one.

Examples:
  ./bin/run.sh pair --prompt /path/to/prompt.txt --training-code /path/to/job-folder
  ./bin/run.sh pair --prompt /path/to/prompt.txt --results-root /path/to/results /path/to/job-folder
  ./bin/run.sh pair --prompt /path/to/prompt.txt --output-dir /path/to/exact-run-dir /path/to/job-folder
  ./bin/run.sh scenario /path/to/scenario.yaml --output-dir /path/to/exact-run-dir
  ./bin/run.sh replay /path/to/existing-run-dir
  ./bin/run.sh one --prompt /path/to/prompt.txt /path/to/job-folder
EOF
}

if [[ "$#" -eq 0 ]]; then
  usage
  exit 2
fi

command="$1"
shift

case "${command}" in
  one|run-one|single)
    exec python3 -m assist_tools.skills_benchmark.skills.harness.host.runner run-one "$@"
    ;;
  pair)
    exec python3 -m assist_tools.skills_benchmark.skills.harness.host.runner pair "$@"
    ;;
  scenario)
    exec python3 -m assist_tools.skills_benchmark.skills.harness.host.runner scenario "$@"
    ;;
  replay)
    exec python3 -m assist_tools.skills_benchmark.skills.harness.host.runner replay "$@"
    ;;
  interactive|shell)
    exec python3 -m assist_tools.skills_benchmark.skills.harness.host.runner interactive "$@"
    ;;
  with-skills)
    MODE=with_skills USE_PREINSTALLED_SKILLS=true exec python3 -m assist_tools.skills_benchmark.skills.harness.host.runner run-one "$@"
    ;;
  without-skills)
    MODE=without_skills USE_PREINSTALLED_SKILLS=false exec python3 -m assist_tools.skills_benchmark.skills.harness.host.runner run-one "$@"
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    echo "Unknown command: ${command}" >&2
    usage >&2
    exit 2
    ;;
esac
