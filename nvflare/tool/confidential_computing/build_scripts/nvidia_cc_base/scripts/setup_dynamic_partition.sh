#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"
source "${SCRIPT_DIR}/../config/partition.conf"
source "${SCRIPT_DIR}/keys/internal/key_settings.conf"

setup_dynamic_partition() {
    local device="$1"
    local mount_point="${DYNAMIC_PARTITION[mount]}"
    local keyfile="${DYNAMIC_PARTITION[keyfile]}"
    local fallback="${DYNAMIC_PARTITION[fallback]}"
    
    log "Setting up dynamic partition on ${device}"
    
    # Check if key file exists
    if [ -f "$keyfile" ]; then
        log "Key file found, setting up encrypted partition"
        
        # Set up LUKS encryption
        cryptsetup luksFormat \
            --type luks2 \
            --cipher "${LUKS_CIPHER}" \
            --key-size "${LUKS_KEY_SIZE}" \
            --hash "${KEY_HASH}" \
            "$device"
            
        # Open encrypted partition
        local mapper_name="dynamic_crypt"
        cryptsetup luksOpen \
            --key-file "$keyfile" \
            "$device" \
            "$mapper_name"
            
        # Create filesystem
        mkfs.ext4 "/dev/mapper/$mapper_name"
        
        # Add to crypttab
        echo "dynamic_crypt $device $keyfile luks" >> /etc/crypttab
        
        # Add to fstab
        echo "/dev/mapper/$mapper_name $mount_point ext4 defaults,noatime 0 0" >> /etc/fstab
        
    else
        log "No key file found, using unencrypted partition"
        if [ "$fallback" = "error" ]; then
            error "Key file not found and fallback=error"
        fi
        
        # Create filesystem directly
        mkfs.ext4 "$device"
        
        # Add to fstab
        echo "$device $mount_point ext4 defaults,noatime 0 0" >> /etc/fstab
    fi
    
    # Create mount point with proper permissions
    mkdir -p "$mount_point"
    chown "${DYNAMIC_PARTITION[owner]}" "$mount_point"
    chmod "${DYNAMIC_PARTITION[mode]}" "$mount_point"
    
    success "Dynamic partition setup complete"
}

# Mount for immediate use
mount_dynamic_partition() {
    mount "${DYNAMIC_PARTITION[mount]}"
} 