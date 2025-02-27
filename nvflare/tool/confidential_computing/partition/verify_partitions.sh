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

# Verify verity partition
verify_verity_partition() {
    local name=$1 mount_point=$2
    
    log "Verifying verity partition: $name"
    
    # Check if mounted
    if ! mountpoint -q "$mount_point"; then
        error "Partition $name not mounted at $mount_point"
    fi
    
    # Verify verity device
    if ! veritysetup status "${name}_verity" >/dev/null 2>&1; then
        error "Verity device for $name not active"
    fi
    
    # Verify hash tree
    if ! veritysetup verify /dev/mapper/${name}_verity; then
        error "Verity hash verification failed for $name"
    }
    
    log "Verity partition $name verified successfully"
}

# Verify encrypted partition
verify_crypt_partition() {
    local name=$1 mount_point=$2 encryption=$3
    
    log "Verifying encrypted partition: $name"
    
    # Check if mounted
    if ! mountpoint -q "$mount_point"; then
        error "Partition $name not mounted at $mount_point"
    fi
    
    if [ "$encryption" = "required" ] || [ "$encryption" = "optional" -a -n "$ENCRYPT_JOBS" ]; then
        # Verify LUKS device
        if ! cryptsetup status "${name}_crypt" >/dev/null 2>&1; then
            error "LUKS device for $name not active"
        fi
        
        # Verify encryption
        if ! cryptsetup luksDump /dev/mapper/${name}_crypt >/dev/null 2>&1; then
            error "LUKS verification failed for $name"
        }
    fi
    
    log "Encrypted partition $name verified successfully"
}

# Main verification
main() {
    log "Starting partition verification..."
    
    for name in "${!PARTITIONS[@]}"; do
        IFS=':' read -r size type mount_point encryption <<< "${PARTITIONS[$name]}"
        
        case $type in
            "verity")
                verify_verity_partition "$name" "$mount_point"
                ;;
            "crypt")
                verify_crypt_partition "$name" "$mount_point" "$encryption"
                ;;
            "tmpfs")
                if ! mountpoint -q "$mount_point"; then
                    error "Tmpfs $name not mounted at $mount_point"
                fi
                ;;
        esac
    done
    
    log "All partitions verified successfully"
}

# Run verification
main "$@" 