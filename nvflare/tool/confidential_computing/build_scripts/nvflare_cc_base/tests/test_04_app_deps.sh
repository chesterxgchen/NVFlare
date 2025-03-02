#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../config/nvflare.conf"
source "${SCRIPT_DIR}/../../nvidia_cc_base/scripts/common/common.sh"

# Test application dependencies
test_app_deps() {
    local image="$OUTPUT_IMAGE"
    local mount_dir="/tmp/nvflare_test"
    
    # Skip if no requirements file
    if [ ! -f "${APP_REQUIREMENTS}" ]; then
        log "No application requirements file, skipping test"
        return 0
    }
    
    mkdir -p "$mount_dir"
    
    # Mount root partition
    guestmount -a "$image" -m "label:${NVFLARE_ROOT_LABEL}" "$mount_dir"
    
    # Test each package
    while read -r line; do
        if [[ -n "$line" && "$line" != \#* ]]; then
            pkg=$(echo "$line" | cut -d'=' -f1 | cut -d'>' -f1 | cut -d'<' -f1 | tr -d ' ')
            if ! chroot "$mount_dir" /bin/bash -c "
                source ${VENV_PATH}/bin/activate
                python -c 'import ${pkg}' 2>/dev/null
            "; then
                error "Package $pkg import test failed"
                guestunmount "$mount_dir"
                return 1
            fi
        fi
    done < "${APP_REQUIREMENTS}"
    
    # Cleanup
    guestunmount "$mount_dir"
    rmdir "$mount_dir"
    return 0
}

test_app_deps 