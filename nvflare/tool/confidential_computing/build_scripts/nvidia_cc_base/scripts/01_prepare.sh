#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

# Check required tools
check_prerequisites() {
    local required_tools=(
        "debootstrap"
        "parted"
        "cryptsetup"
        "veritysetup"
        "qemu-img"
        "curl"
        "wget"
    )
    
    for tool in "${required_tools[@]}"; do
        if ! command -v "$tool" &> /dev/null; then
            error "Required tool '$tool' not found"
        fi
    done
}

# Validate configurations
validate_configs() {
    # Check ISO file
    if [ ! -f "$ISO_FILE" ]; then
        error "ISO file not found: $ISO_FILE"
    fi
    
    # Check mount points
    for mount in "$ROOT_MOUNT" "$APP_MOUNT" "$RO_MOUNT" "$DYNAMIC_MOUNT"; do
        check_mount_point "$mount"
    done
}

# Create build directories
setup_build_env() {
    # Create mount points
    mkdir -p "$ROOT_MOUNT"
    mkdir -p "$APP_MOUNT"
    mkdir -p "$RO_MOUNT"
    mkdir -p "$DYNAMIC_MOUNT"
    
    check_output_dir
    
    # Create work directory
    mkdir -p "${ROOT_MOUNT}/work"
    
    # Set up logging
    mkdir -p "${ROOT_MOUNT}/log"
    exec 1> >(tee "${ROOT_MOUNT}/log/build.log")
    exec 2>&1
}

# Main
log "Preparing build environment..."
check_root
check_prerequisites
validate_configs
setup_build_env
success "Preparation complete" 