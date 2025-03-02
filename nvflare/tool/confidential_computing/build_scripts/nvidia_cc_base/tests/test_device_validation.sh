#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"
source "${SCRIPT_DIR}/test_utils/device_mock.sh"

test_device_validation() {
    # Test case 1: Valid device
    TARGET_DEVICE="/dev/sda"
    if ! check_device; then
        error "Failed to validate valid device"
    fi
    success "Test 1: Valid device check passed"

    # Test case 2: Invalid device
    TARGET_DEVICE="/dev/invalid"
    if check_device 2>/dev/null; then
        error "Failed to catch invalid device"
    fi
    success "Test 2: Invalid device check passed"

    # Test case 3: Empty device (should pass during build)
    TARGET_DEVICE=""
    if ! check_device; then
        error "Failed to handle empty device during build"
    fi
    success "Test 3: Empty device check passed"

    # Test case 4: Device size check
    TARGET_DEVICE="/dev/sdc"
    if check_device_size 2>/dev/null; then
        error "Failed to catch undersized device"
    fi
    success "Test 4: Device size check passed"
}

# Run tests
test_device_validation 