#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../config/nvflare.conf"
source "${SCRIPT_DIR}/../config/security.conf"
source "${SCRIPT_DIR}/../../common/install_package.sh"

# Create NVFLARE directory structure based on role
create_nvflare_dirs() {
    local role="$1"
    
    # CC Apps Partition - Core installation
    mkdir -p "/etc/cc/apps/nvflare"
    mkdir -p "/etc/cc/apps/nvflare/venv"
    chown -R ${NVFLARE_USER}:${NVFLARE_GROUP} "/etc/cc/apps/nvflare"

    # Config Partition - Read-only configs
    mkdir -p "${NVFLARE_STARTUP_DIR}"
    mkdir -p "${NVFLARE_SITE_CONF_DIR}"
    # For server, also create job store key directory
    if [ "$role" = "SERVER" ] || [ "$role" = "ALL" ]; then
        mkdir -p "${NVFLARE_JOB_STORE_KEY}"
    fi
    chown -R ${NVFLARE_USER}:${NVFLARE_GROUP} "${NVFLARE_CONFIG_MOUNT}"

    # Dynamic Partition - Writable workspace
    mkdir -p "${NVFLARE_WORKSPACE}"
    mkdir -p "${NVFLARE_LOG_DIR}"
    # For server, create job store directory
    if [ "$role" = "SERVER" ] || [ "$role" = "ALL" ]; then
        mkdir -p "${NVFLARE_JOB_STORE_DIR}"
    fi
    chown -R ${NVFLARE_USER}:${NVFLARE_GROUP} "${NVFLARE_DYNAMIC_MOUNT}"
    
    # Data Partition - Client data access
    if [ "$role" = "CLIENT" ] || [ "$role" = "ALL" ]; then
        mkdir -p "${NVFLARE_DATA_DIR}"
        chown -R ${NVFLARE_USER}:${NVFLARE_GROUP} "${NVFLARE_DATA_MOUNT}"
    fi
}

# Setup environment configuration
setup_environment() {
    # Create environment setup script
    cat > "/etc/cc/apps/nvflare/env.sh" << EOF
#!/bin/bash
export PYTHONPATH="/etc/cc/apps/nvflare/venv/lib/python${PYTHON_VERSION}/site-packages"
export PATH="/etc/cc/apps/nvflare/venv/bin:\$PATH"
EOF

    chmod +x "/etc/cc/apps/nvflare/env.sh"
    chown ${NVFLARE_USER}:${NVFLARE_GROUP} "/etc/cc/apps/nvflare/env.sh"
}

# Check and install NVFLARE PEX package
install_nvflare_pex() {
    # PEX should be in host-visible config partition for verification
    local pex_file="/host/cc/packages/nvflare-${NVFLARE_VERSION}.pex"
    local pex_hash_file="${pex_file}.sha512"

    # Check if PEX file exists
    if [[ ! -f "$pex_file" ]]; then
        log_error "NVFLARE PEX package not found: $pex_file"
        return 1
    fi

    # Check if hash file exists
    if [[ ! -f "$pex_hash_file" ]]; then
        log_error "NVFLARE PEX hash file not found: $pex_hash_file"
        return 1
    }

    # Verify PEX hash
    if ! sha512sum -c "$pex_hash_file"; then
        log_error "PEX package hash verification failed"
        return 1
    }

    log_info "Installing NVFLARE PEX package..."

    # Create user and group
    groupadd -r ${NVFLARE_GROUP}
    useradd -r -g ${NVFLARE_GROUP} -d "/etc/cc/apps/nvflare" ${NVFLARE_USER}

    # Create directory structure based on role
    create_nvflare_dirs "${NVFLARE_ROLE}"

    # Create Python virtual environment in CC partition
    python3 -m venv "/etc/cc/apps/nvflare/venv"

    # Copy PEX to CC partition
    cp "$pex_file" "/etc/cc/apps/nvflare/nvflare.pex"
    chmod 500 "/etc/cc/apps/nvflare/nvflare.pex"
    chown "${NVFLARE_USER}:${NVFLARE_GROUP}" "/etc/cc/apps/nvflare/nvflare.pex"

    # Create symlink in PATH
    ln -sf "/etc/cc/apps/nvflare/nvflare.pex" "/usr/local/bin/nvflare"

    # Setup environment
    setup_environment

    # Verify installation
    if ! nvflare --version | grep -q "${NVFLARE_VERSION}"; then
        log_error "NVFLARE installation verification failed"
        return 1
    }

    log_info "NVFLARE PEX installation completed successfully"
    return 0
}

# Main function
main() {
    local mount_point="$1"

    if [[ -z "$mount_point" ]]; then
        log_error "Mount point not specified"
        return 1
    fi

    if [[ ! -d "$mount_point" ]]; then
        log_error "Mount point does not exist: $mount_point"
        return 1
    }

    log_info "Starting NVFLARE installation..."

    # Install NVFLARE PEX package
    if ! install_package "$mount_point" \
        "/host/cc/packages/nvflare-${NVFLARE_VERSION}.pex" \
        "/etc/cc/apps/nvflare" \
        "nvflare" \
        "/etc/cc/apps/nvflare/venv"; then
        log_error "NVFLARE installation failed"
        return 1
    fi

    log_info "NVFLARE installation completed"
    return 0
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    if [[ $# -ne 1 ]]; then
        log_error "Usage: $0 <mount_point>"
        exit 1
    fi
    main "$@"
fi 