#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"
source "${SCRIPT_DIR}/../config/security.conf"
source "${SCRIPT_DIR}/scripts/common/security_hardening.sh"

test_security() {
    local test_dir=$(mktemp -d)
    guestmount -a "$OUTPUT_IMAGE" -i "$test_dir"

    # Test system hardening
    test_system_hardening() {
        # Test kernel modules
        for module in "${KERNEL_MODULES_DISABLE[@]}"; do
            if ! grep -q "blacklist $module" "${test_dir}/etc/modprobe.d/blacklist-cc.conf"; then
                error "Kernel module $module not blacklisted"
            fi
        done

        # Test system services
        for service in "${SYSTEM_SERVICES_DISABLE[@]}"; do
            if [ -f "${test_dir}/etc/systemd/system/$service.service" ]; then
                error "Service $service not disabled"
            fi
        done

        # Test kernel parameters
        local required_params=(
            "kernel.modules_disabled=1"
            "kernel.dmesg_restrict=1"
            "kernel.kexec_load_disabled=1"
            "kernel.yama.ptrace_scope=2"
        )
        for param in "${required_params[@]}"; do
            if ! grep -q "^$param" "${test_dir}/etc/sysctl.d/99-cc-secure.conf"; then
                error "Kernel parameter $param not set"
            fi
        done
    }

    # Test secure boot configuration
    test_secure_boot() {
        # Test UEFI secure boot
        if [ ! -d "${test_dir}/etc/secureboot" ]; then
            error "Secure boot not configured"
        fi

        # Test MOK enrollment
        if [ ! -f "${test_dir}/etc/secureboot/MOK.der" ]; then
            error "Machine Owner Key not found"
        fi
    }

    # Test audit configuration
    test_audit() {
        # Test audit rules
        if [ ! -f "${test_dir}/etc/audit/rules.d/cc.rules" ]; then
            error "CC audit rules not found"
        fi

        # Test audit service
        if ! chroot "$test_dir" systemctl is-enabled auditd | grep -q "enabled"; then
            error "Audit service not enabled"
        fi
    }

    # Run all tests
    test_system_hardening
    test_secure_boot
    test_audit

    # Cleanup
    guestunmount "$test_dir"
    rm -rf "$test_dir"
}

# Run tests
test_security 