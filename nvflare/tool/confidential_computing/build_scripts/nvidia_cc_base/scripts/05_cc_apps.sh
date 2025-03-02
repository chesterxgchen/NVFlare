#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"
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
    
    # Create attestation directory
    mkdir -p "$install_dir"
    
    # Always install NVIDIA NRAS since this is NVIDIA CC
    install_nvidia_nras_sdk "$install_dir"
    
    # Install CPU-specific SDK
    case "$cpu_vendor" in
        "amd")
            install_amd_snp_sdk "$install_dir"
            ;;
        "intel")
            install_intel_ita_sdk "$install_dir"
            ;;
    esac
}

# Install CC applications
install_cc_apps() {
    local root_mount="$1"
    
    # Verify hardware binding before installing apps
    if ! verify_binding; then
        error "Hardware binding verification failed"
        return 1
    fi
    
    # Create CC application directories
    for dir_spec in "${CC_APP_DIRS[@]}"; do
        IFS=':' read -r dir owner perms <<< "$dir_spec"
        mkdir -p "${root_mount}${dir}"
        chown "$owner" "${root_mount}${dir}"
        chmod "$perms" "${root_mount}${dir}"
    done
    
    # Initialize CC app keys
    init_cc_app_keys
    
    # Create application directories
    local cc_mount="${root_mount}/etc/cc"
    mkdir -p "${cc_mount}/apps"
    mkdir -p "${cc_mount}/attestation"
    
    # Install attestation SDKs
    install_attestation_sdks "${cc_mount}/attestation"
    
    # Configure secure boot for attestation
    chroot "$root_mount" /bin/bash -c "
        # Update grub config for secure boot
        echo 'GRUB_CMDLINE_LINUX_DEFAULT=\"\$GRUB_CMDLINE_LINUX_DEFAULT mem_encrypt=on kvm_amd.sev=1\"' >> /etc/default/grub
        update-grub
    "
    
    # Install other CC applications here
    # TODO: Add other CC application installations
    
    success "CC applications installation complete"
}

# Run installation
install_cc_apps "$ROOT_MOUNT" 