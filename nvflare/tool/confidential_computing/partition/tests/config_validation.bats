#!/usr/bin/env bats

load test_helper

@test "validate device exists" {
    source "${BATS_TEST_DIRNAME}/../config/partition_config.sh"
    DEVICE="${MOCK_DEVICE}"
    run validate_device
    [ "$status" -eq 0 ]
}

@test "validate device does not exist" {
    source "${BATS_TEST_DIRNAME}/../config/partition_config.sh"
    DEVICE="/nonexistent/device"
    run validate_device
    [ "$status" -eq 1 ]
    [[ "${output}" =~ "does not exist" ]]
}

@test "validate partition order" {
    source "${BATS_TEST_DIRNAME}/../config/partition_config.sh"
    declare -A PARTITIONS=(
        ["root-fs"]="20G:verity:/mnt/root:none"
        ["oem-launcher"]="1G:verity:/mnt/launcher:none"
    )
    run validate_partition_order
    [ "$status" -eq 0 ]
}

@test "validate missing required partition" {
    source "${BATS_TEST_DIRNAME}/../config/partition_config.sh"
    declare -A PARTITIONS=(
        ["root-fs"]="20G:verity:/mnt/root:none"
    )
    run validate_partition_dependencies
    [ "$status" -eq 1 ]
    [[ "${output}" =~ "oem-launcher" ]]
}

@test "validate base paths" {
    source "${BATS_TEST_DIRNAME}/../config/partition_config.sh"
    ROOT_MOUNT=""
    run validate_config
    [ "$status" -eq 1 ]
    [[ "${output}" =~ "ROOT_MOUNT must be set" ]]
}

@test "validate partition sizes" {
    source "${BATS_TEST_DIRNAME}/../config/partition_config.sh"
    ROOT_FS_SIZE="invalid"
    run validate_config
    [ "$status" -eq 1 ]
    [[ "${output}" =~ "must be a number followed by G, M, or K" ]]
}

@test "validate partition types" {
    source "${BATS_TEST_DIRNAME}/../config/partition_config.sh"
    ROOT_FS_TYPE="invalid"
    run validate_config
    [ "$status" -eq 1 ]
    [[ "${output}" =~ "must be one of: verity, crypt, tmpfs" ]]
}

@test "validate mount points" {
    source "${BATS_TEST_DIRNAME}/../config/partition_config.sh"
    ROOT_FS_MOUNT="relative/path"
    run validate_config
    [ "$status" -eq 1 ]
    [[ "${output}" =~ "must be an absolute path" ]]
}

@test "validate encryption settings" {
    source "${BATS_TEST_DIRNAME}/../config/partition_config.sh"
    ROOT_FS_ENCRYPTION="invalid"
    run validate_config
    [ "$status" -eq 1 ]
    [[ "${output}" =~ "must be one of: none, required, optional" ]]
}

@test "validate crypto settings" {
    source "${BATS_TEST_DIRNAME}/../config/partition_config.sh"
    CRYPT_KEYSIZE="invalid"
    run validate_config
    [ "$status" -eq 1 ]
    [[ "${output}" =~ "CRYPT_KEYSIZE must be a number" ]]
}

@test "validate verity settings" {
    source "${BATS_TEST_DIRNAME}/../config/partition_config.sh"
    VERITY_DATABLOCK="invalid"
    run validate_config
    [ "$status" -eq 1 ]
    [[ "${output}" =~ "VERITY_DATABLOCK must be a number" ]]
}

@test "validate tmpfs settings" {
    source "${BATS_TEST_DIRNAME}/../config/partition_config.sh"
    TMPFS_MODE="999999"
    run validate_config
    [ "$status" -eq 1 ]
    [[ "${output}" =~ "TMPFS_MODE must be a 4-digit octal number" ]]
}

@test "validate valid configuration" {
    source "${BATS_TEST_DIRNAME}/../config/partition_config.sh"
    run validate_config
    [ "$status" -eq 0 ]
    [[ "${output}" =~ "Configuration validation passed" ]]
} 