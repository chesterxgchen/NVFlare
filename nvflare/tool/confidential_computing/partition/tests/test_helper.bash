#!/usr/bin/env bash

# Setup test environment
setup() {
    # Create temp directory for test files
    export TEST_DIR="$(mktemp -d)"
    export MOCK_DEVICE="${TEST_DIR}/mock_device"
    
    # Create mock block device file
    dd if=/dev/zero of="${MOCK_DEVICE}" bs=1M count=1024
    
    # Mock commands
    export PATH="${BATS_TEST_DIRNAME}/mocks:$PATH"

    # Mock confidential VM environment
    echo "SEV-SNP enabled" > "${TEST_DIR}/dmesg"
    export MOCK_DMESG_FILE="${TEST_DIR}/dmesg"
}

# Cleanup after tests
teardown() {
    rm -rf "${TEST_DIR}"
}

# Mock functions
mock_dmesg() {
    cat "${MOCK_DMESG_FILE}"
}

mock_device_mounted() {
    echo "${MOCK_DEVICE} /mnt/test ext4 rw 0 0" > /proc/mounts
}

mock_device_unmounted() {
    sed -i "\|${MOCK_DEVICE}|d" /proc/mounts
} 