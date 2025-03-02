#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/config/nvflare.conf"

# Process arguments
while getopts "s:" opt; do
    case $opt in
        s) RESIZE_TO="$OPTARG" ;;
        *) error "Invalid option: -$OPTARG" ;;
    esac
done

# Use default size if not specified
RESIZE_TO="${RESIZE_TO:-$DEFAULT_SIZE}"

# Run build scripts
for script in "${SCRIPT_DIR}"/scripts/[0-9]*.sh; do
    bash "$script"
done

# Run tests
for test in "${SCRIPT_DIR}"/tests/test_*.sh; do
    bash "$test"
done 