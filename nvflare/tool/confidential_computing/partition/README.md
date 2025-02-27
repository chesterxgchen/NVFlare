# NVFLARE Partition Setup Tool

This tool helps set up secure partitions for NVFLARE in Confidential Computing environments, providing secure storage and runtime isolation for NVFLARE components.

## Overview

### Purpose
- Secure storage for NVFLARE components
- Runtime isolation between components
- Protection of sensitive data
- Integrity verification of critical files

## Requirements

### Hardware Requirements
- Running in a Confidential VM (AMD SEV-SNP or Intel TDX)
- Minimum 200GB available disk space
- Minimum 16GB RAM (for tmpfs)

### Software Requirements
- Ubuntu 20.04 or later
- Required packages:
  - cryptsetup
  - veritysetup
  - parted
  - systemd

### Access Requirements
- Root access
- Available block device for partitioning

### Development Requirements
- For testing:
  - bats (Bash Automated Testing System)
  - kcov (for coverage reporting)

## Security Risk Analysis

### Attack Surface Overview
```
┌──────────────────────────────────────────────────────┐
│                   Attack Surface                      │
│                                                      │
│    Runtime                     Storage               │
│  ┌──────────┐               ┌──────────────┐        │
│  │ Memory   │               │ Model Files  │        │
│  │ I/O Ops  │               │ Checkpoints  │        │
│  │ Network  │               │ Gradients    │        │
│  └──────────┘               └──────────────┘        │
│        │                           │                 │
│        └───────────────────────────┘                │
│                     ▼                               │
│              Host Monitoring                        │
└──────────────────────────────────────────────────────┘
```

### Memory Protection Analysis
```
┌────────────────────────────────────────────┐
│           Memory Attack Vectors            │
├────────────────┬───────────────────────────┤
│ Component      │ Protection Mechanism      │
├────────────────┼───────────────────────────┤
│ Runtime Memory │ CVM Memory Encryption     │
│ Swap Space     │ Disabled/Encrypted        │
│ I/O Buffers    │ Protected tmpfs          │
│ Temp Files     │ In-memory + Secure Wipe  │
└────────────────────────────────────────────┘
```

### Storage Protection Analysis
```
┌────────────────────────────────────────────┐
│           Storage Protection               │
│                                           │
│ Read-Only   ┌──────────┐   ┌──────────┐  │
│ Partitions  │dm-verity │   │  Hash    │  │
│             └──────────┘   │  Trees   │  │
│                            └──────────┘  │
│                                         │
│ Encrypted   ┌──────────┐   ┌──────────┐ │
│ Partitions  │  LUKS    │   │  CVM     │ │
│             │Encryption│   │  Keys    │ │
│             └──────────┘   └──────────┘ │
└────────────────────────────────────────────┘
```

### I/O Protection and Remaining Risks
```
┌──────────────────────────────────────────────────────┐
│                   I/O Operations                      │
│                                                      │
│    Protected                    Remaining Risks      │
│  ┌──────────┐                ┌──────────────┐       │
│  │Data      │◄─────────────► │Timing       │       │
│  │Content   │                │Analysis      │       │
│  └──────────┘                └──────────────┘       │
│                                                     │
│  ┌──────────┐                ┌──────────────┐       │
│  │Integrity │◄─────────────► │Access        │       │
│  │Checks    │                │Patterns      │       │
│  └──────────┘                └──────────────┘       │
│                                                     │
│  ┌──────────┐                ┌──────────────┐       │
│  │Data      │◄─────────────► │Size/Volume   │       │
│  │Encryption│                │Information   │       │
│  └──────────┘                └──────────────┘       │
└──────────────────────────────────────────────────────┘
```

### I/O Risk Details
```
┌──────────────────────────────────────────────────┐
│              I/O Attack Vectors                   │
├────────────────────┬─────────────────────────────┤
│ Protected          │ Still Vulnerable            │
├────────────────────┼─────────────────────────────┤
│ • Data content     │ • Operation timing          │
│ • Data integrity   │ • Access frequency          │
│ • Data at rest     │ • I/O block sizes          │
│ • Data in transit  │ • Operation patterns        │
└────────────────────────────────────────────────────┘
```

Even with dm-verity and LUKS:
1. **Timing Analysis**
   - When I/O operations occur
   - Frequency of operations
   - Duration of operations

2. **Pattern Analysis**
   - Read vs Write ratios
   - Sequential vs Random access
   - Operation clustering

3. **Volume Analysis**
   - Size of operations
   - Frequency of large transfers
   - Changes in I/O volume

### Side-Channel Attack Prerequisites
```
┌──────────────────────────────────────────────────────┐
│           Restricted Access Environment              │
│                                                      │
│ ┌────────────────┐          ┌────────────────┐      │
│ │   Physical     │──✗───────│  Co-Location   │      │
│ │   Access       │  blocked │  Impossible    │      │
│ └────────────────┘          └────────────────┘      │
│                                                      │
│ ┌────────────────┐          ┌────────────────┐      │
│ │    Network     │──only────│   Legitimate   │      │
│ │    Ports       │  path    │     APIs      │      │
│ └────────────────┘          └────────────────┘      │
└──────────────────────────────────────────────────────┘
```

### Practical Risk Assessment
```
┌──────────────────────────────────────────────────────┐
│              Access Control Model                     │
│                                                      │
│ External Access         │      Internal Protection   │
│ ┌──────────────┐       │      ┌──────────────┐      │
│ │ Network API  │       │      │ TEE Memory   │      │
│ │ Only        ├───────────────│ Encryption   │      │
│ └──────────────┘       │      └──────────────┘      │
│                        │                            │
│ ┌──────────────┐       │      ┌──────────────┐      │
│ │ No Physical  │       │      │ Full I/O     │      │
│ │ Access      │       │      │ Protection   │      │
│ └──────────────┘       │      └──────────────┘      │
└──────────────────────────────────────────────────────┘
```

### Mitigation Strategies
```
┌──────────────────────────────────────────────────┐
│            I/O Protection Layers                 │
│                                                 │
│ ┌─────────────┐    ┌─────────────┐            │
│ │ Randomized  │    │ Fixed-Size  │            │
│ │  Delays     │    │   Blocks    │            │
│ └─────────────┘    └─────────────┘            │
│                                               │
│ ┌─────────────┐    ┌─────────────┐           │
│ │  Batched    │    │   Dummy     │           │
│ │Operations   │    │Operations   │           │
│ └─────────────┘    └─────────────┘           │
└──────────────────────────────────────────────────┘
```

### Disk Encryption Stack
```
┌────────────────────────────────────────────┐
│              LUKS Structure                │
│                                           │
│ ┌──────────────────┐  ┌───────────────┐  │
│ │    LUKS Header   │  │  Encrypted    │  │
│ │ • Crypto params  │  │  Data Area    │  │
│ │ • Master key     │  │               │  │
│ │ • Key slots      │  │               │  │
│ └──────────────────┘  └───────────────┘  │
│            │                 ▲            │
│            │    dm-crypt    │            │
│            └────────────────┘            │
│                                          │
│        Device Mapper Framework           │
└────────────────────────────────────────────┘
```

LUKS provides:
- Standardized header format
- Multiple key slots
- Password/key management
- Salt and iteration count

While dm-crypt:
- Handles actual encryption
- Manages crypto operations
- Interfaces with block layer

### Risk Assessment and Mitigation

| Risk Category | Threat | Impact | Current Controls | Residual Risk |
|--------------|---------|---------|-----------------|---------------|
| Memory Exposure | Host memory dump | High | • CVM memory encryption<br>• No swap<br>• Secure tmpfs | Low |
| Storage Access | Disk access by host | High | • LUKS encryption<br>• dm-verity for integrity | Low |
| Key Management | Key extraction | Critical | • Keys in CVM memory<br>• Hardware-backed keys | Low |
| I/O Operations | Side-channel analysis | Low | • Network-only access<br>• TEE isolation<br>• No physical access | Negligible |
| Model Extraction | Checkpoint analysis | High | • Encrypted storage<br>• Secure deletion | Low |
| Runtime Inspection | Process debugging | High | • CVM isolation<br>• Memory protection | Low |

### Current Implementation Approach
```
┌─────────────────────────────────────────────────────┐
│                Protection Layers                     │
│                                                     │
│ ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │
│ │    CVM      │  │  Storage    │  │  Runtime    │  │
│ │ Protection  │  │ Protection  │  │ Protection  │  │
│ │ • Memory    │  │ • LUKS      │  │ • tmpfs    │  │
│ │ • Isolation │  │ • dm-verity │  │ • Wiping   │  │
│ └─────────────┘  └─────────────┘  └─────────────┘  │
└─────────────────────────────────────────────────────┘
```

### Limitations and Considerations

1. **VM-based TEE Limitations**:
   - ✅ Memory encryption
   - ✅ Memory integrity
   - ✅ VM isolation
   - ✅ I/O protection (Network-only access)
   - ❌ Side-channel protection

2. **Storage Protection Trade-offs**:
   - Performance vs. Security
   - Complexity vs. Usability
   - Recovery vs. Protection

3. **Residual Risks**:
   - Network-based attacks only
   - API-level security critical
   - Host OS level attacks

### Future Enhancements
```
┌────────────────────────────────────────────┐
│           Planned Improvements             │
│                                           │
│ ┌──────────────┐      ┌───────────────┐  │
│ │ I/O Pattern  │      │ Side-Channel  │  │
│ │ Obfuscation  │      │ Hardening     │  │
│ └──────────────┘      └───────────────┘  │
│                                          │
│ ┌──────────────┐      ┌───────────────┐  │
│ │   Secure     │      │   Runtime     │  │
│ │  Recovery    │      │  Attestation  │  │
│ └──────────────┘      └───────────────┘  │
└────────────────────────────────────────────┘
```

## Design Approach 

### Architecture
The partition tool creates and manages the following partitions:
- `root-fs`: Root filesystem (read-only, dm-verity protected)
  - Contains core NVFLARE binaries and libraries
  - contains application binaries and libraries 
  - Integrity protected using dm-verity
  - Size: 20G (configurable)

- `oem-launcher`: OEM launcher (read-only, dm-verity protected)
  - Contains OEM-specific launch scripts
  - Integrity protected using dm-verity
  - Size: 1G (configurable)

- `os-config`: OS configuration (read-only, dm-verity protected)
  - Contains system configuration files
  - Integrity protected using dm-verity
  - Size: 5G (configurable)

- `workspace`: Workspace (encrypted)
  - Runtime workspace for NVFLARE
  - key in TEE memory 
  - LUKS encrypted for data protection
  - Size: 50G (configurable)

- `job-store`: Job storage (encrypted)
  - Storage for job data and results
  - LUKS encrypted for data protection
  - Option 1: 
    LUKS model owner has key to decrypt for the final result
  - Option 2: 
    Job store is not encrypted, the final result is visible to the model owner
  - Size: 10G (configurable)

- `tmp-fs`: Temporary storage (in-memory)
  - Volatile storage for temporary data
  - Cleared on reboot
  - Size: 8G (configurable)

- swap is disabled in the kernel



## Installation

### Production Environment
1. Clone the repository:
```bash
git clone https://github.com/NVIDIA/NVFlare.git
cd NVFlare/nvflare/tool/confidential_computing/partition
```

2. Review and modify configuration:
```bash
vim config/partition.conf
```

3. Run installation:
```bash
sudo ./install.sh
```

### Development Environment
1. Set up test environment:
```bash
sudo apt-get update
sudo apt-get install -y bats cryptsetup veritysetup parted
```

2. Run with mock CVM:
```bash
MOCK_CVM=1 sudo ./install.sh
```

## Configuration

### Basic Configuration
The `partition.conf` file contains all configuration settings:

```bash
# Base paths
ROOT_MOUNT=/mnt/nvflare     # Base mount point
DEVICE=/dev/nvme0n1         # Target device

# Partition sizes and types
ROOT_FS_SIZE=20G
WORKSPACE_SIZE=50G
JOB_STORE_SIZE=100G
# ... see partition.conf for all options
```

### Advanced Configuration
```bash
# Encryption settings
CRYPT_CIPHER=aes-xts-plain64
CRYPT_KEYSIZE=512
CRYPT_HASH=sha256

# Verity settings
VERITY_HASH=sha256
VERITY_DATABLOCK=4096
VERITY_HASHBLOCK=4096

# Tmpfs settings
TMPFS_MODE=1777
TMPFS_UID=0
TMPFS_GID=0
```

## Usage

### Basic Usage
1. Start partition setup:
```bash
sudo systemctl start nvflare-partitions
```

2. Verify setup:
```bash
sudo verify_partitions.sh
```

3. Clean up when needed:
```bash
sudo cleanup_partitions.sh
```

### Advanced Usage
1. Manual partition setup:
```bash
sudo setup_partitions.sh
```

2. Check partition status:
```bash
sudo dmsetup status
sudo cryptsetup status workspace_crypt
```

3. View integrity hashes:
```bash
cat /mnt/nvflare/root.roothash
```

## Testing

### Unit Testing
For development/testing in non-CVM environments:

1. Install test dependencies:
```bash
sudo apt-get install bats
```

2. Run tests with mock CVM:
```bash
MOCK_CVM=1 ./run_tests.sh
```

### Integration Testing
1. Run full system test:
```bash
MOCK_CVM=1 sudo ./tests/integration_test.sh
```

2. View test coverage:
```bash
firefox coverage/merged/index.html
```

## Security Features

### Storage Security
- dm-verity for read-only partition integrity
  - Detects tampering with read-only partitions
  - Uses cryptographic hashes for verification

- LUKS encryption for sensitive data
  - Protects data at rest
  - Uses hardware-backed keys in CVM

- In-memory tmpfs for temporary data
  - No data persistence
  - Cleared on reboot

- Secure key management in CVM memory
  - Keys never leave CVM memory
  - Protected by hardware encryption

## Troubleshooting

Common issues:

1. "Not running in a Confidential VM"
   - Ensure you're running in a CVM
   - For testing, use MOCK_CVM=1
   - Check dmesg for CVM status

2. "Device not found"
   - Check DEVICE setting in partition.conf
   - Ensure device exists and is not in use
   - Run `lsblk` to list available devices

3. "Mount point already in use"
   - Run cleanup_partitions.sh first
   - Check for existing mounts
   - Run `mount | grep nvflare` to check mounts

4. "Encryption failed"
   - Check available memory for key generation
   - Verify LUKS support in kernel
   - Check cryptsetup version

5. "Verity setup failed"
   - Check dm-verity kernel module
   - Verify hash algorithm support
   - Check available disk space

## Contributing

### Development Workflow
1. Run tests before submitting changes:
```bash
./run_tests.sh
```

2. Add tests for new features
3. Update documentation as needed

### Code Style
- Follow Google Shell Style Guide
- Add comments for complex operations
- Include error handling

### Testing Requirements
- Add unit tests for new functions
- Update integration tests if needed
- Maintain test coverage above 80% 

### Attack Complexity Assessment

| Attack Requirements | Defense Mechanisms | Difficulty Level |
|---------------------|-------------------|------------------|
| Hardware expertise | TEE isolation | Very High |
| Physical access | Encrypted memory | Impossible* |
| Co-location | Cache isolation | Impossible* |
| Precise timing | Protected bus | Very High |
| Network access | API restrictions | Medium |
| Host OS privileges | VM isolation | High |

*In network-only access configuration

#### Defense in Depth
| Layer | Protection | Effectiveness |
|-------|------------|---------------|
| Physical | No direct access | Complete |
| Hardware | TEE/CVM isolation | Very High |
| Memory | Encryption + integrity | Very High |
| Storage | LUKS + dm-verity | Very High |
| Network | API-only access | High |
| Runtime | Process isolation | High |

#### Conclusion
- Attack surface limited to network API
- Physical attacks prevented by access control
- Side-channel attacks impractical without physical access
- Focus should be on API security and network protection 