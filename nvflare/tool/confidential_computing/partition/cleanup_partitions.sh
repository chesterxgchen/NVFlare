#!/bin/bash

set -e  # Exit on error

# Source configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/config/partition_config.sh"

# Logging
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

error() {
    log "ERROR: $1" >&2
    exit 1
}

# Check required kernel modules
check_kernel_modules() {
    log "Checking required kernel modules..."
    
    local required_modules=(
        "dm_crypt"
        "dm_verity"
        "aes"
        "sha256"
        "xts"
    )
    
    for module in "${required_modules[@]}"; do
        if ! lsmod | grep -q "^${module}"; then
            error "Required kernel module not loaded: $module"
        fi
    done
}

# Check requirements
check_requirements() {
    log "Checking system requirements..."

    # Check kernel modules are still loaded
    check_kernel_modules

    # Check required commands
    for cmd in cryptsetup dmsetup umount; do
        command -v $cmd >/dev/null 2>&1 || error "$cmd is required but not installed."
    done

    log "System requirements check passed"
}

# Function to cleanup mounts
cleanup_mounts() {
    log "Starting cleanup..."
    
    # Unmount all partitions in reverse order
    for name in "${!PARTITIONS[@]}"; do
        IFS=':' read -r size type mount_point encryption <<< "${PARTITIONS[$name]}"
        
        log "Cleaning up: $name ($type)"
        
        if mountpoint -q "$mount_point" 2>/dev/null; then
            umount "$mount_point" || error "Failed to unmount $mount_point"
        fi
        
        case $type in
            "verity")
                if veritysetup status "${name}_verity" >/dev/null 2>&1; then
                    veritysetup close "${name}_verity" || error "Failed to close verity device for $name"
                fi
                ;;
            "crypt")
                if [ "$encryption" = "required" ] || [ "$encryption" = "optional" -a -n "$ENCRYPT_JOBS" ]; then
                    if cryptsetup status "${name}_crypt" >/dev/null 2>&1; then
                        cryptsetup close "${name}_crypt" || error "Failed to close encrypted device for $name"
                    fi
                fi
                ;;
        esac
    done
    
    log "Cleanup completed successfully"
}

# Run cleanup
check_requirements
cleanup_mounts 