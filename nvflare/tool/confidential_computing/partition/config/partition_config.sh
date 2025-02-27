#!/bin/bash

# Source configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/partition.conf"

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

# Validate configuration values
validate_config() {
    log "Validating configuration..."

    # Validate base paths
    [[ -n "$ROOT_MOUNT" ]] || error "ROOT_MOUNT must be set"
    [[ -n "$DEVICE" ]] || error "DEVICE must be set"

    # Validate partition sizes (must end with G/M/K)
    local size_pattern="^[0-9]+[GMK]$"
    for var in ROOT_FS_SIZE LAUNCHER_SIZE CONFIG_SIZE WORKSPACE_SIZE JOBSTORE_SIZE TMPFS_SIZE; do
        [[ "${!var}" =~ $size_pattern ]] || error "$var must be a number followed by G, M, or K"
    done

    # Validate partition types
    for var in ROOT_FS_TYPE LAUNCHER_TYPE CONFIG_TYPE WORKSPACE_TYPE JOBSTORE_TYPE TMPFS_TYPE; do
        case "${!var}" in
            verity|crypt|tmpfs) ;;
            *) error "$var must be one of: verity, crypt, tmpfs" ;;
        esac
    done

    # Validate mount points
    for var in ROOT_FS_MOUNT LAUNCHER_MOUNT CONFIG_MOUNT WORKSPACE_MOUNT JOBSTORE_MOUNT TMPFS_MOUNT; do
        [[ "${!var}" == /* ]] || error "$var must be an absolute path"
    done

    # Validate encryption settings
    for var in ROOT_FS_ENCRYPTION LAUNCHER_ENCRYPTION CONFIG_ENCRYPTION WORKSPACE_ENCRYPTION JOBSTORE_ENCRYPTION TMPFS_ENCRYPTION; do
        case "${!var}" in
            none|required|optional) ;;
            *) error "$var must be one of: none, required, optional" ;;
        esac
    done

    # Validate crypto settings
    [[ -n "$CRYPT_CIPHER" ]] || error "CRYPT_CIPHER must be set"
    [[ "$CRYPT_KEYSIZE" =~ ^[0-9]+$ ]] || error "CRYPT_KEYSIZE must be a number"
    [[ -n "$CRYPT_HASH" ]] || error "CRYPT_HASH must be set"

    # Validate verity settings
    [[ -n "$VERITY_HASH" ]] || error "VERITY_HASH must be set"
    [[ "$VERITY_DATABLOCK" =~ ^[0-9]+$ ]] || error "VERITY_DATABLOCK must be a number"
    [[ "$VERITY_HASHBLOCK" =~ ^[0-9]+$ ]] || error "VERITY_HASHBLOCK must be a number"

    # Validate tmpfs settings
    [[ "$TMPFS_MODE" =~ ^[0-7]{4}$ ]] || error "TMPFS_MODE must be a 4-digit octal number"
    [[ "$TMPFS_UID" =~ ^[0-9]+$ ]] || error "TMPFS_UID must be a number"
    [[ "$TMPFS_GID" =~ ^[0-9]+$ ]] || error "TMPFS_GID must be a number"

    # Validate system settings
    [[ "$SWAP_ENABLED" =~ ^(true|false)$ ]] || error "SWAP_ENABLED must be true or false"

    log "Configuration validation passed"
}

# Run validation
validate_config

# Verity mount point
VERITY_MOUNT="/mnt/verity" 