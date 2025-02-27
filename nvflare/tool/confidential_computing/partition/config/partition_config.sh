#!/bin/bash

# Source configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/partition.conf"

# Validate configuration
validate_config() {
    # Check required variables
    [ -z "$ROOT_MOUNT" ] && error "ROOT_MOUNT must be set"
    [ -z "$DEVICE" ] && error "DEVICE must be set"
    
    # Validate paths
    [[ "$ROOT_MOUNT" =~ ^/ ]] || error "ROOT_MOUNT must be absolute path"
    [[ "$DEVICE" =~ ^/dev/ ]] || error "DEVICE must be a device path"
    
    # Validate sizes
    [[ "$ROOT_FS_SIZE" =~ ^[0-9]+[MG]$ ]] || error "Invalid ROOT_FS_SIZE format"
    [[ "$WORKSPACE_SIZE" =~ ^[0-9]+[MG]$ ]] || error "Invalid WORKSPACE_SIZE format"
    [[ "$JOBSTORE_SIZE" =~ ^[0-9]+[MG]$ ]] || error "Invalid JOBSTORE_SIZE format"
    [[ "$TMPFS_SIZE" =~ ^[0-9]+[MG]$ ]] || error "Invalid TMPFS_SIZE format"
    
    # Validate types
    local valid_types=("verity" "crypt" "tmpfs")
    [[ " ${valid_types[@]} " =~ " $ROOT_FS_TYPE " ]] || error "Invalid ROOT_FS_TYPE"
    [[ " ${valid_types[@]} " =~ " $WORKSPACE_TYPE " ]] || error "Invalid WORKSPACE_TYPE"
    [[ " ${valid_types[@]} " =~ " $JOBSTORE_TYPE " ]] || error "Invalid JOBSTORE_TYPE"
    [[ " ${valid_types[@]} " =~ " $TMPFS_TYPE " ]] || error "Invalid TMPFS_TYPE"
    
    # Validate encryption modes
    local valid_modes=("required" "optional" "none")
    [[ " ${valid_modes[@]} " =~ " $ROOT_FS_ENCRYPTION " ]] || error "Invalid ROOT_FS_ENCRYPTION"
    [[ " ${valid_modes[@]} " =~ " $WORKSPACE_ENCRYPTION " ]] || error "Invalid WORKSPACE_ENCRYPTION"
    [[ " ${valid_modes[@]} " =~ " $JOBSTORE_ENCRYPTION " ]] || error "Invalid JOBSTORE_ENCRYPTION"
    [[ " ${valid_modes[@]} " =~ " $TMPFS_ENCRYPTION " ]] || error "Invalid TMPFS_ENCRYPTION"
}

# Validate configuration
validate_config

# Allow environment overrides
ROOT_MOUNT="${NVFLARE_ROOT:-$ROOT_MOUNT}"
DEVICE="${NVFLARE_DEVICE:-$DEVICE}"

# Build partition array
declare -A PARTITIONS=(
    ["root-fs"]="${ROOT_FS_SIZE}:${ROOT_FS_TYPE}:${ROOT_FS_MOUNT}:${ROOT_FS_ENCRYPTION}"
    ["oem-launcher"]="${LAUNCHER_SIZE}:${LAUNCHER_TYPE}:${LAUNCHER_MOUNT}:${LAUNCHER_ENCRYPTION}"
    ["os-config"]="${CONFIG_SIZE}:${CONFIG_TYPE}:${CONFIG_MOUNT}:${CONFIG_ENCRYPTION}"
    ["workspace"]="${WORKSPACE_SIZE}:${WORKSPACE_TYPE}:${WORKSPACE_MOUNT}:${WORKSPACE_ENCRYPTION}"
    ["job-store"]="${JOBSTORE_SIZE}:${JOBSTORE_TYPE}:${JOBSTORE_MOUNT}:${JOBSTORE_ENCRYPTION}"
    ["tmp-fs"]="${TMPFS_SIZE}:${TMPFS_TYPE}:${TMPFS_MOUNT}:${TMPFS_ENCRYPTION}"
)

# Build other configs
CRYPT_CONFIG=("${CRYPT_CIPHER}:${CRYPT_KEYSIZE}:${CRYPT_HASH}")
VERITY_CONFIG=("${VERITY_HASH}:${VERITY_DATABLOCK}:${VERITY_HASHBLOCK}")
TMPFS_CONFIG=("${TMPFS_MODE}:${TMPFS_UID}:${TMPFS_GID}")

# Logging
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

error() {
    log "ERROR: $1" >&2
    exit 1
}

# Run validation
validate_config

# Verity mount point
VERITY_MOUNT="/mnt/verity" 