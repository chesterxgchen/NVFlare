#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Copy initramfs scripts
install_initramfs() {
    local root_mount="$1"
    
    # Create directories
    mkdir -p "${root_mount}/etc/initramfs-tools/scripts/init-premount"
    mkdir -p "${root_mount}/etc/initramfs-tools/hooks"
    
    # Copy scripts
    cp "${SCRIPT_DIR}/initramfs/scripts/init-premount/tee-init" \
        "${root_mount}/etc/initramfs-tools/scripts/init-premount/"
    
    # Copy hooks
    cp "${SCRIPT_DIR}/initramfs/hooks/tee" \
        "${root_mount}/etc/initramfs-tools/hooks/"
    
    # Set permissions
    chmod 755 "${root_mount}/etc/initramfs-tools/scripts/init-premount/tee-init"
    chmod 755 "${root_mount}/etc/initramfs-tools/hooks/tee"
    
    # Update initramfs
    chroot "$root_mount" update-initramfs -u
} 