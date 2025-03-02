#!/bin/bash

set -e

# Source configs
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../config/partition.conf"
source "${SCRIPT_DIR}/../config/security.conf"
source "${SCRIPT_DIR}/common.sh"
source "${SCRIPT_DIR}/lib/key_management.sh"
source "${SCRIPT_DIR}/lib/key_service.sh"

# Setup boot partition first
mkfs.ext4 "${DEVICE}p1"
mount "${DEVICE}p1" "/mnt/boot"

# Copy and source TEE config
mkdir -p "/mnt/boot/cc"
cp "${SCRIPT_DIR}/../config/tee.conf" "/mnt/boot/cc/tee.conf"
source "/mnt/boot/cc/tee.conf"

# Setup LUKS on root partition
cryptsetup luksFormat \
    --type luks2 \
    --cipher "$LUKS_CIPHER" \
    --key-size "$LUKS_KEY_SIZE" \
    --hash "$LUKS_HASH" \
    "${DEVICE}p2"  # Now p2 is root

# Open and format root partition
cryptsetup open "${DEVICE}p2" root_crypt
mkfs.${ROOT_FS} /dev/mapper/root_crypt
mount /dev/mapper/root_crypt "$ROOT_MOUNT"

# Setup LUKS on app partition
cryptsetup luksFormat \
    --type luks2 \
    --cipher "$LUKS_CIPHER" \
    --key-size "$LUKS_KEY_SIZE" \
    --hash "$LUKS_HASH" \
    "${DEVICE}p3"

# Open and format app partition
cryptsetup open "${DEVICE}p3" app_crypt
mkfs.${ROOT_FS} /dev/mapper/app_crypt
mount /dev/mapper/app_crypt "$APP_MOUNT"

# Format read-only partition (prepared for dm-verity)
mkfs.${ROOT_FS} "${DEVICE}p4"
mount "${DEVICE}p4" "$RO_MOUNT"

# Format dynamic partition
mkfs.${ROOT_FS} "${DEVICE}p5"
mount "${DEVICE}p5" "$DYNAMIC_MOUNT"

# Initial TEE setup using template values
mkdir -p "$TEE_MEMORY_PATH"
mount -t tmpfs -o size="$TEE_MEMORY_SIZE" tmpfs "$TEE_MEMORY_PATH"
chown "$TEE_MEMORY_OWNER:$TEE_MEMORY_GROUP" "$TEE_MEMORY_PATH"
chmod "$TEE_MEMORY_MODE" "$TEE_MEMORY_PATH"

# Generate crypttab entries
cat > "$ROOT_MOUNT/etc/crypttab" <<EOF
root_crypt UUID=$(blkid -s UUID -o value "${DEVICE}p2") none luks
app_crypt UUID=$(blkid -s UUID -o value "${DEVICE}p3") none luks
EOF

# Generate fstab entries
cat > "$ROOT_MOUNT/etc/fstab" <<EOF
UUID=$(blkid -s UUID -o value ${DEVICE}p1) /boot ext4 defaults 0 2
/dev/mapper/root_crypt / ${ROOT_FS} defaults 0 1
/dev/mapper/app_crypt $APP_MOUNT ${ROOT_FS} defaults 0 2
/dev/disk/by-uuid/$(blkid -s UUID -o value "${DEVICE}p4") $RO_MOUNT ${ROOT_FS} ro 0 2
/dev/disk/by-uuid/$(blkid -s UUID -o value "${DEVICE}p5") $DYNAMIC_MOUNT ${ROOT_FS} defaults 0 2
tmpfs $TEE_MEMORY_PATH tmpfs size=$TEE_MEMORY_SIZE 0 0
EOF

# Setup dm-verity on data partition
veritysetup format \
    "${DEVICE}p4" \
    "${DEVICE}p4.verity" \
    --hash="$VERITY_HASH" \
    --salt-size="$VERITY_SALT_SIZE" \
    --data-block-size="$VERITY_BLOCK_SIZE"

# Remove duplicate tmpfs mount
rm -f "$TMP_MOUNT"

# Setup CC application directories with proper permissions
setup_cc_app_dirs() {
    local root_mount="$1"
    
    log "Setting up CC application directories"
    
    # Create and set permissions for each CC app directory
    for dir_spec in "${CC_APP_DIRS[@]}"; do
        IFS=':' read -r dir owner perms <<< "$dir_spec"
        
        local full_path="${root_mount}${dir}"
        mkdir -p "$full_path"
        chown "$owner" "$full_path"
        chmod "$perms" "$full_path"
        
        log "Created $dir ($perms) owned by $owner"
    done
}

# Calculate partition sizes based on available space
calculate_partition_sizes() {
    local device="$1"
    local total_size=$(blockdev --getsize64 "$device")
    local total_mb=$((total_size / 1024 / 1024))
    
    # Reserve space for fixed partitions
    local fixed_mb=$((512 + 256))  # p1(512M) + p2(256M)
    local available_mb=$((total_mb - fixed_mb))
    
    log "Total device size: ${total_mb}MB"
    log "Available after fixed partitions: ${available_mb}MB"
    
    # Calculate sizes based on weights and constraints
    declare -A partition_sizes
    local total_weight=0
    local remaining_mb=$available_mb
    
    # First pass: Allocate minimum sizes
    for resize in "${PARTITION_RESIZE[@]}"; do
        IFS=':' read -r part min max weight <<< "$resize"
        # Convert min size from G to MB
        local min_mb=$((${min%G} * 1024))
        remaining_mb=$((remaining_mb - min_mb))
        partition_sizes[$part]=$min_mb
        total_weight=$((total_weight + weight))
    done
    
    # Second pass: Distribute remaining space by weight
    if [ $remaining_mb -gt 0 ]; then
        for resize in "${PARTITION_RESIZE[@]}"; do
            IFS=':' read -r part min max weight <<< "$resize"
            
            # Calculate weighted share
            local share_mb=$(( (remaining_mb * weight) / total_weight ))
            
            # Handle percentage max if specified
            if [[ "$max" == *"%" ]]; then
                local max_percent=${max%\%}
                local max_mb=$(( (available_mb * max_percent) / 100 ))
                local current_mb=${partition_sizes[$part]}
                
                # Don't exceed max percentage
                if [ $((current_mb + share_mb)) -gt $max_mb ]; then
                    share_mb=$((max_mb - current_mb))
                fi
            fi
            
            # Update partition size
            partition_sizes[$part]=$((${partition_sizes[$part]} + share_mb))
            log "Partition $part size: ${partition_sizes[$part]}MB"
        done
    fi
    
    # Export sizes for partition creation
    declare -g -A CALCULATED_SIZES=()
    for part in "${!partition_sizes[@]}"; do
        CALCULATED_SIZES[$part]="${partition_sizes[$part]}M"
    done
}

# Setup partitions
setup_partitions() {
    local device="$1"
    log "Setting up partitions on ${device}"
    
    # Initialize GPT partition table
    parted -s "$device" mklabel gpt
    
    # Calculate optimal partition sizes
    calculate_partition_sizes "$device"
    
    # Create partitions
    local start_mb=1
    for part in "${PARTITIONS[@]}"; do
        IFS=':' read -r name size fs mount opts resize <<< "$part"
        
        # Determine partition size
        local part_size
        if [[ "$size" == "*" ]]; then
            part_size="100%"
        elif [[ "$size" == *"+"* ]]; then
            part_size="${CALCULATED_SIZES[${name}]}"
        else
            part_size="$size"
        fi
        
        # Create partition
        log "Creating partition ${name} with size ${part_size}"
        if [[ "$part_size" == "100%" ]]; then
            parted -s "$device" mkpart primary ${fs} ${start_mb}MiB 100%
        else
            local end_mb=$((start_mb + ${part_size%M}))
            parted -s "$device" mkpart primary ${fs} ${start_mb}MiB ${end_mb}MiB
            start_mb=$end_mb
        fi
        
        # Format partition
        case "$name" in
            "p1")  # Boot partition (dm-verity protected)
                mkfs.${fs} "${device}${name}"
                # Setup dm-verity for boot partition
                veritysetup format \
                    "${device}${name}" \
                    "${device}${name}.verity" \
                    --hash="$VERITY_HASH" \
                    --salt-size="$VERITY_SALT_SIZE" \
                    --data-block-size="$VERITY_BLOCK_SIZE"
            "p2")  # Host-CC partition (unencrypted)
                mkfs.${fs} "${device}${name}"
            "p3"|"p4")  # Root and CC-Apps partitions (encrypted)
                setup_encrypted_partition "${device}${name}" "${name%p*}_crypt"
                ;;
            "p5")       # Dynamic partition (configurable encryption)
                if [ -f "${DYNAMIC_PARTITION[keyfile]}" ]; then
                    setup_dynamic_partition "${device}${name}"
                else
                    mkfs.${fs} "${device}${name}"
                fi
                ;;
        esac
        
        # Handle resizable partitions
        if [[ "$resize" == "resize" ]]; then
            resize2fs "${device}${name}"
        fi
    done
    
    # Mount partitions and setup directories
    mount_partitions "$device"
    setup_cc_app_dirs "$ROOT_MOUNT"
    
    success "Partition setup complete"
}

# Setup encrypted partition
setup_encrypted_partition() {
    local device="$1"
    local mapper_name="$2"
    local partition="$3"
    
    # Get partition key from key service
    local part_key=$(get_key "${partition}_key")
    if [ -z "$part_key" ]; then
        generate_key "${partition}_key" "partition"
        part_key=$(get_key "${partition}_key")
    fi
    
    # Setup LUKS with partition key
    cryptsetup luksFormat \
        --type luks2 \
        --cipher "${LUKS_CIPHER}" \
        --key-size "${LUKS_KEY_SIZE}" \
        --key-file <(echo -n "$part_key") \
        "$device"
}

# Mount all partitions
mount_partitions() {
    local device="$1"
    
    # Mount root first
    mount /dev/mapper/root_crypt "$ROOT_MOUNT"
    
    # Mount other partitions
    for part in "${PARTITIONS[@]}"; do
        IFS=':' read -r name size fs mount opts resize <<< "$part"
        [ "$mount" = "/" ] && continue  # Skip root, already mounted
        
        mkdir -p "${ROOT_MOUNT}${mount}"
        if [[ "$name" = "p3" || "$name" = "p4" ]]; then
            mount "/dev/mapper/${name%p*}_crypt" "${ROOT_MOUNT}${mount}"
        else
            mount "${device}${name}" "${ROOT_MOUNT}${mount}"
        fi
    done
}

# Run partition setup
setup_partitions "$DEVICE" 