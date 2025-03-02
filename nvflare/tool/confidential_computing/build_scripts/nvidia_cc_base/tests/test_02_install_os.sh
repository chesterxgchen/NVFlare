#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"
source "${SCRIPT_DIR}/../config/partition.conf"
source "${SCRIPT_DIR}/../config/security.conf"
source "${SCRIPT_DIR}/scripts/common/security_hardening.sh"

test_os_installation() {
    local test_dir=$(mktemp -d)
    
    # Mount image
    guestmount -a "$OUTPUT_IMAGE" -i "$test_dir"
    
    # Test required packages
    local required_packages=(
        "cryptsetup"
        "cryptsetup-bin"
        "cryptsetup-initramfs"
        "tpm2-tools"
        "veritysetup"
    )

    for pkg in "${required_packages[@]}"; do
        if ! chroot "$test_dir" dpkg -l | grep -q "^ii.*$pkg"; then
            error "Required package '$pkg' not installed"
        fi
    done
    
    # Test OS version
    if ! grep -q "VERSION=\"$OS_VERSION\"" "${test_dir}/etc/os-release"; then
        error "Wrong OS version installed"
    fi
    
    # Test locale settings
    if ! grep -q "LANG=$LANGUAGE" "${test_dir}/etc/default/locale"; then
        error "Wrong locale configured"
    fi
    
    # Test timezone
    if [ "$(readlink -f ${test_dir}/etc/localtime)" != "/usr/share/zoneinfo/$TIMEZONE" ]; then
        error "Wrong timezone configured"
    fi
    
    # Test CC user/group
    if ! grep -q "^$CC_GROUP:" "${test_dir}/etc/group"; then
        error "CC group not created"
    fi
    if ! grep -q "^$CC_USER:" "${test_dir}/etc/passwd"; then
        error "CC user not created"
    fi
    
    # Test grub configuration
    if ! grep -q "GRUB_TIMEOUT=0" "${test_dir}/etc/default/grub"; then
        error "Grub not configured properly"
    fi
    
    # Test disabled services
    for service in "${SYSTEM_SERVICES_DISABLE[@]}"; do
        if [ -f "${test_dir}/etc/systemd/system/$service.service" ]; then
            error "Service $service not disabled"
        fi
    done
    
    # Test swap disabled
    if grep -q "swap" "${test_dir}/etc/fstab"; then
        error "Swap not disabled"
    fi
    
    # Test kernel modules
    for module in "${KERNEL_MODULES_DISABLE[@]}"; do
        if ! grep -q "blacklist $module" "${test_dir}/etc/modprobe.d/blacklist-cc.conf"; then
            error "Kernel module $module not blacklisted"
        fi
    done
    
    # Test secure directories
    for dir_config in "${SECURE_DIRS[@]}"; do
        IFS=':' read -r dir owner group mode <<< "$dir_config"
        if [ ! -d "${test_dir}${dir}" ]; then
            error "Secure directory $dir not found"
        fi
        if [ "$(stat -c %a ${test_dir}${dir})" != "$mode" ]; then
            error "Directory $dir has wrong permissions"
        fi
    done
    
    # Test kernel parameters
    if ! grep -q "kernel.modules_disabled = 1" "${test_dir}/etc/sysctl.d/99-cc-secure.conf"; then
        error "Kernel hardening not configured"
    fi
    
    # Test TEE memory setup
    if [ ! -d "${test_dir}${TEE_MEMORY_PATH}" ]; then
        error "TEE memory path not created"
    fi
    if [ "$(stat -c %a ${test_dir}${TEE_MEMORY_PATH})" != "700" ]; then
        error "TEE memory path has wrong permissions"
    fi
    
    # Cleanup
    guestunmount "$test_dir"
    rm -rf "$test_dir"
}

# Run tests
test_os_installation 