#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/config/provision.conf"
source "${SCRIPT_DIR}/../common/utils.sh"

main() {
    local mount_point="$1"

    if [[ -z "$mount_point" ]]; then
        log_error "Mount point not specified"
        return 1
    fi

    if [[ ! -d "$mount_point" ]]; then
        log_error "Mount point does not exist: $mount_point"
        return 1
    fi

    log_info "Starting app executable installation..."

    if ! executable_install "$mount_point" "${APP_PEX_PATH}" "${APP_INSTALL_PATH}" "0500" "root:root"; then
        log_error "App executable installation failed"
        return 1
    fi

    log_info "App executable installation completed"
    return 0
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    if [[ $# -ne 1 ]]; then
        log_error "Usage: $0 <mount_point>"
        exit 1
    fi
    main "$@"
fi 