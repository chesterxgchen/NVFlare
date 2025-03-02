#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"
source "${SCRIPT_DIR}/test_utils/attestation_mock.sh"

test_attestation_setup() {
    local test_dir=$(mktemp -d)
    mount_image "$test_dir"

    # Test installed SDKs
    local sdks=($(get_attestation_sdks))
    for sdk in "${sdks[@]}"; do
        case "$sdk" in
            "snp-guest")
                if ! grep -q "${AMD_SNP_SDK_NAME}-${AMD_SNP_SDK_VERSION}" "${test_dir}/var/lib/dpkg/status"; then
                    error "AMD SNP guest tools not installed"
                fi
                ;;
            "nras")
                if ! grep -q "${NVIDIA_NRAS_SDK_NAME}-${NVIDIA_NRAS_SDK_VERSION}" "${test_dir}/var/lib/dpkg/status"; then
                    error "NVIDIA NRAS not installed"
                fi
                ;;
            "ita")
                if ! grep -q "${INTEL_ITA_SDK_NAME}-${INTEL_ITA_SDK_VERSION}" "${test_dir}/var/lib/dpkg/status"; then
                    error "Intel ITA SDK not installed"
                fi
                ;;
            "maa")
                if ! grep -q "${MS_MAA_SDK_NAME}-${MS_MAA_SDK_VERSION}" "${test_dir}/var/lib/dpkg/status"; then
                    error "Microsoft MAA SDK not installed"
                fi
                ;;
        esac
    done

    cleanup_test "$test_dir"
}

# Test dependency validation
test_attestation_dependencies() {
    # Test CPU vendor detection
    local cpu_vendor=$(detect_cpu_vendor)
    case "$cpu_vendor" in
        "amd")
            if ! check_amd_cpu_support; then
                error "AMD CPU does not support SNP"
            fi
            ;;
        "intel")
            if ! check_intel_tdx_support; then
                error "Intel CPU does not support TDX"
            fi
            ;;
        *)
            error "Unsupported CPU vendor: $cpu_vendor"
            ;;
    esac
    
    # NVIDIA CC driver should always be present
    if ! check_nvidia_cc_support; then
        error "NVIDIA CC driver not installed or incompatible"
    fi
}

# Run tests
test_attestation_dependencies
test_attestation_setup 