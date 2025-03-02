#!/bin/bash

set -e

# Source configs
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../config/partition.conf"
source "${SCRIPT_DIR}/../config/security.conf"
source "${SCRIPT_DIR}/common/security_hardening.sh"
source "${SCRIPT_DIR}/keys/key_management.sh"
source "${SCRIPT_DIR}/keys/key_service.sh"

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
                setup_crypt_partition "${name%p*}" "${part_size}" "${ROOT_MOUNT}${mount}" "${encryption}" "${name#p*}"
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

# Error handling
handle_error() {
    local func="$1"
    local cmd="$2"
    local ret="$3"
    error "Failed in ${func} executing '${cmd}': exit code ${ret}"
    cleanup_partitions
    exit 1
}

# Verification helpers
verify_luks_device() {
    local device="$1"
    local name="$2"
    
    # Verify LUKS header
    if ! cryptsetup isLuks "$device"; then
        handle_error "verify_luks_device" "cryptsetup isLuks" 1
    fi
    
    # Verify cipher and key size
    local header_info=$(cryptsetup luksDump "$device")
    if ! echo "$header_info" | grep -q "cipher: ${LUKS_CIPHER}"; then
        handle_error "verify_luks_device" "cipher verification" 1
    fi
}

verify_verity_device() {
    local device="$1"
    local hash_dev="$2"
    local root_hash="$3"
    
    # Verify verity setup
    if ! veritysetup verify "$device" "$hash_dev" "$root_hash"; then
        handle_error "verify_verity_device" "veritysetup verify" 1
    fi
}

# Setup LUKS encrypted partition
setup_crypt_partition() {
    local name="$1"
    local size="$2"
    local mount_point="$3"
    local encryption="$4"
    local part_num="$5"

    # Get hardware-bound key
    local hw_key=$(get_tee_key "hw_key")
    [ -z "$hw_key" ] && handle_error "setup_crypt_partition" "get_tee_key" 1
    
    # Create and format LUKS partition
    cryptsetup luksFormat --type luks2 \
        --cipher "${LUKS_CIPHER}" \
        --key-size "${LUKS_KEY_SIZE}" \
        --hash "${KEY_HASH}" \
        "${DEVICE}p${part_num}" \
        <(echo -n "$hw_key") || handle_error "setup_crypt_partition" "luksFormat" $?
        
    # Verify LUKS setup
    verify_luks_device "${DEVICE}p${part_num}" "${name}_crypt"
    
    # Open LUKS device
    cryptsetup open "${DEVICE}p${part_num}" "${name}_crypt" \
        --key-file <(echo -n "$hw_key") || handle_error "setup_crypt_partition" "open" $?
        
    # Create filesystem
    mkfs.ext4 "/dev/mapper/${name}_crypt" || handle_error "setup_crypt_partition" "mkfs.ext4" $?

    # Verify filesystem
    fsck.ext4 -n "/dev/mapper/${name}_crypt" || handle_error "setup_crypt_partition" "fsck.ext4" $?
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

# Setup verity for boot partition (p2)
setup_verity_partition() {
    local name="$1"
    local size="$2"
    local mount_point="$3"
    local part_num="$4"

    # Create data and hash partitions
    parted -s "$DEVICE" mkpart primary ext4 "$start" "$end"
    mkfs.ext4 -O metadata_csum,64bit "${DEVICE}p${part_num}" || \
        handle_error "setup_verity_partition" "mkfs.ext4" $?
    
    # Calculate hash
    veritysetup format \
        --hash="${VERITY_HASH_ALGORITHM}" \
        --data-block-size="${VERITY_DATA_BLOCK_SIZE}" \
        --hash-block-size="${VERITY_HASH_BLOCK_SIZE}" \
        "${DEVICE}p${part_num}" "${DEVICE}p${part_num}_hash"
    
    # Store hash for boot
    veritysetup create "${name}_verity" \
        "${DEVICE}p${part_num}" \
        "${DEVICE}p${part_num}_hash" \
        "$root_hash" \
        --options="${VERITY_OPTS}"

    # Verify setup
    verify_verity_device "${DEVICE}p${part_num}" "${DEVICE}p${part_num}_hash" "$root_hash"
}

# Setup root partition (p3) with verity
setup_root_verity() {
    # Similar to above but with root partition specifics
}

# Setup dynamic partition with optional encryption
setup_dynamic_partition() {
    local name="$1"
    local size="$2"
    local mount_point="$3"
    local encryption="$4"
    local part_num="$5"

    if [ "$encryption" = "required" ] || [ "$encryption" = "optional" -a -n "$ENCRYPT_JOBS" ]; then
        setup_crypt_partition "$name" "$size" "$mount_point" "$encryption" "$part_num"
    else
        # Create standard partition
        parted -s "$DEVICE" mkpart primary ext4 "$start" "$end"
        mkfs.ext4 "${DEVICE}p${part_num}"
    fi
}

# Setup TEE memory
setup_tee_memory() {
    # Create mount point
    mkdir -p "${ROOT_MOUNT}${TEE_MEMORY_PATH}"
    chmod 0700 "${ROOT_MOUNT}${TEE_MEMORY_PATH}"
    chown root:root "${ROOT_MOUNT}${TEE_MEMORY_PATH}"
    
    # Add to fstab
    echo "tmpfs ${TEE_MEMORY_PATH} tmpfs defaults,size=${TEE_MEMORY_SIZE},mode=0700 0 0"
}

# Cleanup function
cleanup_partitions() {
    log "Cleaning up partition setup..."
    
    # Close all LUKS devices
    for mapper in $(dmsetup ls --target crypt | cut -f1); do
        cryptsetup close "$mapper" || true
    done
    
    # Close all verity devices
    for mapper in $(dmsetup ls --target verity | cut -f1); do
        veritysetup close "$mapper" || true
    done
    
    # Unmount all partitions
    for mount in $(mount | grep "${ROOT_MOUNT}" | cut -d' ' -f3 | sort -r); do
        umount "$mount" || true
    done
}

# Set trap for cleanup
trap cleanup_partitions EXIT

# Run partition setup
setup_partitions "$DEVICE" 