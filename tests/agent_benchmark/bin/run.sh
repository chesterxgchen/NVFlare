#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BENCHMARK_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
export PYTHONPATH="${BENCHMARK_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"

usage() {
  cat <<EOF
Usage: $(basename "$0") COMMAND [--training-code PATH] [--results-root PATH] [PATH]

Commands:
  one              Run one benchmark case using MODE/USE_PREINSTALLED_SKILLS env.
  pair             Run paired skills/no-skills benchmark cases.
  process-eval     Run the three-mode skill-eval ablation.
  interactive      Start an interactive benchmark container.
  with-skills      Shortcut for: MODE=with_skills_eval_off USE_PREINSTALLED_SKILLS=true one.
  with-skills-eval-on
                   Shortcut for: MODE=with_skills_eval_on NVFLARE_SKILL_EVAL=on one.
  without-skills   Shortcut for: MODE=without_skills USE_PREINSTALLED_SKILLS=false one.

Examples:
  ./bin/run.sh process-eval /path/to/job-folder
  ./bin/run.sh process-eval --results-root /path/to/results /path/to/job-folder
  ./bin/run.sh process-eval --output-dir /path/to/exact-run-dir /path/to/job-folder
  ./bin/run.sh pair --training-code /path/to/job-folder
  ./bin/run.sh one /path/to/job-folder
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
    exec python3 -m harness.host.runner run-one "$@"
    ;;
  pair)
    exec python3 -m harness.host.runner pair "$@"
    ;;
  process-eval|ablation)
    exec python3 -m harness.host.runner process-eval "$@"
    ;;
  interactive|shell)
    exec python3 -m harness.host.runner interactive "$@"
    ;;
  with-skills)
    MODE=with_skills_eval_off USE_PREINSTALLED_SKILLS=true PROCESS_EVAL=false NVFLARE_SKILL_EVAL= exec python3 -m harness.host.runner run-one "$@"
    ;;
  with-skills-eval-on)
    MODE=with_skills_eval_on USE_PREINSTALLED_SKILLS=true PROCESS_EVAL=true NVFLARE_SKILL_EVAL=on exec python3 -m harness.host.runner run-one "$@"
    ;;
  without-skills)
    MODE=without_skills USE_PREINSTALLED_SKILLS=false PROCESS_EVAL=false NVFLARE_SKILL_EVAL= exec python3 -m harness.host.runner run-one "$@"
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
