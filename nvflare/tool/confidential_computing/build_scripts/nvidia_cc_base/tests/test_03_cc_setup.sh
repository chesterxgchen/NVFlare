#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"
source "${SCRIPT_DIR}/../config/partition.conf"
source "${SCRIPT_DIR}/../config/security.conf"

test_cc_setup() {
    local test_dir=$(mktemp -d)
    
    # Mount image
    guestmount -a "$OUTPUT_IMAGE" -i "$test_dir"
    
    # Test CC runtime
    if [ ! -d "${test_dir}/etc/nvidia-cc" ]; then
        error "NVIDIA CC runtime not configured"
    fi
    
    # Test CC environment
    if [ ! -d "${test_dir}${CC_USER_HOME}" ]; then
        error "CC user home not configured"
    fi
    
    # Test CC permissions
    if [ "$(stat -c %U:%G ${test_dir}${CC_USER_HOME})" != "${CC_USER}:${CC_GROUP}" ]; then
        error "Wrong CC user home ownership"
    fi
    
    # Cleanup
    guestunmount "$test_dir"
    rm -rf "$test_dir"
}

test_cc_setup 