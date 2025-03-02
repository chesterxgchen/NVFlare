#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"
source "${SCRIPT_DIR}/../config/partition.conf"
source "${SCRIPT_DIR}/../config/security.conf"

test_drivers() {
    local test_dir=$(mktemp -d)
    
    # Mount image
    guestmount -a "$OUTPUT_IMAGE" -i "$test_dir"
    
    # Test NVIDIA driver installation
    if ! grep -q "nvidia-${NVIDIA_DRIVER}" "${test_dir}/var/lib/dpkg/status"; then
        error "NVIDIA driver not installed"
    fi
    
    # Test CUDA installation
    if [ ! -d "${test_dir}/usr/local/cuda-${NVIDIA_CUDA}" ]; then
        error "CUDA not installed"
    fi
    
    # Test NVIDIA driver configuration
    if [ ! -f "${test_dir}/etc/modprobe.d/nvidia.conf" ]; then
        error "NVIDIA driver not configured"
    fi
    
    # Test AMD SEV driver
    if ! grep -q "snp-guest-dkms" "${test_dir}/var/lib/dpkg/status"; then
        error "AMD SEV driver not installed"
    fi
    
    # Test AMD driver configuration
    if ! grep -q "options snp-guest mode=1" "${test_dir}/etc/modprobe.d/snp-guest.conf"; then
        error "AMD SEV driver not configured"
    fi
    
    # Cleanup
    guestunmount "$test_dir"
    rm -rf "$test_dir"
}

test_drivers 