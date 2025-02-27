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

# Required package versions
declare -A MIN_VERSIONS=(
    ["cryptsetup"]="2.3.0"
    ["systemd"]="245"
    ["e2fsprogs"]="1.45"
    ["lvm2"]="1.02.175"
    ["util-linux"]="2.34"
)

# Version comparison helper
verify_version() {
    local current="$1"
    local required="$2"
    
    # Convert versions to arrays
    IFS='.' read -ra current_arr <<< "$current"
    IFS='.' read -ra required_arr <<< "$required"
    
    # Compare each component
    for i in "${!required_arr[@]}"; do
        if [ "${current_arr[i]:-0}" -lt "${required_arr[i]}" ]; then
            return 1
        elif [ "${current_arr[i]:-0}" -gt "${required_arr[i]}" ]; then
            return 0
        fi
    done
    return 0
}

# Verify package versions
verify_package_versions() {
    log "Verifying package versions..."

    for pkg in "${!MIN_VERSIONS[@]}"; do
        local min_version="${MIN_VERSIONS[$pkg]}"
        local current_version

        case "$pkg" in
            "cryptsetup")
                current_version=$(cryptsetup --version | grep -oE '[0-9]+\.[0-9]+\.[0-9]+')
                ;;
            "systemd")
                current_version=$(systemctl --version | head -1 | grep -oE '[0-9]+')
                ;;
            "e2fsprogs")
                current_version=$(mkfs.ext4 -V 2>&1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+')
                ;;
            "lvm2")
                current_version=$(dmsetup --version | awk '{print $3}' | grep -oE '^[0-9]+\.[0-9]+\.[0-9]+')
                ;;
            "util-linux")
                current_version=$(mount --version | head -1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+')
                ;;
        esac

        log "Checking $pkg version: current=$current_version, required=$min_version"
        if ! verify_version "$current_version" "$min_version"; then
            error "Package $pkg version $current_version is lower than required $min_version"
        fi
    done
}

# Check hardware capabilities
check_hardware_capabilities() {
    log "Checking hardware capabilities..."

    # Check CPU AES support
    if ! grep -q '^flags.*aes' /proc/cpuinfo; then
        error "CPU does not support AES instructions"
    fi

    # Check available memory
    local mem_available=$(free -m | awk '/^Mem:/ {print $7}')
    if [ "$mem_available" -lt 1024 ]; then
        error "Insufficient memory available: ${mem_available}M (need at least 1024M)"
    fi

    # Check disk space
    local disk_space=$(df -m "$PWD" | awk 'NR==2 {print $4}')
    if [ "$disk_space" -lt 2048 ]; then
        error "Insufficient disk space: ${disk_space}M (need at least 2048M)"
    fi
}

# Check kernel modules
check_kernel_modules() {
    log "Checking required kernel modules..."
    
    local required_modules=(
        "dm_crypt"
        "dm_verity"
        "aes"
        "sha256"
        "xts"
        "ecb"
        "cbc"
        "hmac"
    )
    
    for module in "${required_modules[@]}"; do
        if ! lsmod | grep -q "^${module}" && ! modprobe -n "$module" 2>/dev/null; then
            error "Required kernel module not available: $module"
        fi
    done
}

# Check requirements
check_requirements() {
    log "Checking system requirements..."

    # Check hardware and kernel capabilities
    check_hardware_capabilities
    check_kernel_modules

    # Verify package versions
    verify_package_versions

    # Check required commands
    for cmd in parted cryptsetup veritysetup mkfs.ext4; do
        command -v $cmd >/dev/null 2>&1 || error "$cmd is required but not installed."
    done

    # Check if running in a confidential VM
    if [ "${MOCK_CVM:-0}" != "1" ]; then
        if ! dmesg | grep -qE "Confidential|SEV-SNP|TDX guest"; then
            error "Not running in a Confidential VM"
        fi
    else
        log "Running in mock CVM mode"
    fi

    # Check device exists
    if [ ! -b "${DEVICE}" ]; then
        error "Block device ${DEVICE} does not exist"
    fi

    # Check if device is already in use
    if mount | grep -v swap | grep -q "^${DEVICE}"; then
        error "Device ${DEVICE} is already mounted"
    fi

    log "System requirements check passed"
}

# Setup verity partition
setup_verity_partition() {
    local name=$1 size=$2 mount_point=$3
    local part_num=$4
    
    log "Setting up verity partition: $name"
    
    # Verify partition doesn't exist
    if [ -e "${DEVICE}p${part_num}" ]; then
        error "Partition ${DEVICE}p${part_num} already exists"
    }

    # Verify mount point is clean
    if mountpoint -q "$mount_point" 2>/dev/null; then
        error "Mount point $mount_point is already in use"
    }

    # Create parent directories if needed
    local parent_dir=$(dirname "$mount_point")
    if [ ! -d "$parent_dir" ]; then
        mkdir -p "$parent_dir" || error "Failed to create parent directory: $parent_dir"
    }
    
    # Create data partition
    parted -s $DEVICE mkpart primary ${size}
    local data_dev="${DEVICE}p${part_num}"
    
    # Create hash partition (typically 1/64 size of data)
    local hash_size=$(calculate_hash_size ${size})
    parted -s $DEVICE mkpart primary ${hash_size}
    local hash_dev="${DEVICE}p$((part_num+1))"
    
    # Format with dm-verity
    veritysetup format \
        $data_dev \
        $hash_dev \
        --hash-algorithm=${VERITY_HASH} \
        --data-block-size=${VERITY_DATABLOCK} \
        --hash-block-size=${VERITY_HASHBLOCK}
    
    # Store root hash
    local root_hash=$(veritysetup format $data_dev $hash_dev | grep "Root hash:" | cut -d' ' -f3)
    echo $root_hash > "${mount_point}.roothash"
    
    # Create mapping
    veritysetup open \
        $data_dev \
        "${name}_verity" \
        $hash_dev \
        $root_hash
    
    # Create filesystem
    mkfs.ext4 /dev/mapper/${name}_verity || error "Failed to create filesystem for $name"
    
    # Mount
    mkdir -p $mount_point
    mount /dev/mapper/${name}_verity $mount_point || error "Failed to mount $name"
}

# Setup encrypted partition
setup_crypt_partition() {
    local name=$1 size=$2 mount_point=$3 encryption=$4
    local part_num=$5
    
    log "Setting up encrypted partition: $name"
    
    # Create partition
    parted -s $DEVICE mkpart primary ${size} || error "Failed to create partition for $name"
    local part_dev="${DEVICE}p${part_num}"
    
    if [ "$encryption" = "required" ] || [ "$encryption" = "optional" -a -n "$ENCRYPT_JOBS" ]; then
        IFS=':' read -r cipher key_size hash <<< "${CRYPT_CONFIG[0]}"
        
        # Generate key in confidential VM memory
        # Memory is already protected by SEV-SNP/TDX
        local key_file="/dev/shm/${name}.key"  # Using encrypted memory
        dd if=/dev/urandom of="$key_file" bs=1024 count=4
        chmod 0400 "$key_file"
        
        # Setup encryption
        cryptsetup luksFormat \
            --type luks2 \
            --cipher $cipher \
            --key-size $key_size \
            --hash $hash \
            --key-file "$key_file" \
            $part_dev || error "Failed to setup encryption for $name"
            
        # Open encrypted device
        cryptsetup open \
            --key-file "$key_file" \
            $part_dev ${name}_crypt || error "Failed to open encrypted device for $name"
        
        # Securely remove key file from memory
        shred -u "$key_file"
        
        # Create filesystem
        mkfs.ext4 /dev/mapper/${name}_crypt || error "Failed to create filesystem for $name"
        
        # Mount
        mkdir -p $mount_point
        mount /dev/mapper/${name}_crypt $mount_point || error "Failed to mount $name"
    else
        # Create regular filesystem
        mkfs.ext4 $part_dev || error "Failed to create filesystem for $name"
        mkdir -p $mount_point
        mount $part_dev $mount_point || error "Failed to mount $name"
    fi
}

# Setup tmpfs
setup_tmpfs() {
    local name=$1 size=$2 mount_point=$3
    
    log "Setting up tmpfs: $name"
    
    IFS=':' read -r mode uid gid <<< "${TMPFS_CONFIG[0]}"
    
    mkdir -p $mount_point
    mount -t tmpfs \
        -o size=$size,mode=$mode,uid=$uid,gid=$gid \
        tmpfs $mount_point || error "Failed to setup tmpfs for $name"
}

# Main setup
main() {
    # Generate fstab entries
    generate_fstab() {
        local fstab_file="/etc/fstab"
        local tmp_fstab=$(mktemp)
        
        # Copy existing entries except swap
        grep -v swap "$fstab_file" > "$tmp_fstab"
        
        # Add our entries
        for name in "${!PARTITIONS[@]}"; do
            IFS=':' read -r size type mount_point encryption <<< "${PARTITIONS[$name]}"
            case $type in
                "verity")
                    echo "/dev/mapper/${name}_verity $mount_point ext4 ro,noatime 0 0" >> "$tmp_fstab"
                    ;;
                "crypt")
                    if [ "$encryption" = "required" ] || [ "$encryption" = "optional" -a -n "$ENCRYPT_JOBS" ]; then
                        echo "/dev/mapper/${name}_crypt $mount_point ext4 defaults,noatime 0 0" >> "$tmp_fstab"
                    else
                        echo "${DEVICE}p${part_num} $mount_point ext4 defaults,noatime 0 0" >> "$tmp_fstab"
                    fi
                    ;;
                "tmpfs")
                    echo "tmpfs $mount_point tmpfs size=$size,mode=$TMPFS_MODE,uid=$TMPFS_UID,gid=$TMPFS_GID 0 0" >> "$tmp_fstab"
                    ;;
            esac
        done
        
        # Replace fstab
        mv "$tmp_fstab" "$fstab_file"
    }

    check_requirements
    
    # Create base mount point
    mkdir -p $ROOT_MOUNT
    
    # Initialize partition table
    parted -s $DEVICE mklabel gpt || error "Failed to create partition table"
    
    # Setup partitions
    local part_num=1
    for name in "${!PARTITIONS[@]}"; do
        IFS=':' read -r size type mount_point encryption <<< "${PARTITIONS[$name]}"
        
        case $type in
            "verity")
                setup_verity_partition "$name" "$size" "$mount_point" "$part_num"
                ;;
            "crypt")
                setup_crypt_partition "$name" "$size" "$mount_point" "$encryption" "$part_num"
                ;;
            "tmpfs")
                setup_tmpfs "$name" "$size" "$mount_point"
                ;;
        esac
        ((part_num++))
    done
    
    # Disable swap if configured
    if [ "$SWAP_ENABLED" = false ]; then
        swapoff -a
        sed -i '/swap/d' /etc/fstab
    fi
    
    generate_fstab
    log "Setup completed successfully"
}

# Run setup
main "$@" 