#!/bin/bash

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

# Helper Functions
log() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')] $1${NC}"
}

error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}" >&2
    exit 1
}

# Required packages
REQUIRED_PACKAGES=(
    "cryptsetup"
    "cryptsetup-bin"
    "cryptsetup-initramfs"
    "cryptsetup-run"
    "dmsetup"
    "lvm2"
    "parted"
    "acl"
    "attr"  # for extended attributes
    "util-linux"
    "coreutils"
    "e2fsprogs"
    "kmod"
    "systemd"
)

# Required package versions
declare -A MIN_VERSIONS=(
    ["cryptsetup"]="2.3.0"
    ["systemd"]="245"
    ["e2fsprogs"]="1.45"
    ["lvm2"]="1.02.175"
    ["util-linux"]="2.34"
)

# Install required packages
install_dependencies() {
    log "Checking and installing required packages..."
    
    # Check if running as root
    if [[ $EUID -ne 0 ]]; then
        error "Please run as root (sudo)"
    fi
    
    # Check if apt is available
    if ! command -v apt-get >/dev/null 2>&1; then
        error "This script requires apt package manager"
    fi
    
    # Update package list
    apt-get update || error "Failed to update package list"
    
    # Install packages
    for pkg in "${REQUIRED_PACKAGES[@]}"; do
        if ! dpkg -l | grep -q "^ii.*$pkg"; then
            log "Installing $pkg..."
            apt-get install -y "$pkg" || error "Failed to install $pkg"
        fi
    done
    
    # Verify package versions
    verify_package_versions
    
    log "All required packages installed"
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

    log "All package versions meet requirements"
}

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

# Verify required commands
verify_commands() {
    log "Verifying required commands..."
    
    local required_commands=(
        "cryptsetup"
        "dmsetup"
        "parted"
        "mkfs.ext4"
        "systemctl"
        "veritysetup"
        "getfacl"
        "losetup"
        "mount"
        "umount"
        "dd"
        "shred"
        "modprobe"
        "dmsetup"
        "grep"
        "sed"
        "find"
    )
    
    for cmd in "${required_commands[@]}"; do
        if ! command -v "$cmd" >/dev/null 2>&1; then
            error "Required command not found: $cmd"
        fi
    done
    
    # Verify kernel modules
    local required_modules=(
        "dm_crypt"
        "dm_verity"
        "aes"
        "sha256"
        "xts"
    )

    for module in "${required_modules[@]}"; do
        if ! modprobe -n "$module" 2>/dev/null; then
            error "Required kernel module not available: $module"
        fi
    done
    
    log "All required commands available"
}

# Source configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source configuration
source "${SCRIPT_DIR}/config/partition_config.sh"

# Main installation function
install() {
    log "Starting NVFLARE partition installation..."
    
    # Check hardware and kernel capabilities first
    check_hardware_capabilities
    check_kernel_modules

    # Install dependencies and verify commands
    install_dependencies
    verify_commands

    # Create systemd service
    create_systemd_service
    
    # Setup initial partitions
    setup_partitions
    
    # Enable and start service
    systemctl enable nvflare-partitions
    systemctl start nvflare-partitions
    
    log "Installation completed successfully"
}

# Create systemd service
create_systemd_service() {
    # ... existing function content ...
}

# Setup initial partitions
setup_partitions() {
    # ... existing function content ...
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

# Check required kernel modules
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

# Run installation
install 