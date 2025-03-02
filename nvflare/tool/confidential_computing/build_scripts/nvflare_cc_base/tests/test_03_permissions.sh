#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../config/nvflare.conf"
source "${SCRIPT_DIR}/../../nvidia_cc_base/scripts/common/common.sh"

# Test directory permissions
test_permissions() {
    local image="$OUTPUT_IMAGE"
    local mount_dir="/tmp/nvflare_test"
    
    mkdir -p "$mount_dir"
    
    # Mount and check each partition
    for label in "${NVFLARE_ROOT_LABEL}" "${NVFLARE_CONFIG_LABEL}" "${NVFLARE_DYNAMIC_LABEL}"; do
        guestmount -a "$image" -m "label:$label" "$mount_dir"
        
        # Check ownership
        if ! chroot "$mount_dir" /bin/bash -c "
            find /opt/nvflare -not -user ${NVFLARE_USER} -o -not -group ${NVFLARE_GROUP}
        " | grep -q .; then
            error "Found files with incorrect ownership in $label"
            guestunmount "$mount_dir"
            return 1
        fi
        
        guestunmount "$mount_dir"
    done
    
    rmdir "$mount_dir"
    return 0
}

test_permissions 