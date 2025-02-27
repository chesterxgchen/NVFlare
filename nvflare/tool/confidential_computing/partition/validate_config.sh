#!/bin/bash

set -e

# Source configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/config/partition_config.sh"

# Validation functions
validate_device() {
    if [ ! -b "$DEVICE" ]; then
        error "Device $DEVICE does not exist or is not a block device"
    }
    
    # Check if device is already in use
    if mount | grep -q "^$DEVICE"; then
        error "Device $DEVICE is already mounted"
    }
}

validate_mount_points() {
    local total_size=0
    
    for name in "${!PARTITIONS[@]}"; do
        IFS=':' read -r size type mount_point encryption <<< "${PARTITIONS[$name]}"
        
        # Check mount point conflicts
        if mountpoint -q "$mount_point" 2>/dev/null; then
            error "Mount point $mount_point is already in use"
        }
        
        # Validate size format
        if ! [[ $size =~ ^[0-9]+[GMP]$ ]]; then
            error "Invalid size format for $name: $size"
        }
        
        # Calculate total size
        local size_num=${size%[GMP]}
        case "${size: -1}" in
            G) total_size=$((total_size + size_num * 1024 * 1024 * 1024)) ;;
            M) total_size=$((total_size + size_num * 1024 * 1024)) ;;
            P) total_size=$((total_size + size_num * 1024 * 1024 * 1024 * 1024)) ;;
        esac
    }
    
    # Check if total size exceeds device size
    local device_size=$(blockdev --getsize64 "$DEVICE")
    if [ $total_size -gt $device_size ]; then
        error "Total partition size exceeds device size"
    }
}

validate_encryption_config() {
    IFS=':' read -r cipher key_size hash <<< "${CRYPT_CONFIG[0]}"
    
    # Validate cipher
    if ! cryptsetup benchmark "$cipher" >/dev/null 2>&1; then
        error "Invalid or unsupported cipher: $cipher"
    }
    
    # Validate key size
    if ! [[ "$key_size" =~ ^[0-9]+$ ]] || [ "$key_size" -lt 128 ] || [ "$key_size" -gt 1024 ]; then
        error "Invalid key size: $key_size (must be between 128 and 1024)"
    }
    
    # Validate hash
    if ! openssl dgst -"$hash" /dev/null >/dev/null 2>&1; then
        error "Invalid or unsupported hash algorithm: $hash"
    }
}

validate_verity_config() {
    IFS=':' read -r hash_algo data_block hash_block <<< "${VERITY_CONFIG[0]}"
    
    # Validate hash algorithm
    if ! veritysetup --hash-algorithm "$hash_algo" >/dev/null 2>&1; then
        error "Invalid or unsupported verity hash algorithm: $hash_algo"
    }
    
    # Validate block sizes
    for size in "$data_block" "$hash_block"; do
        if ! [[ "$size" =~ ^[0-9]+$ ]] || [ "$size" -lt 512 ] || [ "$size" -gt 65536 ]; then
            error "Invalid block size: $size (must be between 512 and 65536)"
        }
    done
}

validate_partition_order() {
    # Verify root-fs is first
    if [[ ! "${PARTITIONS[root-fs]}" == *"verity"* ]]; then
        error "root-fs must be first partition and type must be verity"
    }
    
    # Verify oem-launcher follows root-fs
    if [[ ! "${PARTITIONS[oem-launcher]}" == *"verity"* ]]; then
        error "oem-launcher must follow root-fs and type must be verity"
    }
}

validate_partition_dependencies() {
    # Check required partitions exist
    local required_parts=("root-fs" "oem-launcher" "os-config" "workspace")
    for part in "${required_parts[@]}"; do
        if [[ ! " ${!PARTITIONS[@]} " =~ " ${part} " ]]; then
            error "Required partition '$part' is missing"
        fi
    done
}

validate_partition_types() {
    for name in "${!PARTITIONS[@]}"; do
        IFS=':' read -r size type mount_point encryption <<< "${PARTITIONS[$name]}"
        
        # Validate partition type
        case "$type" in
            verity|crypt|tmpfs) ;;
            *) error "Invalid partition type '$type' for $name" ;;
        esac
        
        # Validate encryption setting
        case "$encryption" in
            none|required|optional) ;;
            *) error "Invalid encryption setting '$encryption' for $name" ;;
        esac
        
        # Validate specific combinations
        if [[ "$type" == "verity" && "$encryption" != "none" ]]; then
            error "Verity partitions cannot have encryption: $name"
        fi
        
        if [[ "$type" == "tmpfs" && "$encryption" != "none" ]]; then
            error "Tmpfs partitions cannot have encryption: $name"
        fi
    done
}

validate_mount_hierarchy() {
    local prev_mount=""
    for name in "${!PARTITIONS[@]}"; do
        IFS=':' read -r _ _ mount_point _ <<< "${PARTITIONS[$name]}"
        
        # Check mount point is absolute path
        if [[ ! "$mount_point" = /* ]]; then
            error "Mount point must be absolute path: $mount_point"
        fi
        
        # Check parent directory exists in mount points
        local parent_dir=$(dirname "$mount_point")
        if [[ "$parent_dir" != "/" && "$parent_dir" != "$ROOT_MOUNT" ]]; then
            local parent_found=false
            for other_name in "${!PARTITIONS[@]}"; do
                IFS=':' read -r _ _ other_mount _ <<< "${PARTITIONS[$other_name]}"
                if [[ "$other_mount" == "$parent_dir" ]]; then
                    parent_found=true
                    break
                fi
            done
            if ! $parent_found; then
                error "Parent directory $parent_dir not mounted for $mount_point"
            fi
        fi
    done
}

# Main validation
main() {
    log "Validating configuration..."
    
    validate_device
    validate_partition_order
    validate_partition_dependencies
    validate_partition_types
    validate_mount_hierarchy
    validate_mount_points
    validate_encryption_config
    validate_verity_config
    
    log "Configuration validation successful"
}

# Run validation
main "$@" 