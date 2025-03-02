#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"
source "${SCRIPT_DIR}/../config/partition.conf"
source "${SCRIPT_DIR}/../config/security.conf"

# Test security configuration
test_security() {
    local test_dir=$(mktemp -d)
    
    # Mount image
    guestmount -a "$OUTPUT_IMAGE" -i "$test_dir"
    
    # Test kernel modules
    for module in "${KERNEL_MODULES_DISABLE[@]}"; do
        if ! grep -q "blacklist $module" "${test_dir}/etc/modprobe.d/blacklist-cc.conf"; then
            error "Kernel module $module not blacklisted"
        fi
    done
    
    # Test services
    for service in "${SYSTEM_SERVICES_DISABLE[@]}"; do
        if [ -f "${test_dir}/etc/systemd/system/$service.service" ]; then
            error "Service $service not disabled"
        fi
    done
    
    # Test secure directories
    for dir_config in "${SECURE_DIRS[@]}"; do
        IFS=':' read -r dir owner group mode <<< "$dir_config"
        if [ ! -d "${test_dir}${dir}" ]; then
            error "Secure directory $dir not found"
        fi
        if [ "$(stat -c %a ${test_dir}${dir})" != "$mode" ]; then
            error "Directory $dir has wrong permissions"
        fi
    done
    
    # Test kernel parameters
    if ! grep -q "kernel.modules_disabled = 1" "${test_dir}/etc/sysctl.d/99-cc-secure.conf"; then
        error "Kernel hardening not configured"
    fi
    
    # Cleanup
    guestunmount "$test_dir"
    rm -rf "$test_dir"
}

# Test TEE configuration
test_tee_config() {
    local test_dir=$(mktemp -d)
    
    # Mount image
    guestmount -a "$OUTPUT_IMAGE" -i "$test_dir"
    
    # Check TEE config exists
    if [ ! -f "${test_dir}/boot/cc/tee.conf" ]; then
        error "TEE configuration not found"
    fi
    
    # Source TEE config
    source "${test_dir}/boot/cc/tee.conf"
    
    # Check TEE memory settings
    if [ ! -d "${test_dir}${TEE_MEMORY_PATH}" ]; then
        error "TEE memory path not created"
    fi
    
    # Check permissions
    if [ "$(stat -c %a ${test_dir}${TEE_MEMORY_PATH})" != "$TEE_MEMORY_MODE" ]; then
        error "TEE memory has wrong permissions"
    fi
    
    # Cleanup
    guestunmount "$test_dir"
    rm -rf "$test_dir"
}

test_security
test_tee_config 