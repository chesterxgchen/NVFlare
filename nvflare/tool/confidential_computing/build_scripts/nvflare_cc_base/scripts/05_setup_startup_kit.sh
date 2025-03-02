#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../config/nvflare.conf"
source "${SCRIPT_DIR}/../../nvidia_cc_base/scripts/common/common.sh"

# Validate startup source directory
if [ -z "${NVFLARE_STARTUP_SRC}" ]; then
    error "NVFLARE_STARTUP_SRC not set"
    exit 1
fi

if [ ! -d "${NVFLARE_STARTUP_SRC}" ]; then
    error "Startup directory not found: ${NVFLARE_STARTUP_SRC}"
    exit 1
fi

# Mount image
MOUNT_DIR="/tmp/nvflare_build"
mkdir -p "$MOUNT_DIR"

# Mount config partition (p4)
safe_mount "$OUTPUT_IMAGE" "${NVFLARE_CONFIG_LABEL}" "${MOUNT_DIR}${NVFLARE_CONFIG_MOUNT}" || exit 1

log "Setting up NVFLARE startup kit..."

# Step 1: Copy startup directory to config partition
mkdir -p "${MOUNT_DIR}${NVFLARE_STARTUP_DIR}"
cp -r "${NVFLARE_STARTUP_SRC}"/* "${MOUNT_DIR}${NVFLARE_STARTUP_DIR}/"

# Set permissions for startup directory
chown -R ${NVFLARE_USER}:${NVFLARE_GROUP} "${MOUNT_DIR}${NVFLARE_STARTUP_DIR}"
chmod -R 550 "${MOUNT_DIR}${NVFLARE_STARTUP_DIR}"  # Read-only for owner and group

# Step 2: Create site_conf directory and symbolic link
mkdir -p "${MOUNT_DIR}${NVFLARE_SITE_CONF_DIR}"
chown ${NVFLARE_USER}:${NVFLARE_GROUP} "${MOUNT_DIR}${NVFLARE_SITE_CONF_DIR}"
chmod 550 "${MOUNT_DIR}${NVFLARE_SITE_CONF_DIR}"

# Create symbolic link from startup/local to site_conf
if [ -d "${MOUNT_DIR}${NVFLARE_STARTUP_DIR}/local" ]; then
    ln -sf "${MOUNT_DIR}${NVFLARE_STARTUP_DIR}/local" "${MOUNT_DIR}${NVFLARE_SITE_CONF_DIR}"
else
    error "local directory not found in startup kit"
    guestunmount "${MOUNT_DIR}${NVFLARE_CONFIG_MOUNT}"
    rmdir "$MOUNT_DIR"
    exit 1
fi

# Verify setup
if [ ! -L "${MOUNT_DIR}${NVFLARE_SITE_CONF_DIR}/local" ]; then
    error "Failed to create symbolic link to local directory"
    guestunmount "${MOUNT_DIR}${NVFLARE_CONFIG_MOUNT}"
    rmdir "$MOUNT_DIR"
    exit 1
fi

# Cleanup
guestunmount "${MOUNT_DIR}${NVFLARE_CONFIG_MOUNT}"
rmdir "$MOUNT_DIR"

log "NVFLARE startup kit setup completed successfully"



