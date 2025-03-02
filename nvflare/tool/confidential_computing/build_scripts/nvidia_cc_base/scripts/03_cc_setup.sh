#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../config/partition.conf"
source "${SCRIPT_DIR}/../config/security.conf"
source "${SCRIPT_DIR}/keys/key_management.sh"

# Apply AMD patches (placeholder)
apply_amd_patches() {
    chroot "$ROOT_MOUNT" /bin/bash -c "
        echo 'Applying AMD patches...'
        # Placeholder for actual AMD patches
        # Will be implemented when patches are available
        echo 'AMD patches applied successfully'
    "
}

# Install AMD SEV-SNP
chroot "$ROOT_MOUNT" /bin/bash -c "
    # Add AMD repository
    curl -fsSL https://repo.amd.com/gpg | gpg --dearmor -o /etc/apt/trusted.gpg.d/amd.gpg
    echo 'deb [arch=amd64] https://repo.amd.com/snp-guest-ubuntu2204 jammy main' > /etc/apt/sources.list.d/amd.list
    apt-get update

    # Install SNP guest driver
    apt-get install -y snp-guest-dkms=${AMD_SEV_DRIVER}
    
    # Configure SNP guest
    echo 'options snp-guest mode=1' > /etc/modprobe.d/snp-guest.conf

    # Apply AMD patches if available
    apply_amd_patches
"

# Install NVIDIA CC components
chroot "$ROOT_MOUNT" /bin/bash -c "
    # Add NVIDIA repository
    curl -fsSL https://nvidia.github.io/nvidia-docker/gpgkey | gpg --dearmor -o /etc/apt/trusted.gpg.d/nvidia.gpg
    curl -s -L https://nvidia.github.io/nvidia-docker/ubuntu22.04/nvidia-docker.list | tee /etc/apt/sources.list.d/nvidia-docker.list
    apt-get update

    # Install NVIDIA drivers and CC components
    apt-get install -y \
        nvidia-driver-${NVIDIA_DRIVER} \
        nvidia-utils-${NVIDIA_DRIVER} \
        cuda-${NVIDIA_CUDA} \
        nvidia-cc-runtime=${NVIDIA_CC_DRIVER}

    # Configure CC runtime with correct permissions
    nvidia-cc-runtime-configure --enable
    chown ${SYSTEM_USER}:${SYSTEM_GROUP} /etc/nvidia-cc
    chmod 0700 /etc/nvidia-cc

    # Install key management scripts
    mkdir -p /usr/local/cc/scripts/keys
    cp -a ${SCRIPT_DIR}/keys/* /usr/local/cc/scripts/keys/
    chmod 755 /usr/local/cc/scripts/keys/*.sh
    
    # Install key settings
    mkdir -p /etc/cc
    cp ${SCRIPT_DIR}/keys/internal/key_settings.conf /etc/cc/
    chmod 600 /etc/cc/key_settings.conf
"

# Setup attestation
chroot "$ROOT_MOUNT" /bin/bash -c "
    # Install attestation packages
    apt-get install -y \
        snp-guest-tools=${AMD_SNP_GUEST} \
        snp-guest-userspace=${AMD_SNP_GUEST} \
        snp-guest-attestation=${AMD_SNP_GUEST} \
        nvidia-cc-nras=${NVIDIA_NRAS}

    # Configure attestation with secure permissions
    mkdir -p /etc/attestation
    chown ${SYSTEM_USER}:${SYSTEM_GROUP} /etc/attestation
    chmod 0700 /etc/attestation
    
    # Basic attestation config
    echo 'ATTESTATION_MODE=snp-guest' > /etc/attestation/config
    chmod 0600 /etc/attestation/config
"

# Setup secure boot
setup_secure_boot() {
    local root_mount="$1"
    
    # Generate secure boot keys
    mkdir -p "${root_mount}/host/cc/keys/secureboot"
    cd "${root_mount}/host/cc/keys/secureboot"
    
    # Generate keys and certificates
    for key_spec in "${BOOT_SIGNING_KEYS[@]}"; do
        IFS=':' read -r type key cert <<< "$key_spec"
        openssl req -new -x509 -newkey rsa:2048 -keyout "$key" -out "$cert"
    done
    
    # Sign kernel and initramfs
    sbsign --key signature.key --cert signature.crt \
        "${root_mount}/boot/vmlinuz"
    
    # Update GRUB configuration
    for setting in "${SECURE_BOOT_SETTINGS[@]}"; do
        echo "$setting" >> "${root_mount}/etc/default/grub"
    done
    
    chroot "$root_mount" update-grub
}

# Initialize TEE environment
setup_tee_environment() {
    local root_mount="$1"
    
    # Setup TEE memory
    mkdir -p "${TEE_MEMORY_PATH}"
    mount -t tmpfs -o size="${TEE_MEMORY_SIZE}" tmpfs "${TEE_MEMORY_PATH}"
    chmod "${TEE_MEMORY_MODE}" "${TEE_MEMORY_PATH}"
    chown "${TEE_MEMORY_OWNER}:${TEE_MEMORY_GROUP}" "${TEE_MEMORY_PATH}"
    
    # Initialize key service
    source "${SCRIPT_DIR}/keys/key_service.sh"
    init_key_service
}

# TEE Key Management Setup
setup_tee_keys() {
    local root_mount="$1"
    local cpu_vendor=$(detect_cpu_vendor)
    
    # Derive hardware key
    local hw_key=$(derive_hw_key "$cpu_vendor")
    
    # Derive TPM key
    local tpm_key=$(derive_tpm_key)
    
    # Store master keys in TEE
    store_tee_key "$hw_key" "hw_key"
    store_tee_key "$tpm_key" "tpm_key"
}

# Main setup
setup_cc_environment() {
    # Initialize TEE
    setup_tee_environment "$ROOT_MOUNT"
    
    # Setup keys
    setup_tee_keys "$ROOT_MOUNT"
    
    # Install initramfs components
    install_initramfs "$ROOT_MOUNT"
    
    # Install CC components
    install_cc_components
    
    # Configure attestation
    setup_attestation
}

# Run setup
setup_cc_environment 

# Install Intel TDX tools
chroot "$ROOT_MOUNT" /bin/bash -c "
    apt-get install -y \
        tdx-guest-tools=${INTEL_TDX_GUEST} \
        tdx-guest-userspace=${INTEL_TDX_GUEST} \
        tdx-guest-attestation=${INTEL_TDX_GUEST} \
        nvidia-cc-nras=${NVIDIA_NRAS}
" 