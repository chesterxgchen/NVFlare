#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../config/nvflare_cc_base/config/nvflare.conf"
source "${SCRIPT_DIR}/common/utils.sh"

# Mount base image
mount_image() {
    local image="$1"
    local mount_point="$2"

    mkdir -p "$mount_point"
    guestmount -a "$image" -i "$mount_point"
}

# Main build process
main() {
    local base_image="nvflare_provisioned.qcow2"
    local mount_point="/mnt/nvflare_build"

    log_info "Starting NVFLARE provisioning build..."

    # Phase 1: Prepare and resize image
    export CURRENT_BUILD_PHASE="1"
    if ! "${SCRIPT_DIR}/01_prepare_image.sh"; then
        log_error "Image preparation failed"
        exit 1
    fi

    # Mount base image
    mount_image "$base_image" "$mount_point"

    # Phase 2: Install App packages
    export CURRENT_BUILD_PHASE="2"

    //TODO install app packages ( install wheel tar bar)

    # Phase 3: Install Startup Kit
    export CURRENT_BUILD_PHASE="3"
    if ! "${SCRIPT_DIR}/03_install_startup_kit.sh"; then
        log_error "Startup kit installation failed"
        guestunmount "$mount_point"
        exit 1
    fi

    # Unmount image
    guestunmount "$mount_point"
    rmdir "$mount_point"

    log_info "NVFLARE provisioning build completed successfully"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi 