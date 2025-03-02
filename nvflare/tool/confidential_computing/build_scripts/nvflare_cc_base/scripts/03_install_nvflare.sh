#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../config/nvflare.conf"

# Mount all required partitions
MOUNT_DIR="/tmp/nvflare_build"
mkdir -p "$MOUNT_DIR"

# Function to safely mount a partition
safe_mount() {
    local image="$1"
    local label="$2"
    local mount_point="$3"
    local fs_type="$4"
    
    # Create mount point
    mkdir -p "$mount_point"
    
    # Mount partition
    if ! guestmount -a "$image" -m "label:$label" "$mount_point"; then
        error "Failed to mount $label at $mount_point"
        return 1
    fi
    
    log "Successfully mounted $label at $mount_point"
    return 0
}

# Mount root partition (p3)
safe_mount "$OUTPUT_IMAGE" "${NVFLARE_ROOT_LABEL}" "$MOUNT_DIR" || exit 1

# Mount config partition (p4)
safe_mount "$OUTPUT_IMAGE" "${NVFLARE_CONFIG_LABEL}" "${MOUNT_DIR}${NVFLARE_CONFIG_MOUNT}" || exit 1

# Mount dynamic partition (p5)
safe_mount "$OUTPUT_IMAGE" "${NVFLARE_DYNAMIC_LABEL}" "${MOUNT_DIR}${NVFLARE_DYNAMIC_MOUNT}" || exit 1

# Mount data partition (p6) for client
if [ "$NVFLARE_ROLE" = "CLIENT" ] || [ "$NVFLARE_ROLE" = "ALL" ]; then
    safe_mount "$OUTPUT_IMAGE" "${NVFLARE_DATA_LABEL}" "${MOUNT_DIR}${NVFLARE_DATA_MOUNT}" || exit 1
fi

# Install NVFLARE
chroot "$MOUNT_DIR" /bin/bash -c "
    # Create NVFLARE user/group
    groupadd -r ${NVFLARE_GROUP}
    useradd -r -g ${NVFLARE_GROUP} -d ${NVFLARE_HOME} ${NVFLARE_USER}
    
    # Install NVFLARE
    ${VENV_PATH}/bin/pip install nvflare==${NVFLARE_VERSION}
    
    # Setup directories
    mkdir -p ${NVFLARE_HOME}
    chown -R ${NVFLARE_USER}:${NVFLARE_GROUP} ${NVFLARE_HOME}
"

# Create environment setup script
cat > "${MOUNT_DIR}${NVFLARE_HOME}/env.sh" << EOF
#!/bin/bash
export PYTHONPATH="${VENV_PATH}/lib/python${PYTHON_VERSION}/site-packages"
export PATH="${VENV_PATH}/bin:\$PATH"
EOF

chmod +x "${MOUNT_DIR}${NVFLARE_HOME}/env.sh"

# Create directories based on role
create_nvflare_dirs() {
    local role="$1"
    
    # Root Partition (p3) - Core components
    mkdir -p "${MOUNT_DIR}${NVFLARE_HOME}"
    mkdir -p "${MOUNT_DIR}${VENV_PATH}"
    chown -R ${NVFLARE_USER}:${NVFLARE_GROUP} "${MOUNT_DIR}${NVFLARE_HOME}"

    # Config Partition (p4) - Read-only configs
    mkdir -p "${MOUNT_DIR}${NVFLARE_STARTUP_DIR}"
    mkdir -p "${MOUNT_DIR}${NVFLARE_SITE_CONF_DIR}"
    # For server, also create job store key directory
    if [ "$role" = "SERVER" ] || [ "$role" = "ALL" ]; then
        mkdir -p "${MOUNT_DIR}${NVFLARE_JOB_STORE_KEY}"
    fi
    chown -R ${NVFLARE_USER}:${NVFLARE_GROUP} "${MOUNT_DIR}/opt/nvflare/config"

    # Dynamic Partition (p5) - Writable workspace
    mkdir -p "${MOUNT_DIR}${NVFLARE_WORKSPACE}"
    mkdir -p "${MOUNT_DIR}${NVFLARE_LOG_DIR}"
    # For server, create job store directory
    if [ "$role" = "SERVER" ] || [ "$role" = "ALL" ]; then
        mkdir -p "${MOUNT_DIR}${NVFLARE_JOB_STORE_DIR}"
    fi
    chown -R ${NVFLARE_USER}:${NVFLARE_GROUP} "${MOUNT_DIR}/opt/nvflare/dynamic"
    
    # Data Partition (p6) - Client data access
    if [ "$role" = "CLIENT" ] || [ "$role" = "ALL" ]; then
        mkdir -p "${MOUNT_DIR}${NVFLARE_DATA_DIR}"
        chown -R ${NVFLARE_USER}:${NVFLARE_GROUP} "${MOUNT_DIR}/opt/nvflare/data"
    fi
}

# Create directories based on role
create_nvflare_dirs "${NVFLARE_ROLE}"

# Cleanup
guestunmount "${MOUNT_DIR}/opt/nvflare/data" 2>/dev/null || true
guestunmount "${MOUNT_DIR}/opt/nvflare/dynamic"
guestunmount "${MOUNT_DIR}/opt/nvflare/config"
guestunmount "$MOUNT_DIR"
rmdir "$MOUNT_DIR" 