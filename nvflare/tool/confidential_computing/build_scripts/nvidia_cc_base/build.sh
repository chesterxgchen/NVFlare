#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/scripts/common/common.sh"
source "${SCRIPT_DIR}/config/partition.conf"
source "${SCRIPT_DIR}/config/qemu.conf"
source "${SCRIPT_DIR}/config/tee.conf"

log "Starting NVIDIA CC Image Build (Version: ${VERSION})"

# Create output directory
mkdir -p "${OUTPUT_DIR}"

# Build sequence
log "Starting build process..."

"${SCRIPT_DIR}/scripts/01_prepare.sh"         # Prepare environment
"${SCRIPT_DIR}/scripts/02_install_os.sh"      # Install base OS
"${SCRIPT_DIR}/scripts/03_drivers.sh"         # Install TEE drivers
"${SCRIPT_DIR}/scripts/04_cc_setup.sh"        # Setup TEE environment
"${SCRIPT_DIR}/scripts/05_cc_apps.sh"         # Install CC apps
"${SCRIPT_DIR}/scripts/06_partition.sh"       # Setup encrypted partitions
"${SCRIPT_DIR}/scripts/07_qemu_setup.sh"      # Setup QEMU and VM configuration

# Convert to QCOW2 format
log "Converting to QCOW2 format..."
qemu-img convert -f raw -O qcow2 \
  -o compat=1.1,compression_type=zlib \
  "${OUTPUT_DIR}/cc-base.img" \
  "${OUTPUT_DIR}/cc-base.qcow2"

# Generate installer
"${SCRIPT_DIR}/scripts/generate_installer.sh" "${OUTPUT_DIR}"

success "Build completed successfully"
log "Generated:"
log "  - Base Image: ${OUTPUT_DIR}/cc-base.qcow2"
log "  - Installer Package: ${OUTPUT_DIR}/${INSTALLER_NAME}.tar.gz" 