# NVIDIA Confidential Computing Base Image Builder

This tool creates a secure base image for NVIDIA confidential computing and generates an installer script for deployment.

## Overview

The build process consists of four main phases:

### Build Process
Run the complete build process with:

```bash
sudo ./build.sh
```

Build phases:
1. **Base Image Creation**
   - Preparation (01_prepare.sh)
   - Validates prerequisites
   - Creates build environment
   - Sets up logging

2. **CC Components Installation**
   - CC Setup (03_cc_setup.sh)
   - Sets up confidential computing environment
   - Configures security settings

3. **Installer Generation**
   - Creates deployment script
   - Configures auto-device selection
   - Sets up installation validation

4. **Validation Testing**
   - Runs comprehensive test suite
   - Validates all components
   - Verifies security settings

## Output

## Installation
Deploys the built image to target hardware:

```bash
sudo ./cc_image_installer-{VERSION}.sh [-d device] [-i image_file] [-o output_dir]
```

Installation features:
- Automatic device selection based on rules (see device_auto_selection_rule.md)
- Support for both NVMe and SATA devices
- Safety checks for device selection
- Secure partition setup and encryption

## Configuration

Key configuration files:
- `config/partition.conf`: Partition layout and device settings
- `config/security.conf`: Security and encryption settings
- `config/tee.conf`: TEE memory configuration

## Device Selection

The installer supports two modes for device selection:
1. **Automatic** (default): Selects best device based on:
   - Device type (NVMe preferred)
   - Size requirements (minimum 32GB)
   - Availability (skips mounted devices)
   - Safety (avoids devices with OS)

2. **Manual**: User selects device when AUTO_SELECT=false

For detailed device selection rules, see [Device Auto-Selection Rules](device_auto_selection_rule.md)

## Testing

Run the test suite:
```bash
./tests/run_tests.sh
```

Tests cover:
- Build environment preparation
- OS installation
- CC component setup
- Driver installation
- Attestation configuration
- Partition setup
- Device selection
- Security settings

## Requirements

- Ubuntu 22.04 or later
- Root privileges for installation
- Minimum 32GB storage
- AMD SEV-capable CPU
- NVIDIA GPU (supported models)

## Security Features

- LUKS encryption for sensitive partitions
- dm-verity for read-only sections
- Secure boot configuration
- TEE memory isolation
- AMD SEV protection
- NVIDIA confidential computing safeguards

## Secure Key Management

### Available Options

1. Hardware-Bound Keys + Attestation (Current Implementation)
   - Keys derived from hardware features (CPU + TPM)
   - Protected by TEE memory encryption
   - Requires successful attestation
   - Advantages:
     * No keys stored on disk
     * Hardware-specific key derivation
     * Cross-boot data persistence
   - Implementation:
     * CPU features (AMD SEV/Intel TDX) for key derivation
     * TPM measurements for binding
     * TEE memory for runtime storage

2. TEE Memory Only (Alternative)
   - Keys generated and stored only in TEE memory
   - Lost on reboot
   - Maximum security but no data persistence

3. Remote Key Server (Future)
   - Keys stored on remote secure server
   - Provided after successful attestation
   - Advantages:
     * No local key storage
     * Central key management
     * Remote revocation

### Current Implementation Details

1. Key Generation:
   ```
   Hardware Features -> Hardware-bound Key -> Partition Keys
   ```

2. Runtime Protection:
   - Keys only exist in TEE memory
   - All encryption/decryption in TEE
   - Memory encrypted by CPU

3. Boot Process:
   ```
   1. TEE Initialization
   2. Hardware Measurements
   3. Key Derivation
   4. Partition Decryption
   ```

4. Security Boundaries:
   - Host OS: No access to keys or encrypted data
   - Physical Access: Cannot extract keys
   - Memory Attacks: Protected by TEE 