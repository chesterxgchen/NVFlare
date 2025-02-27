#!/usr/bin/env bats

load test_helper

@test "cleanup mounted partitions" {
    source "${BATS_TEST_DIRNAME}/../cleanup_partitions.sh"
    declare -A PARTITIONS=(
        ["test-fs"]="1G:verity:/mnt/test:none"
    )
    mock_device_mounted
    run cleanup_mounts
    [ "$status" -eq 0 ]
}

@test "cleanup encrypted partitions" {
    source "${BATS_TEST_DIRNAME}/../cleanup_partitions.sh"
    declare -A PARTITIONS=(
        ["test-crypt"]="1G:crypt:/mnt/test:required"
    )
    ENCRYPT_JOBS=1
    run cleanup_mounts
    [ "$status" -eq 0 ]
} 