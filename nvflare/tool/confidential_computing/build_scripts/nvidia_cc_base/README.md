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

### Image Management

### Base Image Resizing

The base image is distributed in a compact size for easy distribution. Before building additional layers or deploying, you may need to resize the image to accommodate your needs.

### Resizing QCOW2 Images

The `scripts/resize_qcow2.sh` script allows you to safely resize QCOW2 images and their partitions:

```bash
# View current partition layout
qemu-img info cc-base.qcow2

# Common resize workflows:

# 1. Prepare for layer building (increase root partition)
./scripts/resize_qcow2.sh -i 50G -s +20G cc-base.qcow2 3  # Extend root for package installation

# 2. Add storage for datasets/models
./scripts/resize_qcow2.sh -i +100G cc-base.qcow2 5        # Add 100G to dynamic partition

# 3. Minimal resize for testing
./scripts/resize_qcow2.sh -i 30G -s +5G cc-base.qcow2 3   # Small increase for testing
```

Partition Usage:
- `/boot` (p2): Boot files and kernels
- `root` (p3): OS, packages, and applications
- `dynamic` (p5): Data storage, datasets, models

Recommended Sizes:
```bash
# For development/testing
./scripts/resize_qcow2.sh -i 50G cc-base.qcow2 3   # Root: 30G, Dynamic: 15G

# For production/training
./scripts/resize_qcow2.sh -i 100G cc-base.qcow2 3  # Root: 40G
./scripts/resize_qcow2.sh -s +50G cc-base.qcow2 5  # Dynamic: 50G+
```

Detailed Examples:

1. Extend image and root partition
./scripts/resize_qcow2.sh -i 50G -s +10G cc-base.qcow2 3  # Resize to 50G, add 10G to root

2. Extend dynamic storage partition
./scripts/resize_qcow2.sh -i +20G cc-base.qcow2 5         # Add 20G to image and dynamic partition

3. Safe resize with backup and verification
./scripts/resize_qcow2.sh -b --verify -i 50G cc-base.qcow2 5

4. Preview changes without modifying
./scripts/resize_qcow2.sh -d -i +20G cc-base.qcow2 5      # Dry run
```

Options:
- `-i, --image-size SIZE`: New size for QCOW2 image (e.g., '50G' or '+20G')
- `-s, --size SIZE`: New size for partition (e.g., '+10G')
- `-b, --backup`: Create backup before resizing
- `-d, --dry-run`: Show what would be done without making changes
- `-v, --verbose`: Show detailed progress
- `-f, --force`: Skip safety checks
- `--verify`: Verify image after resize

Supported Partitions:
- `2`: /boot partition
- `3`: root partition (encrypted)
- `5`: dynamic partition (encrypted)

Notes:
- Always backup important data before resizing
- Use `-v` for detailed progress information
- Partitions 1 (EFI) and 4 (config) cannot be resized
- Root and dynamic partitions are LUKS encrypted
- Resize before building additional layers
- Consider future storage needs when resizing
- Dynamic partition can be resized again later

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

Copyright (c) 2025, NVIDIA Corporation. All rights reserved. 