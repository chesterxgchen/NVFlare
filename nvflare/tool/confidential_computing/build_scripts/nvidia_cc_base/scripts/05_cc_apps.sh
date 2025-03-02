#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common/common.sh"
source "${SCRIPT_DIR}/common/security_hardening.sh"
source "${SCRIPT_DIR}/../config/partition.conf"
source "${SCRIPT_DIR}/../config/security.conf"
source "${SCRIPT_DIR}/lib/key_service.sh"

# Detect CPU vendor and features
detect_cpu_vendor() {
    if grep -q "AMD" /proc/cpuinfo; then
        echo "amd"
    elif grep -q "Intel" /proc/cpuinfo; then
        echo "intel"
    else
        error "Unsupported CPU vendor"
    fi
}

# Install AMD SNP SDK
install_amd_snp_sdk() {
    local install_dir="$1"
    log "Installing AMD SNP Guest SDK ${AMD_SNP_SDK_NAME} version ${AMD_SNP_SDK_VERSION}"
    
    chroot "$ROOT_MOUNT" /bin/bash -c "
        # Install in CC partition
        DEBIAN_FRONTEND=noninteractive apt-get install -y \
            --install-root=${install_dir} \
            ${AMD_SNP_SDK_NAME}=${AMD_SNP_SDK_VERSION}
    "
}

# Install NVIDIA NRAS SDK
install_nvidia_nras_sdk() {
    local install_dir="$1"
    log "Installing NVIDIA NRAS SDK ${NVIDIA_NRAS_SDK_NAME} version ${NVIDIA_NRAS_SDK_VERSION}"
    
    chroot "$ROOT_MOUNT" /bin/bash -c "
        # Install in CC partition
        DEBIAN_FRONTEND=noninteractive apt-get install -y \
            --install-root=${install_dir} \
            ${NVIDIA_NRAS_SDK_NAME}=${NVIDIA_NRAS_SDK_VERSION}
    "
}

# Install Intel ITA SDK
install_intel_ita_sdk() {
    local install_dir="$1"
    log "Installing Intel Trust Authority SDK ${INTEL_ITA_SDK_NAME} version ${INTEL_ITA_SDK_VERSION}"
    
    chroot "$ROOT_MOUNT" /bin/bash -c "
        # Install in CC partition
        DEBIAN_FRONTEND=noninteractive apt-get install -y \
            --install-root=${install_dir} \
            ${INTEL_ITA_SDK_NAME}=${INTEL_ITA_SDK_VERSION}
    "
}

# Install attestation SDKs based on CPU vendor
install_attestation_sdks() {
    local install_dir="$1"
    local cpu_vendor=$(detect_cpu_vendor)
    
    # Verify key management is initialized
    if ! verify_key_service_status; then
        error "Key management not initialized"
        return 1
    }
    
    # Create attestation directory
    mkdir -p "$install_dir"
    chmod 0700 "$install_dir"
    
    # Always install NVIDIA NRAS since this is NVIDIA CC
    install_nvidia_nras_sdk "$install_dir"
    
    # Install CPU-specific SDK
    case "$cpu_vendor" in
        "amd")
            verify_partition_encryption || return 1
            install_amd_snp_sdk "$install_dir"
            ;;
        "intel")
            verify_partition_encryption || return 1
            install_intel_ita_sdk "$install_dir"
            ;;
    esac
}

# Install CC applications
install_cc_apps() {
    local root_mount="$1"
    
    # Create app directories with secure permissions
    mkdir -p "${root_mount}/opt/cc/apps"
    chown root:root "${root_mount}/opt/cc/apps"
    chmod 0755 "${root_mount}/opt/cc/apps"
    
    # Verify app signatures before installation
    for app in "${CC_APPS[@]}"; do
        if ! verify_app_signature "$app"; then
            error "App signature verification failed: $app"
            return 1
        fi
    done
    
    # Install apps
    for app in "${CC_APPS[@]}"; do
        install_app "$app" "$root_mount"
    done
}

# Run installation
install_cc_apps "$ROOT_MOUNT" 