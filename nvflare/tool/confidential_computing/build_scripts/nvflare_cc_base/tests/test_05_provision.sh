#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../config/nvflare.conf"
source "${SCRIPT_DIR}/../../nvidia_cc_base/scripts/common/common.sh"

# Test NVFLARE provisioning
test_provision() {
    local image="$OUTPUT_IMAGE"
    local mount_dir="/tmp/nvflare_test"
    
    mkdir -p "$mount_dir"
    
    # Mount config partition
    guestmount -a "$image" -m "label:${NVFLARE_CONFIG_LABEL}" "$mount_dir"
    
    # Check provision directory structure
    for dir in "config" "state" "state/site-1"; do
        if [ ! -d "${mount_dir}${PROVISION_DIR}/$dir" ]; then
            error "Missing provision directory: $dir"
            guestunmount "$mount_dir"
            return 1
        fi
    done
    
    # Check project file
    if [ ! -f "${mount_dir}${PROVISION_CONFIG_DIR}/project.yml" ]; then
        error "Project file not found"
        guestunmount "$mount_dir"
        return 1
    fi
    
    # Check role-specific files
    case "${NVFLARE_ROLE}" in
        SERVER|ALL)
            if [ ! -f "${mount_dir}${PROVISION_STATE_DIR}/site-1/startup/fed_server.json" ]; then
                error "Server configuration not found"
                guestunmount "$mount_dir"
                return 1
            fi
            ;;
        CLIENT|ALL)
            if [ ! -f "${mount_dir}${PROVISION_STATE_DIR}/site-1/startup/fed_client.json" ]; then
                error "Client configuration not found"
                guestunmount "$mount_dir"
                return 1
            fi
            ;;
    esac
    
    # Cleanup
    guestunmount "$mount_dir"
    rmdir "$mount_dir"
    return 0
}

test_provision 