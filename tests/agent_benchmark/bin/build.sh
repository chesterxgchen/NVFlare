#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BENCHMARK_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
export PYTHONPATH="${BENCHMARK_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"

exec python3 -m harness.host.build "$@"
