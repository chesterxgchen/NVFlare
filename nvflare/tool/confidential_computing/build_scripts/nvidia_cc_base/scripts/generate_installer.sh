#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../config/partition.conf"
source "${SCRIPT_DIR}/../config/security.conf"

# Generate installer script
generate_installer() {
    local installer_name="$INSTALLER_NAME"
    
    cat > "$installer_name" <<'EOF'
#!/bin/bash

set -e

# Configuration
IMAGE_FILE="${OUTPUT_IMAGE##*/}"  # Get filename only
TARGET_DEVICE="${TARGET_DEVICE}"
OUTPUT_DIR="${OUTPUT_DIR}"

# Parse arguments
while getopts "d:i:o:h" opt; do
    case $opt in
        d) TARGET_DEVICE="$OPTARG" ;;
        i) IMAGE_FILE="$OPTARG" ;;
        o) OUTPUT_DIR="$OPTARG" ;;
        h) 
            echo "Usage: $0 [-d device] [-i image_file] [-o output_dir]"
            echo "  -d: Target device (will detect if not specified)"
            echo "  -i: Image file (default: ${IMAGE_FILE})"
            echo "  -o: Output directory (default: ${OUTPUT_DIR})"
            exit 0
            ;;
        *) 
            echo "Invalid option: -$OPTARG"
            exit 1
            ;;
    esac
done

# Check requirements
check_requirements() {
    if [[ $EUID -ne 0 ]]; then
        echo "This script must be run as root"
        exit 1
    fi

    if [ ! -f "$IMAGE_FILE" ]; then
        echo "Image file not found: $IMAGE_FILE"
        exit 1
    fi

    # Device check moved to install_image()
}

# Add device detection function
detect_devices() {
    local devices=()
    local scores=()
    # Look for nvme devices
    for dev in /dev/nvme[0-9]n[0-9]; do
        if [ -b "$dev" ]; then
            devices+=("$dev")
            # Score based on device type and size
            local size_gb=$(lsblk -dn -o SIZE -b "$dev" | awk '{print int($1/1024/1024/1024)}')
            local score=100  # Base score for NVMe
            # Add size score (1 point per GB over minimum required)
            score=$((score + size_gb - 32))  # Assuming 32GB minimum
            scores+=("$score")
        fi
    done
    # Look for SATA/SCSI devices
    for dev in /dev/sd[a-z]; do
        if [ -b "$dev" ]; then
            devices+=("$dev")
            # Score based on device type and size
            local size_gb=$(lsblk -dn -o SIZE -b "$dev" | awk '{print int($1/1024/1024/1024)}')
            local score=50   # Base score for SATA/SCSI
            score=$((score + size_gb - 32))
            scores+=("$score")
        fi
    done
    
    if [ ${#devices[@]} -eq 0 ]; then
        error "No suitable devices found"
    fi
    
    # Auto-select based on rules
    local best_score=0
    local best_index=0
    
    for i in "${!devices[@]}"; do
        local dev="${devices[$i]}"
        local score="${scores[$i]}"
        local size_gb=$(lsblk -dn -o SIZE -b "$dev" | awk '{print int($1/1024/1024/1024)}')
        local model=$(lsblk -dn -o MODEL "$dev")
        local mounted=$(lsblk -dn -o MOUNTPOINT "$dev" | grep -v "^$" || true)
        
        # Log device info
        log "Found device: $dev ($size_gb GB, $model)"
        
        # Disqualify if:
        # 1. Device is too small
        if [ "$size_gb" -lt 32 ]; then
            log "Skipping $dev: Too small ($size_gb GB < 32 GB)"
            continue
        fi
        # 2. Device is mounted
        if [ -n "$mounted" ]; then
            log "Skipping $dev: Currently mounted"
            continue
        fi
        # 3. Device contains OS (has EFI or boot partition)
        if lsblk -n "$dev" | grep -qE "EFI|boot"; then
            log "Skipping $dev: Contains OS partitions"
            continue
        fi
        
        # Update best device if score is higher
        if [ "$score" -gt "$best_score" ]; then
            best_score="$score"
            best_index="$i"
        fi
    done
    
    # Check if we found a suitable device
    if [ "$best_score" -eq 0 ]; then
        error "No suitable devices found matching criteria"
    fi
    
    # Use the best device
    TARGET_DEVICE="${devices[$best_index]}"
    log "Auto-selected device: $TARGET_DEVICE (Score: $best_score)"
    
    # Allow override with confirmation
    if [ "${AUTO_SELECT:-true}" != "true" ]; then
        # Print available devices
        echo "Available devices:"
        for i in "${!devices[@]}"; do
            local size=$(lsblk -dn -o SIZE "${devices[$i]}")
            local model=$(lsblk -dn -o MODEL "${devices[$i]}")
            echo "[$i] ${devices[$i]} ($size, $model, Score: ${scores[$i]})"
        done
        
        # Ask user to select device
        while true; do
            read -p "Select device number [0-$((${#devices[@]}-1))]: " choice
            if [[ "$choice" =~ ^[0-9]+$ ]] && [ "$choice" -lt "${#devices[@]}" ]; then
                TARGET_DEVICE="${devices[$choice]}"
                break
            fi
            echo "Invalid selection, try again"
        done
    fi
}

# Install image
install_image() {
    # If no device specified, detect available devices
    if [ -z "$TARGET_DEVICE" ]; then
        detect_devices
    fi
    
    # Confirm device selection
    echo "WARNING: This will erase all data on $TARGET_DEVICE"
    read -p "Continue? [y/N] " confirm
    if [[ ! "$confirm" =~ ^[yY]$ ]]; then
        error "Installation aborted by user"
    fi
    
    echo "Installing CC image to $TARGET_DEVICE..."
    
    # Write image to device
    qemu-img convert -f qcow2 -O raw "$IMAGE_FILE" "$TARGET_DEVICE"
    
    # Update partition table
    partprobe "$TARGET_DEVICE"
    
    # Mount encrypted partitions
    cryptsetup open "${TARGET_DEVICE}p2" app_crypt
    mount /dev/mapper/app_crypt /mnt/app
    
    # Setup dm-verity for read-only partition
    veritysetup verify "${TARGET_DEVICE}p3" "${TARGET_DEVICE}p3.verity"
    
    echo "Installation completed successfully"
}

# Add TEE configuration handling
configure_tee() {
    # TEE config is copied from /boot/cc/tee.conf during installation
    
    # Create systemd service to handle TEE memory resizing
    cat > "/etc/systemd/system/tee-memory.service" <<EOF
[Unit]
Description=TEE Memory Configuration Service
After=local-fs.target

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/configure-tee-memory
RemainAfterExit=yes
ProtectSystem=strict
ReadOnlyPaths=/
ReadWritePaths=/dev/shm
ProtectHome=yes

[Install]
WantedBy=multi-user.target
EOF

    # Create the configuration script
    cat > "/usr/local/sbin/configure-tee-memory" <<EOF
#!/bin/bash
set -e

# Source TEE configuration
source /boot/cc/tee.conf

# Validate memory size
if [[ "\${TEE_MEMORY_SIZE}" =~ ^[0-9]+[GgMm]$ ]]; then
    # Convert sizes to bytes for comparison
    min_bytes=\$(numfmt --from=iec \${TEE_MEMORY_MIN})
    max_bytes=\$(numfmt --from=iec \${TEE_MEMORY_MAX})
    size_bytes=\$(numfmt --from=iec \${TEE_MEMORY_SIZE})
    
    if [ \$size_bytes -lt \$min_bytes ]; then
        echo "Error: TEE memory size below minimum (\${TEE_MEMORY_MIN})"
        exit 1
    fi
    
    if [ \$size_bytes -gt \$max_bytes ]; then
        echo "Error: TEE memory size above maximum (\${TEE_MEMORY_MAX})"
        exit 1
    fi
    
    # Apply configuration
    mount -o remount,size=\${TEE_MEMORY_SIZE} \${TEE_MEMORY_PATH}
    chown \${TEE_MEMORY_OWNER}:\${TEE_MEMORY_GROUP} \${TEE_MEMORY_PATH}
    chmod \${TEE_MEMORY_MODE} \${TEE_MEMORY_PATH}
fi
EOF

    chmod 0755 "/usr/local/sbin/configure-tee-memory"
}

# Main
echo "NVIDIA CC Image Installer"
check_requirements
install_image
configure_tee
EOF

    chmod +x "$installer_name"
    echo "Generated installer script: $installer_name"
}

# Run generator
generate_installer 