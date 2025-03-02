#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/config/hardening.conf"

# Run hardening scripts
for script in "${SCRIPT_DIR}"/scripts/[0-9]*.sh; do
    bash "$script"
done

# Run tests
for test in "${SCRIPT_DIR}"/tests/test_*.sh; do
    bash "$test"
done 