#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"
source "${SCRIPT_DIR}/test_utils/device_mock.sh"

test_device_auto_selection() {
    # Test case 1: NVMe device should be preferred
    local devices=("/dev/nvme1n1" "/dev/sda")
    local result=$(AUTO_SELECT=true detect_devices)
    if [[ "$result" != *"/dev/nvme1n1"* ]]; then
        error "Failed to select NVMe device when available"
    fi
    success "Test 1: NVMe preference passed"

    # Test case 2: Larger device should be preferred
    local devices=("/dev/sda" "/dev/sdb")
    local result=$(AUTO_SELECT=true detect_devices)
    if [[ "$result" != *"/dev/sda"* ]]; then
        error "Failed to select larger device"
    fi
    success "Test 2: Size preference passed"

    # Test case 3: Should skip mounted devices
    local devices=("/dev/sdb" "/dev/sda")
    local result=$(AUTO_SELECT=true detect_devices)
    if [[ "$result" == *"/dev/sdb"* ]]; then
        error "Selected mounted device"
    fi
    success "Test 3: Mount check passed"

    # Test case 4: Should skip devices with OS
    local devices=("/dev/nvme0n1" "/dev/sda")
    local result=$(AUTO_SELECT=true detect_devices)
    if [[ "$result" == *"/dev/nvme0n1"* ]]; then
        error "Selected device with OS"
    fi
    success "Test 4: OS check passed"

    # Test case 5: Should skip devices that are too small
    local devices=("/dev/sdc" "/dev/sda")
    local result=$(AUTO_SELECT=true detect_devices)
    if [[ "$result" == *"/dev/sdc"* ]]; then
        error "Selected device that is too small"
    fi
    success "Test 5: Size requirement passed"
}

# Run tests
test_device_auto_selection 