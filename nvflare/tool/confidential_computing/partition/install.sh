#!/bin/bash

set -e  # Exit on error

# Source configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Logging
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

error() {
    log "ERROR: $1" >&2
    exit 1
}

# Validate installation environment
validate_install_env() {
    log "Validating installation environment..."

    # Check if running as root
    if [ "$EUID" -ne 0 ]; then
        error "Please run as root"
    fi

    # Check required commands
    local required_cmds=(
        parted
        cryptsetup
        veritysetup
        mkfs.ext4
        systemctl
        mount
        umount
        dd
        shred
    )

    for cmd in "${required_cmds[@]}"; do
        command -v "$cmd" >/dev/null 2>&1 || error "$cmd is required but not installed"
    done

    # Check if running in a confidential VM
    if ! dmesg | grep -qE "Confidential|SEV-SNP|TDX guest"; then
        error "Not running in a Confidential VM"
    fi

    # Check if target directories are writable
    local dirs=(
        "/usr/local/bin"
        "/usr/local/etc/nvflare"
        "/etc/systemd/system"
    )

    for dir in "${dirs[@]}"; do
        if [ -e "$dir" ] && ! [ -w "$dir" ]; then
            error "Directory $dir exists but is not writable"
        fi
    done

    # Validate configuration file
    source "${SCRIPT_DIR}/config/partition_config.sh"

    log "Installation environment validation passed"
}

# Install dependencies
install_deps() {
    log "Installing dependencies..."
    
    # Check if package manager is available
    if ! command -v apt-get >/dev/null 2>&1; then
        error "apt-get not found. This script requires a Debian-based system."
    fi
    
    # Check if we can install packages
    if ! apt-get update >/dev/null 2>&1; then
        error "Failed to update package list. Check your internet connection."
    fi
    
    # Install required packages
    apt-get install -y \
        cryptsetup \
        cryptsetup-bin \
        cryptsetup-initramfs \
        cryptsetup-run \
        parted \
        util-linux \
        systemd || error "Failed to install required packages"
}

# Install scripts
install_scripts() {
    log "Installing scripts..."
    
    # Required scripts
    local scripts=(
        "setup_partitions.sh"
        "cleanup_partitions.sh"
        "verify_partitions.sh"
        "config/partition_config.sh"
        "config/partition.conf"
    )
    
    # Validate script files exist
    for script in "${scripts[@]}"; do
        if [ ! -f "${SCRIPT_DIR}/${script}" ]; then
            error "Required script not found: ${script}"
        fi
    done
    
    # Create directories
    mkdir -p /usr/local/bin || error "Failed to create /usr/local/bin"
    mkdir -p /usr/local/etc/nvflare/config || error "Failed to create /usr/local/etc/nvflare/config"
    
    # Copy scripts with error checking
    for script in setup_partitions.sh cleanup_partitions.sh verify_partitions.sh; do
        cp "${SCRIPT_DIR}/${script}" /usr/local/bin/ || error "Failed to copy ${script}"
        chmod +x "/usr/local/bin/${script}" || error "Failed to set permissions for ${script}"
    done
    
    # Copy configuration files
    cp "${SCRIPT_DIR}/config/partition_config.sh" /usr/local/etc/nvflare/config/ || \
        error "Failed to copy partition_config.sh"
    cp "${SCRIPT_DIR}/config/partition.conf" /usr/local/etc/nvflare/config/ || \
        error "Failed to copy partition.conf"
}

# Install systemd service
install_service() {
    log "Installing systemd service..."
    
    if [ ! -f "${SCRIPT_DIR}/nvflare-partitions.service" ]; then
        error "Service file not found: nvflare-partitions.service"
    fi
    
    cp "${SCRIPT_DIR}/nvflare-partitions.service" /etc/systemd/system/ || \
        error "Failed to copy service file"
    
    systemctl daemon-reload || error "Failed to reload systemd configuration"
    systemctl enable nvflare-partitions.service || error "Failed to enable service"
}

# Verify installation
verify_install() {
    log "Verifying installation..."
    
    # Check scripts are installed
    for cmd in setup_partitions.sh cleanup_partitions.sh verify_partitions.sh; do
        if ! command -v "$cmd" >/dev/null 2>&1; then
            error "Installation verification failed: $cmd not found in PATH"
        fi
    done
    
    # Check configuration files exist
    local config_files=(
        "/usr/local/etc/nvflare/config/partition_config.sh"
        "/usr/local/etc/nvflare/config/partition.conf"
    )
    for file in "${config_files[@]}"; do
        if [ ! -f "$file" ]; then
            error "Installation verification failed: $file not found"
        fi
    done
    
    # Check service is installed
    if ! systemctl list-unit-files | grep -q nvflare-partitions.service; then
        error "Installation verification failed: systemd service not installed"
    fi
}

# Main installation
main() {
    validate_install_env
    install_deps
    install_scripts
    install_service
    verify_install
    
    log "Installation completed successfully"
    log "Review and modify /usr/local/etc/nvflare/config/partition.conf if needed"
    log "Run 'systemctl start nvflare-partitions' to setup partitions"
}

# Run installation
main "$@" 