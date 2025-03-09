#!/bin/bash



# Directory handlers
validate_dir() {
    local mount_point="$1"
    verify_dir_signature "$mount_point" || return 1
    verify_dir_manifest "$mount_point" || return 1
    return 0
}

copy_dir() {
    local mount_point="$1"
    local target_dir="$2"
    cp -r "$mount_point"/* "$target_dir"/ || return 1
    return 0
}

verify_dir() {
    local mount_point="$1"
    verify_dir_contents "$mount_point" || return 1
    return 0
} 