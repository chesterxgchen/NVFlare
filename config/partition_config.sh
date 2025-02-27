#!/bin/bash

# Base paths
ROOT_MOUNT="/mnt/flare"
VERITY_MOUNT="/mnt/verity"

# Partition configurations
CONFIG_PARTITIONS=(
    # format: "name:type:size:mount_point:encryption"
    "root-fs:verity:20G:/mnt/flare/root:none"
    "oem-launcher:verity:1G:/mnt/flare/launcher:none"
    "os-config:verity:5G:/mnt/flare/config:none"
    "workspace:crypt:50G:/mnt/flare/workspace:required"
    "job-store:crypt:100G:/mnt/flare/jobs:optional"
    "tmp-fs:tmpfs:8G:/mnt/flare/tmp:none"
)

# Encryption settings
CRYPT_CIPHER="aes-xts-plain64"
CRYPT_KEY_SIZE="512"
CRYPT_HASH="sha256"

# Verity settings
VERITY_HASH_ALGORITHM="sha256"
VERITY_DATA_BLOCK_SIZE="4096"
VERITY_HASH_BLOCK_SIZE="4096"

# Temp filesystem settings
TMPFS_MODE="1777"
TMPFS_UID="0"
TMPFS_GID="0" 