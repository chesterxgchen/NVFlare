 #!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../config/nvflare.conf"
source "${SCRIPT_DIR}/../../nvidia_cc_base/scripts/common/common.sh"

# Check if app requirements exist
if [ ! -f "${APP_REQUIREMENTS}" ]; then
    log "No application requirements found at ${APP_REQUIREMENTS}, skipping..."
    exit 0
fi

# Mount image
MOUNT_DIR="/tmp/nvflare_build"
mkdir -p "$MOUNT_DIR"

# Mount root partition
safe_mount "$OUTPUT_IMAGE" "${NVFLARE_ROOT_LABEL}" "$MOUNT_DIR" || exit 1

# Create app directory
mkdir -p "${MOUNT_DIR}${APP_INSTALL_DIR}"
chown ${NVFLARE_USER}:${NVFLARE_GROUP} "${MOUNT_DIR}${APP_INSTALL_DIR}"

# Copy requirements file
cp "${APP_REQUIREMENTS}" "${MOUNT_DIR}/tmp/app_requirements.txt"

# Install application dependencies
log "Installing application dependencies..."
chroot "$MOUNT_DIR" /bin/bash -c "
    set -e
    
    # Activate virtual environment
    source ${VENV_PATH}/bin/activate
    
    # Log requirements being installed
    echo 'Installing application packages:'
    cat /tmp/app_requirements.txt | while read -r line; do
        [[ -n \"\$line\" && \"\$line\" != \#* ]] && echo \"  \$line\"
    done
    
    # Install requirements
    pip install -r /tmp/app_requirements.txt
    
    # Verify installations
    echo 'Verifying installations:'
    while read -r line; do
        if [[ -n \"\$line\" && \"\$line\" != \#* ]]; then
            pkg=\$(echo \"\$line\" | cut -d'=' -f1 | cut -d'>' -f1 | cut -d'<' -f1 | tr -d ' ')
            if ! pip show \"\$pkg\" >/dev/null 2>&1; then
                echo \"Error: Package \$pkg not installed properly\"
                exit 1
            fi
            echo \"  \$pkg: \$(pip show \$pkg | grep ^Version | cut -d' ' -f2)\"
        fi
    done < /tmp/app_requirements.txt
"

# Cleanup
rm -f "${MOUNT_DIR}/tmp/app_requirements.txt"
guestunmount "$MOUNT_DIR"
rmdir "$MOUNT_DIR"

log "Application dependencies installed successfully"