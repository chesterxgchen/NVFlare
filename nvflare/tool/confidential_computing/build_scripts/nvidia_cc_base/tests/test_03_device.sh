#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"
source "${SCRIPT_DIR}/../config/security.conf"
source "${SCRIPT_DIR}/scripts/common/security_hardening.sh"

test_device() {
    local test_dir=$(mktemp -d)
    guestmount -a "$OUTPUT_IMAGE" -i "$test_dir"

    # Test device selection
    test_device_selection() {
        # Test case 1: NVMe device should be preferred
        local devices=("/dev/nvme1n1" "/dev/sda")
        local result=$(AUTO_SELECT=true detect_devices)
        if [[ "$result" != *"/dev/nvme1n1"* ]]; then
            error "Failed to select NVMe device when available"
        fi

        # Test case 2: Larger device should be preferred
        local devices=("/dev/sda" "/dev/sdb")
        local result=$(AUTO_SELECT=true detect_devices)
        if [[ "$result" != *"/dev/sda"* ]]; then
            error "Failed to select larger device"
        fi

        # Test case 3: Should skip mounted devices
        local devices=("/dev/sdb" "/dev/sda")
        local result=$(AUTO_SELECT=true detect_devices)
        if [[ "$result" == *"/dev/sdb"* ]]; then
            error "Selected mounted device"
        fi

        # Test case 4: Should skip devices with OS
        local devices=("/dev/nvme0n1" "/dev/sda")
        local result=$(AUTO_SELECT=true detect_devices)
        if [[ "$result" == *"/dev/nvme0n1"* ]]; then
            error "Selected device with OS"
        fi

        # Test case 5: Should skip devices that are too small
        local devices=("/dev/sdc" "/dev/sda")
        local result=$(AUTO_SELECT=true detect_devices)
        if [[ "$result" == *"/dev/sdc"* ]]; then
            error "Selected device that is too small"
        fi
    }

    # Test device validation
    test_device_validation() {
        # Test case 1: Valid device
        TARGET_DEVICE="/dev/sda"
        if ! check_device; then
            error "Failed to validate valid device"
        fi

        # Test case 2: Invalid device
        TARGET_DEVICE="/dev/invalid"
        if check_device 2>/dev/null; then
            error "Failed to catch invalid device"
        fi

        # Test case 3: Empty device (should pass during build)
        TARGET_DEVICE=""
        if ! check_device; then
            error "Failed to handle empty device during build"
        fi

        # Test case 4: Device size check
        TARGET_DEVICE="/dev/sdc"
        if check_device_size 2>/dev/null; then
            error "Failed to catch undersized device"
        fi

        # Test hardware requirements
        local min_memory=$((16 * 1024 * 1024))  # 16GB
        local system_memory=$(grep MemTotal /proc/meminfo | awk '{print $2}')
        if [ "$system_memory" -lt "$min_memory" ]; then
            error "Insufficient memory"
        fi

        # Test CPU features
        local required_features=(
            "smx"
            "vmx"
            "aes"
            "sha_ni"
        )
        for feature in "${required_features[@]}"; do
            if ! grep -q "^flags.*$feature" /proc/cpuinfo; then
                error "Required CPU feature '$feature' not found"
            fi
        done

        # Test TPM
        if ! command -v tpm2_pcrread >/dev/null 2>&1; then
            error "TPM 2.0 support not found"
        fi
    }

    # Test drivers
    test_drivers() {
        # Test TEE drivers
        if grep -q "AMD" /proc/cpuinfo; then
            if ! chroot "$test_dir" lsmod | grep -q "^sev"; then
                error "AMD SEV driver not loaded"
            fi
            if ! chroot "$test_dir" dpkg -l | grep -q "^ii.*snp-guest-dkms"; then
                error "AMD SEV guest driver not installed"
            fi
        elif grep -q "Intel" /proc/cpuinfo; then
            if ! chroot "$test_dir" lsmod | grep -q "^tdx"; then
                error "Intel TDX driver not loaded"
            fi
            if ! chroot "$test_dir" dpkg -l | grep -q "^ii.*tdx-guest-dkms"; then
                error "Intel TDX guest driver not installed"
            fi
        fi
        
        # Test NVIDIA drivers
        local nvidia_packages=(
            "nvidia-driver-${NVIDIA_DRIVER}"
            "nvidia-utils-${NVIDIA_DRIVER}"
            "cuda-${NVIDIA_CUDA}"
        )
        for pkg in "${nvidia_packages[@]}"; do
            if ! chroot "$test_dir" dpkg -l | grep -q "^ii.*$pkg"; then
                error "Required NVIDIA package '$pkg' not installed"
            fi
        done
    }

    # Run all tests
    test_device_selection
    test_device_validation
    test_drivers

    # Cleanup
    guestunmount "$test_dir"
    rm -rf "$test_dir"
}

# Run tests
test_device 