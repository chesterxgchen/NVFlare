#!/bin/bash

source "$(dirname "${BASH_SOURCE[0]}")/utils.sh"

# Install PEX package with verification
install_pex_package() {
    local mount_point="$1"
    local pex_path="$2"
    local install_path="$3"

    local pex_file="${mount_point}${pex_path}"
    local target_dir="${mount_point}${install_path}"

    # Verify PEX file and hash
    check_file "${pex_file}" || return 1
    check_file "${pex_file}.sha512" || return 1

    # Verify hash
    pushd "$(dirname ${pex_file})" > /dev/null
    if ! sha512sum -c "$(basename ${pex_file}).sha512"; then
        log_error "PEX hash verification failed"
        popd > /dev/null
        return 1
    fi
    popd > /dev/null

    # Create directories
    check_directory "${target_dir}" || return 1

    # Install PEX
    log_info "Installing PEX to ${target_dir}..."
    
    # Install PEX package with venv
    if ! chroot "${mount_point}" /bin/bash -c "cd ${install_path} && python3 ${pex_path} --venv --install"; then
        log_error "PEX installation failed"
        return 1
    fi

    # Verify PEX execution
    if ! chroot "${mount_point}" /bin/bash -c "cd ${install_path} && python3 -m pex.cli --version"; then
        log_error "PEX installation verification failed"
        return 1
    fi

    log_info "PEX package installed successfully"
    return 0
}

# Install startup kit with verification
install_tar_package() {
    local mount_point="$1"
    local kit_path="$2"
    local install_path="$3"

    local kit_file="${mount_point}${kit_path}"
    local target_dir="${mount_point}${install_path}"

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
    log_info "Installing startup kit to ${target_dir}..."
    if ! tar xzf "${kit_file}" -C "${target_dir}"; then
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

 