#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../config/hardening.conf"

# Setup mount points
mkdir -p "$INPUT_MOUNT" "$OUTPUT_MOUNT"

# Configure encryption if key file exists
if [ -f "$LUKS_KEYFILE" ]; then
    # Setup LUKS for input
    cryptsetup luksFormat \
        --type luks2 \
        --cipher "$LUKS_CIPHER" \
        --key-size "$LUKS_KEYSIZE" \
        --key-file "$LUKS_KEYFILE" \
        "${INPUT_DEVICE}"

    # Setup LUKS for output
    cryptsetup luksFormat \
        --type luks2 \
        --cipher "$LUKS_CIPHER" \
        --key-size "$LUKS_KEYSIZE" \
        --key-file "$LUKS_KEYFILE" \
        "${OUTPUT_DEVICE}"
fi 