#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

# Run all tests in sequence
run_tests() {
    log "Starting tests..."

    # Phase 1: Base Image Tests
    log "Phase 1: Testing Base Image"
    "${SCRIPT_DIR}/test_01_prepare.sh"
    "${SCRIPT_DIR}/test_02_install_os.sh"

    # Phase 2: Device and Driver Tests
    log "Phase 2: Testing Device and Drivers"
    "${SCRIPT_DIR}/test_03_device.sh"      # Consolidated device and driver tests
    "${SCRIPT_DIR}/test_04_keys.sh"        # Consolidated key tests
    "${SCRIPT_DIR}/test_05_cc_apps.sh"     # Test CC apps
    "${SCRIPT_DIR}/test_06_partition.sh"    # Test partitions

    # Remove old test files
    rm -f "${SCRIPT_DIR}/test_device_selection.sh"
    rm -f "${SCRIPT_DIR}/test_device_validation.sh"
    rm -f "${SCRIPT_DIR}/test_driver_keys.sh"
    rm -f "${SCRIPT_DIR}/test_key_lifecycle.sh"
    rm -f "${SCRIPT_DIR}/test_key_management.sh"
    rm -f "${SCRIPT_DIR}/test_tee_keys.sh"
    rm -f "${SCRIPT_DIR}/test_attestation.sh"
    rm -f "${SCRIPT_DIR}/test_03_drivers.sh"
    rm -f "${SCRIPT_DIR}/test_tee_config.sh"

    success "All tests completed successfully!"
}

# Run tests
run_tests

# Main
main() {
    log "Starting NVIDIA CC image tests..."
    run_tests

    # Run individual test suites
    echo "Testing key management..."
    "${SCRIPT_DIR}/test_key_management.sh"
    echo "Testing key lifecycle..."
    "${SCRIPT_DIR}/test_key_lifecycle.sh"
    echo "Testing driver keys..."
    "${SCRIPT_DIR}/test_driver_keys.sh"
    echo "Testing TEE keys..."
    "${SCRIPT_DIR}/test_tee_keys.sh"
    echo "Testing partition setup..."
    "${SCRIPT_DIR}/test_partition.sh"
    echo "Testing CC setup..."
    "${SCRIPT_DIR}/test_cc_setup.sh"
}

main "$@" 