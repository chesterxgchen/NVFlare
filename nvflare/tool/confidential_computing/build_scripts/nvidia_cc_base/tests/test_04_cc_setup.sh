#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"
source "${SCRIPT_DIR}/../config/partition.conf"
source "${SCRIPT_DIR}/../config/security.conf"
source "${SCRIPT_DIR}/scripts/common/security_hardening.sh"

test_cc_setup() {
    local test_dir=$(mktemp -d)
    guestmount -a "$OUTPUT_IMAGE" -i "$test_dir"

    # Test AMD/Intel SDK installation
    test_vendor_sdk() {
        if grep -q "AMD" /proc/cpuinfo; then
            # Test AMD SNP SDK
            local amd_packages=(
                "snp-guest-tools=${AMD_SNP_GUEST}"
                "snp-guest-userspace=${AMD_SNP_GUEST}"
                "snp-guest-attestation=${AMD_SNP_GUEST}"
            )
            for pkg in "${amd_packages[@]}"; do
                if ! chroot "$test_dir" dpkg -l | grep -q "^ii.*$pkg"; then
                    error "AMD package '$pkg' not installed"
                fi
            done
        elif grep -q "Intel" /proc/cpuinfo; then
            # Test Intel TDX SDK
            local intel_packages=(
                "tdx-guest-tools=${INTEL_TDX_GUEST}"
                "tdx-guest-userspace=${INTEL_TDX_GUEST}"
                "tdx-guest-attestation=${INTEL_TDX_GUEST}"
            )
            for pkg in "${intel_packages[@]}"; do
                if ! chroot "$test_dir" dpkg -l | grep -q "^ii.*$pkg"; then
                    error "Intel package '$pkg' not installed"
                fi
            done
        fi
    }

    # Test attestation setup
    test_attestation() {
        # Test attestation SDKs installation
        local required_sdks=(
            "snp-guest-tools"
            "tdx-guest-tools"
            "nvidia-cc-nras"
        )
        
        for sdk in "${required_sdks[@]}"; do
            if ! chroot "$test_dir" dpkg -l | grep -q "^ii.*$sdk"; then
                error "Required SDK '$sdk' not installed"
            fi
        done
        
        # Test attestation configuration
        if [ ! -f "${test_dir}/etc/attestation/config" ]; then
            error "Attestation config not found"
        fi
        
        # Test attestation keys
        if [ ! -d "${test_dir}/etc/attestation/keys" ]; then
            error "Attestation keys directory not found"
        fi
        
        # Test attestation service
        if ! chroot "$test_dir" systemctl is-enabled nvidia-cc-attestation | grep -q "enabled"; then
            error "Attestation service not enabled"
        fi
    }

    # Test CC setup
    test_cc_components() {
        # Test CC directories
        local required_dirs=(
            "/etc/cc"
            "/etc/cc/keys"
            "/etc/cc/attestation"
            "${TEE_MEMORY_PATH}"
        )
        
        for dir in "${required_dirs[@]}"; do
            if [ ! -d "${test_dir}${dir}" ]; then
                error "Required directory '$dir' not found"
            fi
        done
        
        # Test CC configuration
        if [ ! -f "${test_dir}/etc/cc/config" ]; then
            error "CC configuration not found"
        fi

        # Test CC services
        local required_services=(
            "cc-attestation"
            "cc-key-service"
            "cc-tee-service"
        )
        
        for service in "${required_services[@]}"; do
            if ! chroot "$test_dir" systemctl is-enabled "$service" | grep -q "enabled"; then
                error "Required service '$service' not enabled"
            fi
        done

        # Test CC user/group setup
        if ! grep -q "^${CC_GROUP}:" "${test_dir}/etc/group"; then
            error "CC group not created"
        fi
        if ! grep -q "^${CC_USER}:" "${test_dir}/etc/passwd"; then
            error "CC user not created"
        fi
    }

    # Run all tests
    test_vendor_sdk
    test_attestation
    test_cc_components

    # Cleanup
    guestunmount "$test_dir"
    rm -rf "$test_dir"
}

# Run tests
test_cc_setup 