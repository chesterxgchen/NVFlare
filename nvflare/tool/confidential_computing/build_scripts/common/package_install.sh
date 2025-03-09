#!/bin/bash

source "$(dirname "${BASH_SOURCE[0]}")/utils.sh"

# Install wheels from a directory
install_wheels() {
    local target_dir="$1"

    if [[ ! -d "${target_dir}" ]]; then
        log_error "Wheels directory not found: ${target_dir}"
        return 1
    fi

    log_info "Installing wheels from ${target_dir}..."

    # Find and install all wheels in offline mode
    if ! find "${target_dir}" -name "*.whl" | xargs pip install --no-index --find-links="${target_dir}"; then
        log_error "Failed to install wheels from ${target_dir}"
        return 1
    fi

    log_info "Wheels installed successfully"
    return 0
}

# Install startup kit with verification
install_tar_package() {
    local mount_point="$1"
    local kit_path="$2"
    local install_path="$3"

    local kit_file="${mount_point}${kit_path}"
    local target_dir="${mount_point}${install_path}"

    # Determine tar flags based on file extension
    local tar_flags="xf"
    case "${kit_file,,}" in  # Convert to lowercase for comparison
        *.tar.gz|*.tgz)
            tar_flags="xzf"
            ;;
        *.tar.bz2|*.tbz2)
            tar_flags="xjf"
            ;;
        *.tar.xz|*.txz)
            tar_flags="xJf"
            ;;
    esac

    # Verify startup kit and hash
    check_file "${kit_file}" || return 1
    check_file "${kit_file}.sha512" || return 1

    # Verify hash
    pushd "$(dirname ${kit_file})" > /dev/null
    if ! sha512sum -c "$(basename ${kit_file}).sha512"; then
        log_error "Startup kit hash verification failed"
        popd > /dev/null
        return 1
    fi
    popd > /dev/null

    # Create target directory
    check_directory "${target_dir}" || return 1

    # Extract startup kit
    log_info "Installing tar package to ${target_dir} using tar ${tar_flags}..."
    if ! tar "${tar_flags}" "${kit_file}" -C "${target_dir}"; then
        log_error "Failed to extract startup kit"
        return 1
    fi

    # Remove tar file after successful extraction
    rm -f "${kit_file}" || {
        log_warning "Failed to remove startup kit tar file: ${kit_file}"
    }

    # Verify installation
    if [[ ! -f "${target_dir}/startup.sh" ]]; then
        log_error "Startup kit installation verification failed"
        return 1
    fi

    log_info "Startup kit extracted and installed successfully"
    log_info "Removed source tar file: ${kit_file}"
    return 0
}

 