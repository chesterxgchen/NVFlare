#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"
source "${SCRIPT_DIR}/../config/partition.conf"
source "${SCRIPT_DIR}/../config/tee.conf"

test_tee_setup() {
    local test_dir=$(mktemp -d)
    
    # Mount image
    guestmount -a "$OUTPUT_IMAGE" -i "$test_dir"
    
    # Test TEE config file
    if [ ! -f "${test_dir}/boot/cc/tee.conf" ]; then
        error "TEE configuration not found"
    fi
    
    # Source TEE config
    source "${test_dir}/boot/cc/tee.conf"
    
    # Test TEE memory settings
    if [ ! -d "${test_dir}${TEE_MEMORY_PATH}" ]; then
        error "TEE memory path not created"
    fi
    
    # Test TEE service
    if [ ! -f "${test_dir}/etc/systemd/system/tee-memory.service" ]; then
        error "TEE memory service not configured"
    fi
    
    # Test TEE script
    if [ ! -x "${test_dir}/usr/local/sbin/configure-tee-memory" ]; then
        error "TEE configuration script not installed"
    fi
    
    # Test permissions
    if [ "$(stat -c %a ${test_dir}${TEE_MEMORY_PATH})" != "$TEE_MEMORY_MODE" ]; then
        error "TEE memory has wrong permissions"
    fi
    
    # Test fstab entry
    if ! grep -q "tmpfs.*${TEE_MEMORY_PATH}" "${test_dir}/etc/fstab"; then
        error "TEE memory not configured in fstab"
    fi
    
    # Cleanup
    guestunmount "$test_dir"
    rm -rf "$test_dir"
}

test_tee_setup 