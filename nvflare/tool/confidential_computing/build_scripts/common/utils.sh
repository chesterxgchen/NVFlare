#!/bin/bash

source "$(dirname "${BASH_SOURCE[0]}")/validate_config.sh"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Logging functions
log_info() {
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

log_error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}" >&2
}

log_warning() {
    echo -e "${YELLOW}[$(date '+%Y-%m-%d %H:%M:%S')] WARNING: $1${NC}" >&2
}

log_success() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')] SUCCESS: $1${NC}"
}

# Common validation functions
check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root"
        return 1
    fi
}

check_directory() {
    local dir="$1"
    if [[ ! -d "$dir" ]]; then
        log_info "Creating directory: $dir"
        mkdir -p "$dir" || {
            log_error "Failed to create directory: $dir"
            return 1
        }
    fi
}

check_file() {
    local file="$1"
    if [[ ! -f "$file" ]]; then
        log_error "File not found: $file"
        return 1
    fi
}

check_command() {
    local cmd="$1"
    if ! command -v "$cmd" &> /dev/null; then
        log_error "Required command not found: $cmd"
        return 1
    fi
}

# Validate configurations before proceeding
validate_configs() {
    # Validate fixed configurations haven't been modified
    if ! validate_fixed_configs; then
        return 1
    fi

    # Validate partition numbers
    if ! validate_partition_numbers; then
        return 1
    fi

    return 0
}

# Calculate size in GB with safety factor
calculate_size_gb() {
    local bytes=$1
    local safety=${SAFETY_FACTOR:-2.0}
    echo "$((bytes * safety / 1024 / 1024 / 1024 + 1))G"
}

# Verify file exists and get size
get_file_size() {
    local file="$1"
    if [[ ! -f "$file" ]]; then
        log_error "File not found: $file"
        return 1
    fi
    stat -f %z "$file"
}

# Package installation handlers
# These correspond to the handlers defined in security.conf

# Executable package installation handler
exec_wheel_packages_install() {
    local mount_point="$1"
    local package_path="$2"
    local install_path="$3"
    local mode="$4"
    local owner="$5"

    log_info "Installing executable package from ${package_path} to ${install_path}"

    # Verify and install using common package installer
    if ! install_tar_package "$mount_point" "$package_path" "$install_path"; then
        log_error "wheel packages installation failed"
        return 1
    fi

    # Verify and install using common package installer
    if ! install_wheels "$mount_point" "$package_path" "$install_path"; then
        log_error "wheel packages installation failed"
        return 1
    fi
 
    return 0
}

# Startup kit installation handler
startup_kit_install() {
    local mount_point="$1"
    local package_path="$2"
    local install_path="$3"
    local mode="$4"
    local owner="$5"

    log_info "Installing startup kit from ${package_path} to ${install_path}"

    # Verify and install using common package installer
    if ! install_tar_package "$mount_point" "$package_path" "$install_path"; then
        log_error "Startup kit installation failed"
        return 1
    fi

    # Create symbolic link from startup/local to site_conf
    local startup_local="${mount_point}${install_path}/local"
    local site_conf_dir="${mount_point}${NVFLARE_SITE_CONF_DIR}"

    if [[ ! -d "$startup_local" ]]; then
        log_error "Local directory not found in startup kit: $startup_local"
        return 1
    fi

    # Create site_conf parent directory if needed
    check_directory "$(dirname $site_conf_dir)" || return 1

    # Create symbolic link
    log_info "Creating symbolic link from ${startup_local} to ${site_conf_dir}"
    ln -sf "${install_path}/local" "${site_conf_dir}"

    # Set permissions and ownership recursively
    chmod -R "$mode" "${mount_point}${install_path}"
    chown -R "$owner" "${mount_point}${install_path}"

    log_info "Startup kit installation and configuration completed"
    return 0
}

# Generic package handler dispatcher
handle_package_install() {
    local handler="$1"
    local mount_point="$2"
    local package_path="$3"
    local install_path="$4"
    local mode="$5"
    local owner="$6"

    case "$handler" in
        executable_install)
            exec_wheel_packages_install "$mount_point" "$package_path" "$install_path" "$mode" "$owner"
            ;;
        startup_kit_install)
            startup_kit_install "$mount_point" "$package_path" "$install_path" "$mode" "$owner"
            ;;
        *)
            log_error "Unknown package handler: $handler"
            return 1
            ;;
    esac
} 