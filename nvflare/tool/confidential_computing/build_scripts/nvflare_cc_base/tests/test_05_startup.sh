#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../config/nvflare.conf"
source "${SCRIPT_DIR}/../../nvidia_cc_base/scripts/common/common.sh"

# Test startup configuration
test_startup() {
    local image="$OUTPUT_IMAGE"
    local mount_dir="/tmp/nvflare_test"
    
    mkdir -p "$mount_dir"
    
    # Mount config partition
    guestmount -a "$image" -m "label:${NVFLARE_CONFIG_LABEL}" "$mount_dir"
    
    # Check startup directory exists
    if [ ! -d "${mount_dir}${NVFLARE_STARTUP_DIR}" ]; then
        error "Startup directory not found"
        guestunmount "$mount_dir"
        return 1
    fi
    
    # Check key startup files based on role
    case "${NVFLARE_ROLE}" in
        SERVER)
            if [ ! -f "${mount_dir}${NVFLARE_STARTUP_DIR}/fed_server.json" ]; then
                error "Server configuration not found"
                guestunmount "$mount_dir"
                return 1
            fi
            ;;
        CLIENT)
            if [ ! -f "${mount_dir}${NVFLARE_STARTUP_DIR}/fed_client.json" ]; then
                error "Client configuration not found"
                guestunmount "$mount_dir"
                return 1
            fi
            ;;
    esac
    
    # Check permissions
    local perms=$(stat -c "%a" "${mount_dir}${NVFLARE_STARTUP_DIR}")
    if [ "$perms" != "550" ]; then
        error "Incorrect startup directory permissions: $perms"
        guestunmount "$mount_dir"
        return 1
    fi
    
    # Cleanup
    guestunmount "$mount_dir"
    rmdir "$mount_dir"
    return 0
}

test_startup 