#!/usr/bin/env bats

load test_helper

@test "setup verity partition" {
    source "${BATS_TEST_DIRNAME}/../setup_partitions.sh"
    DEVICE="${MOCK_DEVICE}"
    run setup_verity_partition "test-fs" "1G" "/mnt/test" "1"
    [ "$status" -eq 0 ]
}

@test "setup encrypted partition" {
    source "${BATS_TEST_DIRNAME}/../setup_partitions.sh"
    DEVICE="${MOCK_DEVICE}"
    run setup_crypt_partition "test-crypt" "1G" "/mnt/test" "required" "1"
    [ "$status" -eq 0 ]
}

@test "setup tmpfs" {
    source "${BATS_TEST_DIRNAME}/../setup_partitions.sh"
    run setup_tmpfs "test-tmp" "1G" "/mnt/test"
    [ "$status" -eq 0 ]
}

@test "setup partition with invalid size" {
    source "${BATS_TEST_DIRNAME}/../setup_partitions.sh"
    DEVICE="${MOCK_DEVICE}"
    run setup_verity_partition "test-fs" "invalid" "/mnt/test" "1"
    [ "$status" -eq 1 ]
    [[ "${output}" =~ "Invalid size" ]]
}

@test "setup partition with existing mount point" {
    source "${BATS_TEST_DIRNAME}/../setup_partitions.sh"
    mkdir -p /mnt/test
    mount -t tmpfs tmpfs /mnt/test
    DEVICE="${MOCK_DEVICE}"
    run setup_verity_partition "test-fs" "1G" "/mnt/test" "1"
    [ "$status" -eq 1 ]
    [[ "${output}" =~ "already in use" ]]
    umount /mnt/test
}

@test "setup partition with device timeout" {
    source "${BATS_TEST_DIRNAME}/../setup_partitions.sh"
    DEVICE="/nonexistent/device"
    run setup_verity_partition "test-fs" "1G" "/mnt/test" "1"
    [ "$status" -eq 1 ]
    [[ "${output}" =~ "Timeout waiting" ]]
}

@test "generate fstab entries" {
    source "${BATS_TEST_DIRNAME}/../setup_partitions.sh"
    declare -A PARTITIONS=(
        ["root-fs"]="20G:verity:/mnt/root:none"
    )
    run generate_fstab
    [ "$status" -eq 0 ]
    [[ "${output}" =~ "/mnt/root" ]]
} 