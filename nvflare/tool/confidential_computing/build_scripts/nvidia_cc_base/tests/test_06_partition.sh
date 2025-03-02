#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"
source "${SCRIPT_DIR}/../config/partition.conf"
source "${SCRIPT_DIR}/../config/security.conf"

test_partition_setup() {
    local test_dir=$(mktemp -d)
    
    # Mount image
    guestmount -a "$OUTPUT_IMAGE" -i "$test_dir"
    
    # Test boot partition
    if ! grep -q "/boot.*ext4" "${test_dir}/etc/fstab"; then
        error "Boot partition not configured"
    fi
    
    # Test LUKS on root partition
    if ! cryptsetup isLuks "${DEVICE}p2"; then
        error "Root partition not LUKS encrypted"
    fi
    
    # Test LUKS on app partition
    if ! cryptsetup isLuks "${DEVICE}p3"; then
        error "App partition not LUKS encrypted"
    fi
    
    # Test read-only partition
    if ! grep -q "$RO_MOUNT.*ro" "${test_dir}/etc/fstab"; then
        error "Read-only partition not mounted as read-only"
    fi
    
    # Test dynamic partition
    if ! grep -q "$DYNAMIC_MOUNT" "${test_dir}/etc/fstab"; then
        error "Dynamic partition not configured"
    fi
    
    # Test crypttab entries
    if ! grep -q "root_crypt.*luks" "${test_dir}/etc/crypttab"; then
        error "Root partition crypto not configured"
    fi
    if ! grep -q "app_crypt.*luks" "${test_dir}/etc/crypttab"; then
        error "App partition crypto not configured"
    fi
    
    # Cleanup
    guestunmount "$test_dir"
    rm -rf "$test_dir"
}

test_partition_setup 