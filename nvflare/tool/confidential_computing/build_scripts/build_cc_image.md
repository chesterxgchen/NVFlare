# NVFLARE Confidential Computing Image Build Process

## Build Phases

### Stage 1: Base Security Image (nvidia_cc_base)

Base security features and OS hardening:

- System Configuration:
  - Minimal Ubuntu 22.04 base
  - TPM 2.0 support enabled
  - Secure boot configuration
  - SELinux/AppArmor profiles

- Storage Security:
  - LUKS2 encryption setup
  - dm-verity root verification
  - Secure partition layout
  - TPM-bound keys

- Network Configuration:
  - Base firewall rules (deny-all default)
  - Network interface restrictions (lo, eth0, ens*)
  - TCP/IP stack hardening
  - Essential services only

- Security Hardening:
  - Kernel module blacklisting
  - Sysctl security settings
  - Service minimization
  - Mount point restrictions
  - Memory protections

### Stage 2: NVFLARE Environment (nvflare_cc_base)

NVFLARE-specific configuration and security:

- Python Environment:
  - Python 3.9+ virtual environment
  - NVFLARE package installation
  - Dependencies in isolated env
  - Package verification

- NVFLARE Configuration:
  - Site-specific settings
  - Role-based configs (server/client)
  - Workspace initialization
  - Job store setup

- Network Security:
  - FL Ports: 8002 (training), 8003 (admin API)
  - SSHD disabled by default
  - Rate Limits: 
    - FL: 60 conns/min, 10 conns/IP
    - Admin: 30 conns/min, 2 conns/IP
  - TCP Tuning for FL:
    - Increased buffer sizes (16MB)
    - Optimized for FL workloads
  - Attestation Services:
    - Intel Trust Authority (9000/tcp)
    - AMD SNP Guest (9001/tcp)
    - Azure Attestation (9002/tcp)
    - NVIDIA Remote Attestation (9003/tcp)
  - Optional Services (Server Only):
    - System Monitoring (statsd)
    - ML Metrics (tensorboard/mlflow/wandb)

- Directory Structure:
  - /opt/nvflare/
    ├── venv/           # Python virtual environment
    ├── workspace/      # Runtime workspace (encrypted)
    ├── logs/          # Audit and app logs (encrypted)
    ├── config/        # Read-only configs (verity)
    └── data/          # Optional data mount (unencrypted)

### Stage 3: Provisioning (provision_build)

Final configuration and provisioning:

- Package Installation:
  - Application wheel packages
  - Custom dependencies
  - Site-specific tools

- Startup Configuration:
  - Startup kit installation
  - Site certificates/keys
  - Federation setup
  - Job templates

- Validation:
  - Package signature verification
  - Configuration validation
  - Security policy checks
  - Network testing

## Build Process

1. Build base security image:
```bash
cd nvidia_cc_base
./build.sh
```

2. Build NVFLARE environment:
```bash
cd nvflare_cc_base
./build.sh --base-image ../nvidia_cc_base/nvcc_image.qcow2
```

3. Build provisioned image:
```bash
cd provision_build
./build.sh --base-image ../nvflare_cc_base/nvflare_cc_base.qcow2
```

## Security Notes

- Each stage builds on security of previous stage
- All security-sensitive operations in encrypted storage
- Network restrictions increase with each stage
- Final image is fully locked down for production use

## Partition Overview

p1 (Boot):
- Contains: EFI System Partition, UEFI bootloader
- Protection: Secure boot signatures, TPM measurements
- Access: Host-visible, read-only after boot

p2 (Boot):
- Contains: Boot partition, kernel, initramfs
- Protection: dm-verity integrity verification
- Access: Host-visible, read-only

p3 (Root):
- Contains: Core installation, read-only components, workspace, logs
- Protection: LUKS encryption with system key
- Access: Guest-only after boot
- Security: RW,ENC (Static encryption with partition key)

p4 (Config):
- Contains: NVFLARE configs (startup, site_conf, job_store_key)
- Protection: dm-verity integrity verification
- Access: Guest-only, read-only
- Security: RO,DMV (Read-only with dm-verity)

p5 (Dynamic):
- Contains: Job store
- Protection: LUKS encryption with user-provided key
- Access: Guest-only read-write
- Security: RW,DENC (Dynamic encryption with user key)

p6 (Data):
- Contains: User data access
- Protection: Unencrypted
- Access: Guest read-only
- Security: RO (Runtime enforced)

## Key Design Elements

### Security Model
- Layered encryption (disk, memory, runtime)
- Hardware-based key derivation
- Network isolation per role

### Storage Layout
- Read-only system components
- Runtime-encrypted workspace
- Host-visible configuration

### Build Process
- Phase-gated builds with validation
- Package signature verification
- Automated testing for each phase 