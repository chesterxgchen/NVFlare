#!/bin/bash

set -e

# Source configs
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../config/partition.conf"
source "${SCRIPT_DIR}/../config/security.conf"
source "${SCRIPT_DIR}/common.sh"
source "${SCRIPT_DIR}/keys/key_service.sh"

# Install AMD SEV driver
chroot "$ROOT_MOUNT" /bin/bash -c "
    # Add AMD repository
    curl -fsSL https://repo.amd.com/gpg | gpg --dearmor -o /etc/apt/trusted.gpg.d/amd.gpg
    echo 'deb [arch=amd64] https://repo.amd.com/snp-guest-ubuntu2204 jammy main' > /etc/apt/sources.list.d/amd.list
    apt-get update

    # Install SNP guest driver
    DEBIAN_FRONTEND=noninteractive apt-get install -y snp-guest-dkms=${AMD_SEV_DRIVER}
    
    # Configure SNP guest
    echo 'options snp-guest mode=1' > /etc/modprobe.d/snp-guest.conf
"

# Install NVIDIA drivers
chroot "$ROOT_MOUNT" /bin/bash -c "
    # Add NVIDIA repository
    curl -fsSL https://nvidia.github.io/nvidia-docker/gpgkey | gpg --dearmor -o /etc/apt/trusted.gpg.d/nvidia.gpg
    curl -s -L https://nvidia.github.io/nvidia-docker/ubuntu22.04/nvidia-docker.list | tee /etc/apt/sources.list.d/nvidia-docker.list
    apt-get update

    # Install NVIDIA drivers and CUDA
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
        nvidia-driver-${NVIDIA_DRIVER} \
        nvidia-utils-${NVIDIA_DRIVER} \
        cuda-${NVIDIA_CUDA}

    # Configure NVIDIA driver
    echo 'options nvidia NVreg_EnableS0ixPowerManagement=1' > /etc/modprobe.d/nvidia.conf

    # Setup CUDA tmp directory
    mkdir -p /usr/local/cuda/tmp
    echo 'tmpfs /usr/local/cuda/tmp tmpfs size=2G 0 0' >> /etc/fstab
"

# Install NVIDIA CC driver ( This is a Mock scripts, need to be replaced with actual implementation) 
install_nvidia_cc_driver() {
    local root_mount="$1"
    log "Installing NVIDIA CC driver version ${NVIDIA_CC_DRIVER}"

    chroot "$root_mount" /bin/bash -c "
        # 1. Add NVIDIA CC repository
        curl -fsSL https://nvidia.github.io/confidential-computing/gpgkey | \
            gpg --dearmor -o /etc/apt/trusted.gpg.d/nvidia-cc.gpg
        
        # 2. Set up repository
        echo 'deb [arch=amd64] https://nvidia.github.io/confidential-computing/ubuntu22.04/apt-repo/ /' | \
            tee /etc/apt/sources.list.d/nvidia-cc.list
        apt-get update
        
        # 3. Install dependencies
        DEBIAN_FRONTEND=noninteractive apt-get install -y \
            nvidia-cc-runtime \
            nvidia-cc-tools \
            nvidia-cc-libs
            
        # 4. Install NVIDIA CC driver
        DEBIAN_FRONTEND=noninteractive apt-get install -y \
            nvidia-cc-driver-${NVIDIA_CC_DRIVER}
            
        # 5. Configure CC driver
        mkdir -p /etc/nvidia-cc
        cat > /etc/nvidia-cc/config <<EOF
NVIDIA_CC_VERSION=${NVIDIA_CC_DRIVER}
NVIDIA_CC_MODE=guest
NVIDIA_CC_ATTESTATION=snp
EOF
        
        # 6. Enable required services
        systemctl enable nvidia-cc
        systemctl enable nvidia-cc-attestation
        
        # 7. Load kernel modules
        echo 'nvidia-cc' >> /etc/modules-load.d/nvidia-cc.conf
        
        # 8. Set up security policies
        cat > /etc/nvidia-cc/security.conf <<EOF
# NVIDIA CC Security Configuration
CC_SECURE_BOOT=true
CC_MEMORY_ENCRYPTION=true
CC_ATTESTATION_REQUIRED=true
EOF
    "
    
    success "NVIDIA CC driver installation completed"
}

# Install NVIDIA CC components
install_nvidia_cc_driver "$ROOT_MOUNT" 

install_drivers() {
    local root_mount="$1"
    
    # Verify hardware binding before driver installation
    if ! verify_binding; then
        error "Hardware binding verification failed"
        return 1
    }

    # Install NVIDIA drivers with secure options
    chroot "$root_mount" /bin/bash -c "
        # Add secure boot signatures for drivers
        apt-get install -y nvidia-driver-${NVIDIA_DRIVER}-signed
        
        # Generate driver-specific keys
        generate_key 'nvidia_driver' 'driver'
        local driver_key=$(get_key 'nvidia_driver')
        
        # Sign driver modules with hardware-bound key
        for module in nvidia nvidia_uvm nvidia_drm; do
            sign-file sha512 \
                <(echo -n "$driver_key") \
                /lib/modules/$(uname -r)/updates/dkms/$module.ko
        done
    "
} 