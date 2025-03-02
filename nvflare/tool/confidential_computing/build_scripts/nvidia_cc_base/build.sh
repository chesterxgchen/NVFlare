#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/scripts/common/common.sh"
source "${SCRIPT_DIR}/scripts/common/security_hardening.sh"

log "Starting NVIDIA CC Image Build (Version: ${VERSION})"

# Verify build environment
verify_installation || {
    error "Build environment verification failed"
    exit 1
}

# 1. Build Base Image Phase
log "Phase 1: Building Base Image"
"${SCRIPT_DIR}/scripts/01_prepare.sh"
"${SCRIPT_DIR}/scripts/02_install_os.sh"

# 2. CC Components Phase
log "Phase 2: Installing CC Components"
"${SCRIPT_DIR}/scripts/03_drivers.sh"         # Install TEE drivers
"${SCRIPT_DIR}/scripts/04_cc_setup.sh"        # Setup TEE and get keys
"${SCRIPT_DIR}/scripts/05_cc_apps.sh"         # Install CC apps
"${SCRIPT_DIR}/scripts/06_partition.sh"       # Setup encrypted partitions

# 3. Generate Installer Phase
log "Phase 3: Generating Installer"
"${SCRIPT_DIR}/scripts/generate_installer.sh"

# 4. Run Tests
log "Phase 4: Running Tests"
"${SCRIPT_DIR}/tests/run_tests.sh"

success "Build completed successfully!"
log "Generated:"
log "  - Image: ${OUTPUT_IMAGE}"
log "  - Installer: ${INSTALLER_NAME}" 