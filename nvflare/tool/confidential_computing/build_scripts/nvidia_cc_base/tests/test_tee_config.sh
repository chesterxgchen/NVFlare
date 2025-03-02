#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"
source "${SCRIPT_DIR}/../config/tee.conf"
source "${SCRIPT_DIR}/scripts/common/security_hardening.sh"

test_tee_config() {
    local test_dir=$(mktemp -d)
    guestmount -a "$OUTPUT_IMAGE" -i "$test_dir"

    # Test TEE boot configuration
    test_tee_boot() {
        # Test GRUB configuration
        if ! grep -q "tee_enable=1" "${test_dir}/etc/default/grub"; then
            error "TEE not enabled in GRUB"
        fi

        # Test kernel command line
        case "$(detect_cpu_vendor)" in
            "amd")
                if ! grep -q "mem_encrypt=on" "${test_dir}/etc/default/grub"; then
                    error "AMD memory encryption not enabled"
                fi
                ;;
            "intel")
                if ! grep -q "tdx_guest=on" "${test_dir}/etc/default/grub"; then
                    error "Intel TDX guest not enabled"
                fi
                ;;
        esac
    }

    # Test TEE memory configuration
    test_tee_memory() {
        # Test memory limits
        if [ ! -f "${test_dir}/etc/security/limits.d/cc-memory.conf" ]; then
            error "TEE memory limits not configured"
        fi

        # Test memory isolation
        if ! grep -q "isolcpus=" "${test_dir}/etc/default/grub"; then
            error "CPU isolation not configured"
        fi
    }

    # Test TEE launch policy
    test_tee_policy() {
        # Test policy file
        if [ ! -f "${test_dir}/etc/cc/tee/launch_policy.json" ]; then
            error "TEE launch policy not found"
        fi

        # Test policy signature
        if [ ! -f "${test_dir}/etc/cc/tee/launch_policy.sig" ]; then
            error "TEE launch policy not signed"
        fi
    }

    # Run all tests
    test_tee_boot
    test_tee_memory
    test_tee_policy

    # Cleanup
    guestunmount "$test_dir"
    rm -rf "$test_dir"
}

# Run tests
test_tee_config 