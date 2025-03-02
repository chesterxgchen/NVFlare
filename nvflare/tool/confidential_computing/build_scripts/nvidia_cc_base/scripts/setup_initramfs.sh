#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common/common.sh"
source "${SCRIPT_DIR}/common/security_hardening.sh"

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

# Setup initramfs hooks
setup_initramfs_hooks() {
    # Copy security hardening script
    cp "${SCRIPT_DIR}/common/security_hardening.sh" "${INITRAMFS_DIR}/scripts/common/"

    # Setup TEE hooks
    cp "${SCRIPT_DIR}/initramfs/hooks/tee" "${INITRAMFS_DIR}/hooks/"
    chmod +x "${INITRAMFS_DIR}/hooks/tee"
} 