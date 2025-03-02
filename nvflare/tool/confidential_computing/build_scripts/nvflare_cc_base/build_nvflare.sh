#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/config/nvflare.conf"

# Parse role argument
ROLE="ALL"  # Default to both client and server

# Process arguments
while getopts "s:r:h" opt; do
    case $opt in
        s) RESIZE_TO="$OPTARG" ;;
        r) ROLE="$OPTARG" ;;
        h) usage ;;
        *) error "Invalid option: -$OPTARG" ;;
    esac
done

# Validate role
case $ROLE in
    ALL|CLIENT|SERVER) ;;
    *) error "Invalid role: $ROLE. Must be ALL, CLIENT, or SERVER"; exit 1 ;;
esac

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