#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common/common.sh"
source "${SCRIPT_DIR}/common/security_hardening.sh"
source "${SCRIPT_DIR}/../config/partition.conf"
source "${SCRIPT_DIR}/../config/security.conf"

# Test installer package
test_installer() {
    local installer_path="$1"
    local test_dir=$(mktemp -d)
    
    log "Testing installer package..."
    
    # Extract installer
    tar xf "$installer_path" -C "$test_dir"
    
    # Verify package structure
    local required_files=(
        "installer/install.sh"
        "installer/validate.sh"
        "installer/$(basename $OUTPUT_IMAGE)"
        "installer/config/partition.conf"
        "installer/config/security.conf"
        "installer/config/tee.conf"
        "installer/validation/test_03_device.sh"
        "installer/validation/test_04_cc_setup.sh"
        "installer/validation/test_05_cc_apps.sh"
        "installer/validation/test_06_partition.sh"
        "installer/validation/test_security.sh"
        "installer/validation/common.sh"
    )
    
    for file in "${required_files[@]}"; do
        if [ ! -f "${test_dir}/${file}" ]; then
            error "Missing required file: ${file}"
        fi
    done
    
    # Verify file permissions
    if [ "$(stat -c %a ${test_dir}/installer/install.sh)" != "755" ]; then
        error "Wrong permissions on install.sh"
    fi
    if [ "$(stat -c %a ${test_dir}/installer/validate.sh)" != "755" ]; then
        error "Wrong permissions on validate.sh"
    fi
    
    # Verify signatures
    if [ -f "${installer_path}.asc" ]; then
        if ! gpg --verify "${installer_path}.asc" "$installer_path"; then
            error "Invalid installer signature"
        fi
    fi
    
    # Verify checksums
    if ! (cd "$(dirname $installer_path)" && sha256sum -c "${installer_name}.tar.gz.sha256"); then
        error "Checksum verification failed"
    fi
    
    # Test installer scripts
    (
        cd "$test_dir/installer"
        
        # Test validation script
        if ! ./validate.sh --dry-run; then
            error "Validation script test failed"
        fi
        
        # Test install script syntax
        if ! bash -n install.sh; then
            error "Install script syntax check failed"
        fi
        
        # Test install script with mock device
        if ! ./install.sh --test /dev/null; then
            error "Install script test failed"
        fi
    )
    
    # Cleanup
    rm -rf "$test_dir"
    
    success "Installer package tests passed"
}

# Generate installer package
generate_installer() {
    local output_dir="$1"
    local installer_name="${INSTALLER_NAME:-nvidia-cc-installer}"
    
    log "Generating installer package..."

    # Create temporary work directory
    local work_dir=$(mktemp -d)
    mkdir -p "${work_dir}/installer"

    # Copy image
    cp "${OUTPUT_DIR}/cc-base.qcow2" "${work_dir}/installer/"

    # Copy configuration files
    mkdir -p "${work_dir}/installer/config"
    cp "${SCRIPT_DIR}/../config/"*.conf "${work_dir}/installer/config/"

    # Copy validation scripts
    mkdir -p "${work_dir}/installer/validation"
    cp "${SCRIPT_DIR}/../tests/test_"*.sh "${work_dir}/installer/validation/"
    cp "${SCRIPT_DIR}/../tests/common.sh" "${work_dir}/installer/validation/"

    # Copy QEMU scripts
    mkdir -p "${work_dir}/installer/scripts/qemu"
    cp "${SCRIPT_DIR}/07_qemu_setup.sh" "${work_dir}/installer/scripts/qemu/"

    # Generate hardware validation script
    cat > "${work_dir}/installer/validate.sh" << 'EOF'
#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Run validation tests
validate() {
    # Check for test mode
    if [ "$1" = "--dry-run" ]; then
        # Skip actual hardware checks in test mode
        return 0
    fi

    # Check hardware requirements
    "${SCRIPT_DIR}/validation/test_03_device.sh"

    # Check TEE support
    "${SCRIPT_DIR}/validation/test_04_cc_setup.sh"

    # Verify security settings
    "${SCRIPT_DIR}/validation/test_security.sh"
}

validate "$@"
EOF
    chmod +x "${work_dir}/installer/validate.sh"

    # Generate install script
    cat > "${work_dir}/installer/install.sh" << 'EOF'
#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/config/partition.conf"
source "${SCRIPT_DIR}/config/qemu.conf"

# Install NVIDIA CC image
install() {
    # Test mode
    if [ "$1" = "--test" ]; then
        shift
        # Skip actual installation in test mode
        return 0
    fi

    # Validate environment
    "${SCRIPT_DIR}/validate.sh" || {
        echo "Validation failed"
        exit 1
    }

    # Setup QEMU environment
    "${SCRIPT_DIR}/scripts/qemu/07_qemu_setup.sh" || {
        echo "QEMU setup failed"
        exit 1
    }

    # Install image
    local target_device="$1"
    if [ -z "$target_device" ]; then
        echo "Usage: $0 <target_device>"
        exit 1
    fi

    # Convert and write image
    qemu-img convert -f qcow2 -O raw \
      "${SCRIPT_DIR}/cc-base.qcow2" "$target_device"

    # Setup partitions
    "${SCRIPT_DIR}/validation/test_06_partition.sh" || {
        echo "Partition setup failed"
        exit 1
    }

    # Verify installation
    "${SCRIPT_DIR}/validation/test_05_cc_apps.sh" || {
        echo "Application verification failed"
        exit 1
    }

    # Test QEMU setup
    "${SCRIPT_DIR}/validation/test_vm_config.sh" || {
        echo "VM configuration failed"
        exit 1
    }

    echo "Installation completed successfully"
}

install "$@"
EOF
    chmod +x "${work_dir}/installer/install.sh"

    # Create installer package
    cd "$work_dir"
    tar czf "${output_dir}/${installer_name}.tar.gz" installer/
    
    # Generate checksum
    cd "${output_dir}"
    sha256sum "${installer_name}.tar.gz" > "${installer_name}.tar.gz.sha256"

    # Sign installer
    if [ -f "${SCRIPT_DIR}/keys/signing.key" ]; then
        gpg --detach-sign --armor -u "${SIGNING_KEY}" "${installer_name}.tar.gz"
    fi

    # Cleanup
    rm -rf "$work_dir"

    success "Generated installer: ${output_dir}/${installer_name}.tar.gz"
    
    # Test the generated installer
    test_installer "${output_dir}/${installer_name}.tar.gz"
}

# Main
main() {
    local output_dir="${1:-$(pwd)}"
    mkdir -p "$output_dir"

    # Generate installer
    generate_installer "$output_dir"
}

main "$@" 