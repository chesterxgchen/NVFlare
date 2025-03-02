#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK_DIR="$(mktemp -d)"

source "${SCRIPT_DIR}/../config/nvflare_cc_base/config/nvflare.conf"
source "${SCRIPT_DIR}/../config/nvflare_cc_base/config/security.conf"
source "${SCRIPT_DIR}/../config/nvflare_cc_base/config/pex_build.conf"
source "${SCRIPT_DIR}/common/utils.sh"

# Validate Python version
validate_python_version() {
    local current_version=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')
    
    if ! python3 -c "import sys; from packaging import version; sys.exit(not (version.parse('${current_version}') in version.SpecifierSet('${PYTHON_VERSION}')))" ; then
        echo "ERROR: Python version ${current_version} not in required range ${PYTHON_VERSION}"
        return 1
    fi
}

# Function to install pex if not present
ensure_pex() {
    if ! command -v pex &> /dev/null; then
        echo "Installing pex..."
        python3 -m pip install pex
    fi
}

# Function to build PEX package
build_pex() {
    local package_name="$1"
    local output_dir="$2"
    local requirements="$3"  # optional

    check_command "pex" || {
        log_info "Installing pex..."
        pip install pex
    }

    log_info "Building PEX for ${package_name}..."
    
    if [[ -n "$requirements" ]]; then
        # Build from requirements
        pex . -r "$requirements" -o "${output_dir}/${package_name}.pex" --venv
    else
        # Build from package name
        pex "$package_name" -o "${output_dir}/${package_name}.pex" --venv
    fi

    # Generate hash
    pushd "$output_dir" > /dev/null
    sha512sum "${package_name}.pex" > "${package_name}.pex.sha512"
    popd > /dev/null

    log_info "PEX package built: ${output_dir}/${package_name}.pex"
    return 0
}

# Function to verify PEX package
verify_pex() {
    local pex_file="$1"
    
    echo "Verifying PEX package..."
    
    # Check hash
    if ! sha512sum -c "${pex_file}.sha512"; then
        echo "ERROR: PEX package hash verification failed"
        return 1
    fi

    # Test PEX execution
    if ! "${pex_file}" --version; then
        echo "ERROR: PEX package execution test failed"
        return 1
    }

    echo "PEX package verification successful"
    return 0
}

# Main execution
main() {
    if [[ $# -lt 2 ]]; then
        log_error "Usage: $0 <package_name> <output_dir> [requirements.txt]"
        return 1
    fi

    local package_name="$1"
    local output_dir="$2"
    local requirements="$3"

    check_directory "$output_dir" || return 1
    
    if ! build_pex "$package_name" "$output_dir" "$requirements"; then
        log_error "Failed to build PEX package"
        return 1
    fi

    return 0
}

# Run main if script is executed directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi 