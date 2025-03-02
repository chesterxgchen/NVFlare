#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

# Run all tests
run_tests() {
    local tests=(
        "test_01_prepare.sh"         # Test preparation
        "test_02_install_os.sh"      # Test OS installation
        "test_03_cc_setup.sh"        # Test CC setup
        "test_04_drivers.sh"         # Test drivers
        "test_05_attestation.sh"     # Test attestation
        "test_06_partition.sh"       # Test partition setup
        "test_device_selection.sh"   # Test device auto-selection
        "test_device_validation.sh"  # Test device validation
        "test_tee_config.sh"         # Test TEE configuration
        "test_security.sh"           # Test security settings
    )

    local failed=0
    for test in "${tests[@]}"; do
        log "Running $test..."
        if ! "${SCRIPT_DIR}/$test"; then
            log "${RED}$test failed${NC}"
            failed=$((failed + 1))
        else
            success "$test passed"
        fi
    done

    if [ $failed -gt 0 ]; then
        error "$failed tests failed"
    else
        success "All tests passed successfully"
    fi
}

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