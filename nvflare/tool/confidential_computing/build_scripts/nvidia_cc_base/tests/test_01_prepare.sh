#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../scripts/common.sh"
source "${SCRIPT_DIR}/../config/partition.conf"
source "${SCRIPT_DIR}/../config/security.conf"
source "${SCRIPT_DIR}/../config/tee.conf"
source "${SCRIPT_DIR}/scripts/common/security_hardening.sh"

test_preparation() {
    # Test required tools
    local required_tools=(
        "debootstrap"
        "parted"
        "cryptsetup"
        "veritysetup"
        "tpm2_tools"
        "qemu-img"
        "curl"
        "wget"
    )
    
    for tool in "${required_tools[@]}"; do
        if ! command -v "$tool" &> /dev/null; then
            error "Required tool '$tool' not found"
        fi
    done
    
    # Test config files exist
    local required_configs=(
        "partition.conf"
        "security.conf"
        "tee.conf"
    )
    
    for config in "${required_configs[@]}"; do
        if [ ! -f "${SCRIPT_DIR}/config/${config}" ]; then
            error "Required config '${config}' not found"
        fi
    done
    
    # Test mount points
    local mount_points=(
        "$ROOT_MOUNT"
        "$APP_MOUNT"
        "$RO_MOUNT"
        "$DYNAMIC_MOUNT"
    )
    
    for mount in "${mount_points[@]}"; do
        if [ ! -d "$mount" ]; then
            error "Mount point not created: $mount"
        fi
    done
    
    # Test work directory
    if [ ! -d "${ROOT_MOUNT}/work" ]; then
        error "Work directory not created"
    fi
    
    # Test log directory and file
    if [ ! -f "${ROOT_MOUNT}/log/build.log" ]; then
        error "Build log not created"
    fi
    
    # Test security hardening
    verify_build_deps || error "Build dependencies verification failed"
}

test_preparation 