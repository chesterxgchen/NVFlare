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

## Building the Image

## Build Process

1. Configure settings:
```bash
# Edit configuration files in config/
vim config/partition.conf    # Partition layout
vim config/security.conf     # Security settings
vim config/tee.conf         # TEE configuration
vim config/qemu.conf        # QEMU/virtualization settings
```

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
   - `output/nvidia-cc-installer.tar.gz`: Installer package containing:
     * The disk image
     * Installation scripts
     * Validation tests
     * Configuration files

## Build-time Configuration

Key configurations that must be set in config/ before building:

### 1. TEE Configuration (`config/tee.conf`)
```bash
# TEE Type Selection
TEE_TYPE="auto"         # Will auto-detect SEV-SNP or TDX
TEE_POLICY="0x03"      # Default policy for memory encryption

# Memory Settings
TEE_MEMORY_SIZE="8G"   # Total encrypted memory for CVM
TEE_MEMORY_SLOTS="4"   # Number of memory slots

# Key Management
TEE_KEY_SETTINGS=(
  KEY_DIR="/etc/cc/keys"
  KEY_SIZE="4096"
  KEY_ALGO="rsa"
)
```

### 2. Security Configuration (`config/security.conf`)
```bash
# Encryption Settings
LUKS_CIPHER="aes-xts-plain64"
LUKS_KEY_SIZE="512"
LUKS_HASH="sha512"

# TPM Configuration
TPM_DEVICE="/dev/tpm0"
TPM_VERSION="2.0"
TPM_PCR="0,1,2,3,7"
```

### 3. QEMU Configuration (`config/qemu.conf`)
```bash
# QEMU Settings
QEMU_MACHINE="q35"
QEMU_CPU_TYPE="host-passthrough"
QEMU_FIRMWARE="/usr/share/OVMF/OVMF_CODE.fd"

# These will be configured during installation
GPU_SETTINGS_FILE="/etc/cc/qemu/gpu_settings"
NETWORK_SETTINGS_FILE="/etc/cc/qemu/network_settings"
```

### Build Validation

Verify your configuration before building:
```bash
# Check configuration syntax
./scripts/validate_config.sh

# Test configuration compatibility
./scripts/check_compatibility.sh

# Estimate resource requirements
./scripts/estimate_resources.sh
```

### Build Components

The installer package (`nvidia-cc-installer.tar.gz`) contains:
```bash
installer/
├── cc-base.qcow2            # QEMU disk image
├── install.sh               # Installation script
├── validate.sh              # Hardware validation
├── config/                  # Configuration files
│   ├── partition.conf
│   ├── security.conf
│   ├── tee.conf
│   └── qemu.conf
└── validation/              # Test scripts
    ├── test_03_device.sh
    ├── test_04_keys.sh
    ├── test_05_cc_apps.sh
    ├── test_06_partition.sh
    └── common.sh
```

The installer package provides:
- Self-contained installation
- Hardware validation
- Configuration verification
- Installation testing
- QEMU/KVM integration

## Runtime Configuration

Critical settings that can be modified in config files before CVM start:

### 1. TEE Memory Adjustment
```bash
# Modify TEE memory size in tee.conf
TEE_MEMORY_SIZE="16G"  # Must be power of 2MB for SEV-SNP
TEE_MEMORY_SLOTS="8"   # Increase if more memory needed
```

### 2. GPU Assignment
```bash
# Auto-detected during installation
# Can override in /etc/cc/qemu/gpu_settings:
NVIDIA_GPU_INDEX="0"     # Use first GPU
NVIDIA_GPU_MEMORY="8G"   # Reserved GPU memory
```

### 3. Network Configuration
```bash
# Auto-detected during installation
# Can override in /etc/cc/qemu/network_settings:
NETWORK_TYPE="bridge"    # bridge or nat
NETWORK_ISOLATION=true   # Enable network isolation
```

## Troubleshooting

### Build Issues

1. Configuration Errors:
```bash
# Check config syntax
./scripts/validate_config.sh

# View detailed config
./scripts/show_config.sh --verbose

# Test config compatibility
./scripts/check_compatibility.sh
```

2. Resource Issues:
```bash
# Check system requirements
./scripts/check_resources.sh

# Monitor build resources
./build.sh --monitor

# Clean build environment
./build.sh --clean
```

3. TEE Setup Issues:
```bash
# Verify CPU support
./scripts/check_tee_support.sh

# Test TEE configuration
./scripts/test_tee_config.sh

# Check TEE measurements
./scripts/verify_measurements.sh
```

### Runtime Issues

1. Hardware Validation Fails:
```bash
# Check TEE support
dmesg | grep -i "sev\|tdx"

# Verify TPM
tpm2_getcap -l

# Check detailed status
./scripts/check_hardware.sh --verbose
```

2. Key Generation Fails:
```bash
# Check TPM access
tpm2_pcrread sha256:0,1,2,3,4,5,6,7

# Verify TEE measurements
./tests/test_04_keys.sh

# Debug key generation
DEBUG=true ./scripts/generate_keys.sh
```

### Common Problems

1. Build Fails:
- Check system requirements
- Verify configuration syntax
- Clean build environment
- Check build logs

2. TEE Issues:
- Verify CPU support
- Check BIOS settings
- Update firmware
- Verify measurements

3. Performance Issues:
- Check resource allocation
- Verify NUMA configuration
- Monitor system metrics
- Adjust VM settings

## Installation

1. Locate the installer package in output/:
```bash
output/
├── cc-base.qcow2                      # QEMU disk image
├── nvidia-cc-installer.tar.gz         # Installer package
├── nvidia-cc-installer.tar.gz.sha256  # Checksum file
└── nvidia-cc-installer.tar.gz.asc     # GPG signature (if signed)
```

2. Verify the package:
```bash
# Verify checksum
sha256sum -c nvidia-cc-installer.tar.gz.sha256

# Verify signature (if available)
gpg --verify nvidia-cc-installer.tar.gz.asc nvidia-cc-installer.tar.gz
```

3. Extract and install:
```bash
tar xf nvidia-cc-installer.tar.gz
cd installer
./install.sh /dev/target_device
```

## Hardware Detection

The installer automatically detects and configures:

1. NVIDIA GPU:
- Detects available NVIDIA GPUs
- Identifies correct device paths
- Configures PCI passthrough

2. Network:
- Detects/creates bridge interfaces
- Finds available IP ranges
- Configures network isolation

3. TEE Environment:
- Auto-detects CPU vendor (AMD/Intel)
- Configures appropriate TEE mode
- Sets up memory encryption

## Installation Process

### Device Selection

The installer supports automatic device selection based on predefined rules:

1. Auto Selection Rules:
```bash
# Device priority (highest to lowest):
- NVMe devices
- SSD devices
- HDD devices

# Selection criteria:
- Device size (larger preferred)
- Device type (faster media preferred)
- Device availability (unmounted preferred)
```

2. Using Auto Selection:
```bash
# Enable auto selection
AUTO_SELECT=true ./install.sh

# Or specify device type preference
PREFER_NVME=true ./install.sh
PREFER_SSD=true ./install.sh
```

3. Manual Device Selection:
```bash
# List available devices
./install.sh --list-devices

# Install to specific device
./install.sh /dev/nvme0n1
```

4. Review Selection:
```bash
# Show selection process
DEBUG=true AUTO_SELECT=true ./install.sh

# Verify selected device
./install.sh --verify /dev/nvme0n1
```

1. Hardware Detection:
```bash
# Extract installer
tar xf nvidia-cc-installer.tar.gz
cd installer

# Run hardware detection (automatic)
./validate.sh
```

2. Review Configuration:
```bash
# Check detected hardware
cat /etc/cc/qemu/gpu_settings    # GPU configuration
cat /etc/cc/qemu/network_settings # Network configuration
```

3. Install System:
```bash
./install.sh /dev/target_device
```

4. Verify Installation:
```bash
# Check VM configuration
virsh list --all

# Verify GPU passthrough
lspci -v | grep -i nvidia

# Check network setup
brctl show
```

## Security Notes

1. Key Protection:
- Hardware keys are derived from CPU features
- Keys are stored in TEE memory only
- Key rotation is automated

2. Partition Security:
- Root and app partitions are encrypted
- Read-only configuration partition
- Dynamic partition for flexible storage

3. System Hardening:
- Secure boot enabled
- Kernel hardening
- Service minimization
- Audit logging

## Contributing

1. Testing:
- Add tests to appropriate test file
- Update test documentation
- Verify with dry-run mode

2. Features:
- Follow security guidelines
- Include validation tests
- Update documentation

## License

Copyright (c) 2024, NVIDIA Corporation. All rights reserved.

## Image Management

### Converting Image Formats
```bash
# Convert raw to qcow2
qemu-img convert -f raw -O qcow2 cc-base.img cc-base.qcow2

# Convert qcow2 to raw
qemu-img convert -f qcow2 -O raw cc-base.qcow2 cc-base.img

# Create compressed qcow2
qemu-img convert -f raw -O qcow2 -c cc-base.img cc-base.qcow2

# Resize image
qemu-img resize cc-base.qcow2 +10G
```

### Image Snapshots
```bash
# Create snapshot
qemu-img snapshot -c baseline cc-base.qcow2

# List snapshots
qemu-img snapshot -l cc-base.qcow2

# Revert to snapshot
qemu-img snapshot -a baseline cc-base.qcow2
```
