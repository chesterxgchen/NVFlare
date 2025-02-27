#!/usr/bin/env bats

load test_helper

@test "validate root requirement" {
    source "${BATS_TEST_DIRNAME}/../install.sh"
    EUID=1000
    run validate_install_env
    [ "$status" -eq 1 ]
    [[ "${output}" =~ "Please run as root" ]]
}

@test "validate required commands" {
    source "${BATS_TEST_DIRNAME}/../install.sh"
    PATH=""
    run validate_install_env
    [ "$status" -eq 1 ]
    [[ "${output}" =~ "is required but not installed" ]]
}

@test "validate confidential VM requirement" {
    source "${BATS_TEST_DIRNAME}/../install.sh"
    echo "Regular VM" > "${TEST_DIR}/dmesg"
    run validate_install_env
    [ "$status" -eq 1 ]
    [[ "${output}" =~ "Not running in a Confidential VM" ]]
}

@test "validate directory permissions" {
    source "${BATS_TEST_DIRNAME}/../install.sh"
    mkdir -p "${TEST_DIR}/readonly"
    chmod 555 "${TEST_DIR}/readonly"
    run validate_install_env
    [ "$status" -eq 1 ]
    [[ "${output}" =~ "exists but is not writable" ]]
}

@test "validate successful environment check" {
    source "${BATS_TEST_DIRNAME}/../install.sh"
    EUID=0
    run validate_install_env
    [ "$status" -eq 0 ]
    [[ "${output}" =~ "Installation environment validation passed" ]]
} 