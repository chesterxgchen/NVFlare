# NVIDIA Confidential Computing Base Image Builder

This tool creates a base image for NVIDIA Confidential Computing (CC) environments, with built-in TEE support, security hardening, and encrypted storage.

## Overview

The base image provides:
- TEE (Trusted Execution Environment) support for AMD SEV-SNP and Intel TDX
- QEMU/KVM virtualization support for confidential computing
- Secure encrypted storage with LUKS2
- Hardware-bound key management
- Security hardening features
- Validation and testing framework

## Prerequisites

- Ubuntu 22.04 or later
- 16GB RAM minimum
- TPM 2.0 support
- QEMU/KVM with confidential computing support
- One of:
  - AMD CPU with SEV-SNP support
  - Intel CPU with TDX support
- NVIDIA GPU (supported models)
- libvirt/virsh for VM management

## Build and Installation Process

### 1. Build Configuration

These settings must be configured before building the image:

1. Configure settings:
```bash
# Edit configuration files in config/
vim config/partition.conf    # Partition layout
vim config/security.conf     # Security settings
vim config/tee.conf         # TEE configuration
vim config/qemu.conf        # QEMU/virtualization settings
```

Key Configuration Files:

#### TEE Configuration (`config/tee.conf`)
```bash
# TEE Type Selection
TEE_TYPE="auto"         # Options: auto, sev-snp, tdx
TEE_POLICY="0x03"      # Security Levels:
                        # - "0x01": DEBUG (Not for production)
                        # - "0x02": Blocks key sharing
                        # - "0x03": Production mode
                        # - "0x07": Strict mode
```

#### QEMU Configuration (`config/qemu.conf`)
```bash
# VM Settings
VM_NAME="nvidia-cc-vm"
VM_MEMORY_SIZE="16G"   # Total VM memory
VM_CPUS="4"           # Number of vCPUs

# QEMU Settings
QEMU_MACHINE="q35"    # Required for TEE
QEMU_CPU_TYPE="host-passthrough"
```

### Runtime Configuration

These settings can be modified before starting the Confidential VM:

### Partition Management

After installation, certain partitions can be safely resized:

```bash
# View current partition layout
lsblk
fdisk -l /dev/target_device

# Partition Layout:
# p1: /boot/efi (fixed)
# p2: /boot      (resizable)
# p3: root       (resizable)
# p4: config     (fixed - contains critical measurements)
# p5: dynamic    (resizable - for additional storage)
```

#### Resizing Partitions

1. Resize /boot (p2):
```bash
# Extend partition
growpart /dev/target_device 2
# Resize filesystem
resize2fs /dev/target_devicep2
```

2. Resize root (p3):
```bash
# Extend LUKS container
cryptsetup resize root_crypt
# Resize LVM
pvresize /dev/mapper/root_crypt
lvextend -l +100%FREE /dev/mapper/vg_root-lv_root
# Resize filesystem
resize2fs /dev/mapper/vg_root-lv_root
```

3. Resize dynamic partition (p5):
```bash
# Extend partition
growpart /dev/target_device 5
# Extend LUKS container
cryptsetup resize dynamic_crypt
# Resize filesystem
resize2fs /dev/mapper/dynamic_crypt
```

Note: 
- /boot/efi (p1) and config (p4) partitions cannot be resized
- System should be in maintenance mode during resizing
- Always backup data before resizing

1. Memory Settings:
```bash
# In config/qemu.conf
VM_MEMORY_SIZE="32G"   # Increase VM memory if needed
```

2. CPU Settings:
```bash
# In config/qemu.conf
VM_CPUS="8"           # Adjust vCPU count
```

3. TEE Policy:
```bash
# In config/tee.conf
TEE_POLICY="0x07"     # Change security level if needed
```

Note: Changes to these settings require VM restart to take effect.

### 2. Build Process

2. Build the image:
```bash
./build.sh
```

The build process:
1. Prepares the environment
2. Installs base OS
3. Configures TEE support
4. Sets up encrypted partitions
5. Installs CC applications
6. Generates output files:
   - `output/cc-base.qcow2`: QEMU disk image with CC environment
   - `output/nvidia-cc-installer.tar.gz`: Installer package

### 3. Installation

1. Locate the installer package:
```bash
output/
├── cc-base.qcow2                      # QEMU disk image
├── nvidia-cc-installer.tar.gz         # Installer package
├── nvidia-cc-installer.tar.gz.sha256  # Checksum file
└── nvidia-cc-installer.tar.gz.asc     # GPG signature
```

2. Install:
```bash
tar xf nvidia-cc-installer.tar.gz
cd installer
./install.sh /dev/target_device
```

## Troubleshooting

### Common Issues

1. Configuration Errors:
```bash
# Check TEE support
dmesg | grep -i "sev\|tdx"

# Check QEMU/KVM status
systemctl status libvirtd
virsh list --all
```

2. Resource Issues:
```bash
# Check system memory
free -h

# Check disk space
df -h
```

3. TEE Setup Issues:
```bash
# Check CPU features
lscpu | grep -i "sev\|tdx"

# Check TPM status
tpm2_getcap -l
```

4. Installation Issues:
```bash
# Check installer logs
cat installer/build.log

# Verify device status
lsblk
```

## License

Copyright (c) 2024, NVIDIA Corporation. All rights reserved. 