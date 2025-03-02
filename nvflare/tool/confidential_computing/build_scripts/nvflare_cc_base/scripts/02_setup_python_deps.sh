#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../config/nvflare.conf"
source "${SCRIPT_DIR}/../../nvidia_cc_base/scripts/common/common.sh"

# Python version validation
validate_python_version() {
    local version="$1"
    
    # Check if version is in supported range
    if [[ ! "$version" =~ ^3\.(9|10|11|12)$ ]]; then
        error "Unsupported Python version: $version. Must be 3.9, 3.10, 3.11, or 3.12"
        return 1
    fi
    return 0
}

# Backup and rollback functions
BACKUP_DIR="/tmp/nvflare_backup"

create_venv_backup() {
    local mount_dir="$1"
    log "Creating backup of virtual environment..."
    mkdir -p "${BACKUP_DIR}"
    if [ -d "${mount_dir}${VENV_PATH}" ]; then
        tar czf "${BACKUP_DIR}/venv_backup.tar.gz" -C "${mount_dir}${VENV_PATH}" .
    fi
}

restore_from_backup() {
    local mount_dir="$1"
    if [ -f "${BACKUP_DIR}/venv_backup.tar.gz" ]; then
        log "Restoring from backup..."
        rm -rf "${mount_dir}${VENV_PATH}"
        mkdir -p "${mount_dir}${VENV_PATH}"
        tar xzf "${BACKUP_DIR}/venv_backup.tar.gz" -C "${mount_dir}${VENV_PATH}"
    fi
}

cleanup_backup() {
    rm -rf "${BACKUP_DIR}"
}

# Version compatibility check
check_version_compatibility() {
    local pkg="$1"
    local version="$2"
    local nvflare_ver="${NVFLARE_VERSION}"
    local python_ver="${PYTHON_VERSION}"
    
    case $pkg in
        "protobuf")
            if [[ "${version}" =~ ^4\. ]] && [[ "${nvflare_ver}" < "2.3" ]]; then
                error "Protobuf 4.x is not compatible with NVFLARE < 2.3"
                return 1
            fi
            ;;
        "grpcio")
            if [[ "${version}" =~ ^1\.62\. ]] && [[ "${nvflare_ver}" < "2.3" ]]; then
                error "grpcio 1.62.x requires NVFLARE >= 2.3"
                return 1
            fi
            # Check Python compatibility
            if [[ "${version}" =~ ^1\.62\. ]] && [[ "${python_ver}" > "3.11" ]]; then
                error "grpcio 1.62.x may have issues with Python > 3.11"
                return 1
            fi
            ;;
        "numpy")
            if [[ "${version}" =~ ^1\.2[0-3]\. ]]; then
                error "numpy versions 1.20-1.23 have known issues with NVFLARE"
                return 1
            fi
            ;;
        "PyYAML")
            if [[ "${version}" < "5.4" ]]; then
                error "PyYAML < 5.4 has security vulnerabilities"
                return 1
            fi
            ;;
        "cryptography")
            if [[ "${version}" < "36.0.0" ]]; then
                error "cryptography < 36.0.0 is not compatible with NVFLARE ${nvflare_ver}"
                return 1
            fi
            ;;
    esac
    return 0
}

# Check for dependency conflicts
check_dependency_conflicts() {
    local mount_dir="$1"
    local conflicts=0
    
    log "Checking for dependency conflicts..."
    
    # Run pip check and capture output
    local check_output
    check_output=$(chroot "$mount_dir" /bin/bash -c "
        source ${VENV_PATH}/bin/activate
        pip check 2>&1
    ")
    
    if [ $? -ne 0 ]; then
        error "Dependency conflicts found:"
        echo "$check_output" | while IFS= read -r line; do
            error "  $line"
        done
        conflicts=1
    fi
    
    # Additional specific checks
    chroot "$mount_dir" /bin/bash -c "
        source ${VENV_PATH}/bin/activate
        
        # Check torch compatibility if installed
        if pip show torch >/dev/null 2>&1; then
            torch_ver=$(pip show torch | grep Version | cut -d' ' -f2)
            numpy_ver=$(pip show numpy | grep Version | cut -d' ' -f2)
            
            if [[ "$torch_ver" =~ ^1\. ]] && [[ "$numpy_ver" =~ ^1\.2[0-3]\. ]]; then
                echo "Warning: PyTorch 1.x may have issues with numpy 1.20-1.23"
                conflicts=1
            fi
        fi
    "
    
    return $conflicts
}

# Enhanced logging
log_installation_summary() {
    local mount_dir="$1"
    local log_file="${mount_dir}/tmp/pip.log"
    
    log "Installation Summary:"
    log "===================="
    
    # Count total packages
    local total_pkgs=$(grep "Successfully installed" "$log_file" | tail -1 | wc -w)
    log "Total packages installed: $((total_pkgs - 2))"
    
    # Show versions of key packages
    log "Key package versions:"
    chroot "$mount_dir" /bin/bash -c "
        source ${VENV_PATH}/bin/activate
        for pkg in cryptography grpcio numpy protobuf PyYAML; do
            pip show $pkg | grep -E '^(Name|Version):'
        done
    " | while IFS= read -r line; do
        log "  $line"
    done
    
    # Show any warnings
    log "Warnings during installation:"
    grep -i "warning:" "$log_file" | sort -u | while IFS= read -r line; do
        log "  $line"
    done
}

# Mount image
MOUNT_DIR="/tmp/nvflare_build"
mkdir -p "$MOUNT_DIR"
guestmount -a "$OUTPUT_IMAGE" -m /dev/sda3 "$MOUNT_DIR"

# Create backup
create_venv_backup "$MOUNT_DIR"

log "Installing Python dependencies..."

# Validate Python version first
if ! validate_python_version "${PYTHON_VERSION}"; then
    exit 1
fi

# Define NVFLARE dependencies based on version
get_nvflare_deps() {
    local ver="$1"
    local python_ver="$2"
    case $ver in
        "2.3.0"|"2.6.0")
            cat << EOF
cryptography>=36.0.0
grpcio>=1.62.1
gunicorn>=22.0.0
numpy
protobuf>=4.24.4
psutil>=5.9.1
PyYAML>=6.0
requests>=2.28.0
six>=1.15.0
msgpack>=1.0.3
docker>=6.0
pyhocon
EOF
            ;;
        *)
            error "Unsupported NVFLARE version: $ver"
            return 1
            ;;
    esac
}

# Validate Python version
chroot "$MOUNT_DIR" /bin/bash -c "
    if ! command -v python${PYTHON_VERSION} >/dev/null 2>&1; then
        # Try to install Python if not found
        apt-get update
        apt-get install -y python${PYTHON_VERSION} python${PYTHON_VERSION}-venv python${PYTHON_VERSION}-dev
    fi

    if ! command -v python${PYTHON_VERSION} >/dev/null 2>&1; then
        echo "Error: Failed to install Python ${PYTHON_VERSION}"
        exit 1
    fi
    
    ver=$(python${PYTHON_VERSION} -V 2>&1 | cut -d' ' -f2)
    if [[ "$ver" < "${PYTHON_VERSION}" ]]; then
        echo "Error: Python version $ver is less than required ${PYTHON_VERSION}"
        exit 1
    fi
"

# Create requirements.txt from nvflare.conf
mkdir -p "${MOUNT_DIR}/tmp"
get_nvflare_deps "${NVFLARE_VERSION}" "${PYTHON_VERSION}" > "${MOUNT_DIR}/tmp/requirements.txt" || exit 1

# Install and validate dependencies
chroot "$MOUNT_DIR" /bin/bash -c "
    set -e
    # Activate virtual environment
    source ${VENV_PATH}/bin/activate

    # Check pip version
    pip_ver=$(pip --version | cut -d' ' -f2)
    if [[ "$pip_ver" < "21.0.0" ]]; then
        echo "Error: pip version $pip_ver is too old"
        exit 1
    fi

    # Install dependencies with progress
    pip install --no-cache-dir -r /tmp/requirements.txt 2>&1 | tee /tmp/pip.log | while IFS= read -r line; do
        echo "[PIP] $line"
    done

    # Verify installations and versions
    for pkg in cryptography grpcio gunicorn numpy protobuf psutil PyYAML requests six msgpack docker pyhocon; do
        pkg_info=$(pip show $pkg 2>/dev/null)
        if [ -z "$pkg_info" ]; then
            echo "Error: Package $pkg not installed properly"
            exit 1
        fi
        
        version=$(echo "$pkg_info" | grep ^Version: | cut -d' ' -f2)
        if ! check_version_compatibility "$pkg" "$version"; then
            exit 1
        fi
    done

    # Clean pip cache
    pip cache purge
" || {
    error "Failed to install dependencies"
    restore_from_backup "$MOUNT_DIR"
    exit 1
}

# Check for conflicts
if ! check_dependency_conflicts "$MOUNT_DIR"; then
    error "Dependency conflicts detected"
    restore_from_backup "$MOUNT_DIR"
    exit 1
fi

# Log installation summary
log_installation_summary "$MOUNT_DIR"

# Cleanup
rm "${MOUNT_DIR}/tmp/requirements.txt"
guestunmount "$MOUNT_DIR"
rmdir "$MOUNT_DIR"
cleanup_backup

log "Python dependencies installed successfully" 