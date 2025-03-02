## Key Management Design

### Overview

The key management system is designed to provide secure key storage and handling in a Confidential Computing environment, with a focus on hardware-bound keys and TEE (Trusted Execution Environment) protection.

```ascii
┌──────────────────────────────────────────────────┐
│                 Key Hierarchy                     │
│                                                  │
│    Hardware Key         TPM Key                  │
│         │                  │                     │
│         └──────┬──────────┘                     │
│                │                                 │
│          Master Key                             │
│                │                                │
│    ┌──────────┴──────────┐                     │
│    │                     │                     │
│ Partition Keys      Runtime Keys               │
│    │                     │                     │
│    │                     │                     │
│  LUKS              Application                 │
│ Volumes               Keys                     │
└──────────────────────────────────────────────────┘
```

### Key Types and Lifecycle

1. Hardware-Bound Keys
   ```ascii
   CPU Features (SEV/TDX) ──► Hardware Key ──► TEE Memory
                                    │
   TPM Measurements ────────► TPM Key ─┘
   ```
   - Generated from CPU-specific features (SEV-SNP/TDX)
   - Bound to hardware state and TPM measurements
   - Never stored on disk
   - Lost on power off (by design)

2. Partition Keys
   ```ascii
   Hardware Key + TPM Key ──► Master Key ──► Partition Keys
                                                │
                                          LUKS Volumes
   ```
   - Derived from hardware-bound keys
   - Used for LUKS encryption
   - Unique per partition
   - Stored only in TEE memory

### Implementation Components

1. key_management.sh
   - Core key derivation functions
   - Hardware binding implementation
   - TPM integration
   - Key generation logic

2. key_service.sh
   - Key storage management
   - TEE memory handling
   - Service initialization
   - Key lifecycle management

### Security Boundaries

```ascii
┌─────────────────────────────────────────────────────┐
│                  Security Domains                    │
│                                                     │
│ Host OS                │        Guest TEE            │
│                       │                             │
│ ┌─────────────┐      │      ┌─────────────┐        │
│ │ Block       │      │      │ Key         │        │
│ │ Devices     │◄─────┼─────►│ Service     │        │
│ └─────────────┘      │      └─────────────┘        │
│                      │            │                 │
│ ┌─────────────┐      │      ┌─────────────┐        │
│ │ LUKS        │◄─────┼─────►│ Key         │        │
│ │ Layer       │      │      │ Management  │        │
│ └─────────────┘      │      └─────────────┘        │
│                      │                             │
└─────────────────────────────────────────────────────┘
```

### Initramfs Integration

The initramfs integration is crucial for:

1. Early Boot Security
   - TEE initialization before root mount
   - Key service startup
   - Hardware key derivation

2. Root Encryption
   - LUKS key setup
   - Encrypted root partition mounting
   - Secure boot chain

```ascii
┌────────────────────────────────────────────┐
│            Boot Process                     │
│                                            │
│ UEFI ──► initramfs ──► TEE Init           │
│                           │                │
│                      Key Service           │
│                           │                │
│                    Mount Encrypted         │
│                      Volumes               │
│                           │                │
│                      Switch Root           │
└────────────────────────────────────────────┘
```

### Design Decisions

1. Hardware Binding
   - **Decision**: Use CPU features + TPM for key derivation
   - **Pro**: Strong hardware root of trust
   - **Con**: Keys lost on power off
   - **Mitigation**: Design for key regeneration

2. TEE Memory Storage
   - **Decision**: Store all keys in TEE memory only
   - **Pro**: Protected from host OS
   - **Con**: Memory overhead
   - **Mitigation**: Key cleanup when not needed

3. Key Hierarchy
   - **Decision**: Multi-level key derivation
   - **Pro**: Compartmentalization
   - **Con**: Complex key relationships
   - **Mitigation**: Clear key service API

### Security Considerations

1. Attack Vectors
   ```ascii
   ┌────────────────────────────────────────┐
   │         Attack Surface Analysis         │
   │                                        │
   │ Host OS ──► Limited                    │
   │ Memory  ──► Protected by TEE           │
   │ Storage ──► Encrypted                  │
   │ Network ──► N/A (local only)          │
   └────────────────────────────────────────┘
   ```

2. Potential Risks
   - Cold boot attacks (mitigated by TEE)
   - Key derivation timing attacks
   - TPM state manipulation
   - Initramfs tampering

3. Mitigations
   - Secure boot for initramfs
   - TEE memory encryption
   - Hardware-bound keys
   - Regular key rotation

### Performance Impact

1. Boot Time
   - Additional time for key derivation
   - TEE initialization overhead
   - LUKS volume mounting

2. Runtime
   - Minimal impact once keys are in TEE
   - Key service memory footprint
   - Encryption/decryption overhead

### Future Considerations

1. Key Backup
   - Secure key backup mechanisms
   - Recovery procedures
   - Key escrow options

2. Key Rotation
   - Automated key rotation
   - Version management
   - Migration procedures

3. Monitoring
   - Key usage tracking
   - Health checks
   - Audit logging

4. Remote Key Store Integration
   The remote key store option provides an alternative to local key derivation and storage.

   ```ascii
   ┌────────────────────────────────────────────────┐
   │            Remote Key Store Flow               │
   │                                               │
   │ Attestation ──► Remote Key ──► Local Cache   │
   │ Service          Store         (TEE Memory)   │
   │     │              │               │          │
   │     └──────────────┴───────────────┘         │
   │           Secure Channel (TLS)               │
   └────────────────────────────────────────────────┘
   ```
   - **Benefits**:
     - Centralized key management
     - Remote revocation capability
     - Audit trail for key access
     - No local key persistence needed
     - Simplified key rotation
     - Centralized policy enforcement
     - Real-time access control

   - **Challenges**:
     - Network dependency
     - Attestation requirements
     - Latency considerations
     - Offline operation needs
     - Initial trust establishment
     - Network security requirements
     - High availability needs

   - **Implementation Requirements**:
     - Attestation integration
     - Secure channel setup
     - Caching strategy
     - Failure handling
     - Offline fallback mechanism
     - Key synchronization protocol
     - Access control policies

   - **Operational Modes**:
     ```ascii
     ┌─────────────────────────────────────────┐
     │           Operational Modes             │
     │                                         │
     │ Online:                                 │
     │ Remote Store ──► TEE Cache ──► Usage   │
     │                                         │
     │ Offline:                                │
     │ Local Backup ──► TEE Cache ──► Usage   │
     │                                         │
     │ Emergency:                              │
     │ Recovery Key ──► TEE Cache ──► Usage   │
     └─────────────────────────────────────────┘
     ```

   - **Integration Points**:
     - Boot process integration
     - Attestation service hooks
     - Network security layer
     - Monitoring and logging
     - Recovery procedures

   - **Security Considerations**:
     - Remote attestation requirements
     - Network security protocols
     - Key revocation mechanisms
     - Audit logging requirements
     - Compliance considerations

### Conclusion

The implemented key management system provides a robust foundation for securing sensitive data in a Confidential Computing environment. The design prioritizes security through hardware binding and TEE protection, while maintaining usability and performance considerations.

The initramfs integration ensures a secure boot chain and early availability of key services, which is crucial for encrypted root partition support and overall system security.

### TEE Cross-Boot Data Persistence

#### Overview

```ascii
┌──────────────────────────────────────────────────┐
│           TEE Data Persistence Model             │
│                                                  │
│    Hardware State        TPM State               │
│         │                    │                   │
│         └──────┬────────────┘                   │
│                │                                 │
│         Derived Keys                            │
│                │                                 │
│    ┌──────────┴──────────┐                     │
│    │                     │                     │
│ Sealed Data         Runtime Data               │
│ (Persistent)         (Volatile)                │
└──────────────────────────────────────────────────┘
```

#### Persistence Mechanisms

1. Hardware-Based Persistence
   - CPU-specific measurements (SEV-SNP/TDX)
   - TPM PCR values
   - Platform configuration state
   ```ascii
   Boot 1: HW State + TPM ──► Key A
   Boot 2: Same State    ──► Key A (Same)
   Boot 3: Changed State ──► Key B (Different)
   ```

2. Key Storage Approaches
   ```ascii
   Approach 1: Hardware-Bound (Recommended)
   - No persistent storage
   - Keys derived from hardware state
   - TPM measurements for validation
  
   Approach 2: Sealed Storage (Alternative)
   - TPM-sealed key blobs
   - Protected by hardware binding
   - Used when state derivation unstable
   ```

   Both approaches use TEE memory for runtime:
   - Active keys kept only in TEE
   - Cleared on power off
   - Protected from host access

   Detailed Comparison:
   ```ascii
   Approach 1 (Currently Implemented):
   Hardware State ──► Derive Keys ──► TEE Memory
        │                                │
        └── TPM Measurements ───────────┘

   Approach 2 (Alternative):
   TPM ──► Seal Keys ──► Encrypted Blobs on Disk
    │                          │
    └── Unseal Keys ──► TEE Memory
   ```

   Approach 1 Characteristics:
   - **Pros**:
     - No keys stored anywhere (even encrypted)
     - Keys automatically change if hardware/platform compromised
     - Simpler implementation (no key storage/retrieval)
     - No key backup needed
     - Perfect forward secrecy
   - **Cons**:
     - Sensitive to hardware/platform state changes
     - May need re-encryption on legitimate changes
     - Requires stable hardware measurements
     - More complex recovery for hardware changes

   Approach 2 Characteristics:
   - **Pros**:
     - More resilient to platform changes
     - Easier recovery process
     - Can survive some hardware updates
     - Keys can be backed up
     - Traditional key management
   - **Cons**:
     - Keys exist on disk (though encrypted)
     - Need secure key backup mechanism
     - More complex implementation
     - Potential for key extraction if TPM compromised
     - Need key version and rotation management

   Implementation Choice:
   We implemented Approach 1 because:
   - Better security properties (no stored keys)
   - Simpler implementation
   - Automatic key changes on compromise
   - No key management overhead

#### Implementation Details

1. Early Boot Process
```ascii
┌────────────────────────────────────────────────┐
│              Cross-Boot Flow                    │
│                                                │
│ UEFI ──► Measure ──► TPM Read ──► Key Derive  │
│   │                                   │        │
│   └───► SEV/TDX ──► Get Quote ───────┘        │
│                                               │
└────────────────────────────────────────────────┘
```

2. Key Regeneration Process
   - Hardware measurements collection
   - TPM state verification
   - Key derivation from stable components
   - Validation against sealed reference

#### Security Properties

1. Cross-Boot Stability
   - Same hardware state = Same keys
   - Predictable key regeneration
   - No key material storage needed

2. Tamper Detection
   - Hardware state changes detected
   - TPM measurements validate boot
   - Platform configuration verified

#### Design Decisions

1. Persistence Strategy
   - **Decision**: Hardware-bound key derivation vs. stored keys
   - **Pro**: No key storage needed
   - **Con**: Requires stable measurements
   - **Mitigation**: Two-stage verification

2. State Binding
   - **Decision**: Combined CPU + TPM binding
   - **Pro**: Comprehensive platform state coverage
   - **Con**: More complex key derivation
   - **Mitigation**: Caching in TEE memory

3. Recovery Handling
   - **Decision**: Fallback key derivation paths
   - **Pro**: Handles legitimate state changes
   - **Con**: Additional complexity
   - **Mitigation**: Strict validation

#### Implementation in tee-setup

The tee-setup script in initramfs handles cross-boot persistence:

```bash
# Early in boot process
setup_tee_keys() {
    # Get hardware-bound key
    hw_key=$(get_tee_key "hw_key")
    
    # Export for cryptroot script
    export CRYPTKEY="$hw_key"
}
```

This ensures:
- Consistent key derivation across reboots
- Early availability of keys
- Secure key handling in TEE

#### Limitations and Considerations

1. Platform Updates
   - BIOS updates may change measurements
   - CPU microcode updates affect state
   - TPM firmware modifications

2. Hardware Changes
   - CPU replacement breaks binding
   - TPM replacement affects state
   - Platform modifications

3. Recovery Scenarios
   - Platform state changes
   - Measurement drift
   - Hardware replacements

#### Best Practices

1. State Management
   - Regular measurement baseline updates
   - Monitored TPM state changes
   - Controlled platform modifications

2. Recovery Preparation
   - Backup sealed key blobs
   - Document recovery procedures
   - Test recovery scenarios

3. Monitoring
   - Track measurement changes
   - Alert on unexpected states
   - Log key derivation events

This cross-boot persistence design ensures data remains accessible across reboots while maintaining security properties and providing recovery options for legitimate platform changes.

### Partition Security Enhancements

#### Overview

```ascii
┌──────────────────────────────────────────────────┐
│           Security Enhancement Layers            │
│                                                  │
│    Mount Options    Filesystem      Device      │
│    Protection      Hardening      Security      │
│         │             │              │          │
│         └─────────────┼──────────────┘          │
│                       │                         │
│              Verification Steps                 │
│                       │                         │
│         ┌────────────┴────────────┐            │
│     Runtime         Storage     Cleanup         │
│   Protection      Protection    Handlers        │
└──────────────────────────────────────────────────┘
```

#### Mount Options Security

1. Partition Mount Protections
   - `nodev`: Prevent device file creation
   - `nosuid`: Disable setuid/setgid bits
   - `noexec`: Prevent code execution

2. Verity Mount Options
   - `restart_on_corruption`: Automatic reboot on integrity failure
   - `ignore_corruption`: Continue boot with warnings

3. LUKS Device Options
   - `allow-discards`: Enable secure TRIM
   - `no-read-workqueue`: Reduce DMA attack surface
   - `no-write-workqueue`: Direct I/O for better security

#### Filesystem Hardening

1. Extended Attributes
   ```ascii
   Filesystem Features:
   ├── metadata_csum: Checksum protection
   ├── 64bit: Extended inode support
   └── journal_checksum: Journal integrity
   ```

2. TEE Memory Protection
   - Mode 0700 permissions
   - Root-only ownership
   - Memory-only storage (tmpfs)
   - Secure mount options

#### Verification Mechanisms

1. LUKS Verification
   ```ascii
   LUKS Header Check ──► Cipher Verification ──► Key Size Validation
          │                      │                      │
          └──────────────────────┴──────────────────────┘
                         Continuous Monitoring
   ```

2. Verity Verification
   - Hash algorithm validation
   - Block size verification
   - Root hash confirmation
   - Runtime integrity checks

#### Security Cleanup Handlers

1. Device Cleanup
   - LUKS device closure
   - Verity device cleanup
   - Secure unmounting

2. Error Handling
   - Graceful cleanup on errors
   - Secure state reset
   - Resource deallocation

#### Implementation Benefits

1. Security Properties
   - Defense in depth approach
   - Multiple protection layers
   - Continuous verification

2. Operational Security
   - Clean failure handling
   - Secure resource cleanup
   - State verification

3. Attack Surface Reduction
   - Limited device access
   - Controlled execution paths
   - Protected memory spaces

#### Integration Points

```ascii
┌────────────────────────────────────────────────┐
│              Security Integration              │
│                                               │
│ Boot Process ──► Partition Setup ──► Runtime  │
│      │               │              │         │
│      └───────────────┴──────────────┘         │
│            Continuous Verification             │
└────────────────────────────────────────────────┘
```

1. Boot Time Integration
   - Early security initialization
   - Verified boot chain
   - Secure state establishment

2. Runtime Protection
   - Continuous integrity checking
   - Access control enforcement
   - Resource isolation

These security enhancements provide a comprehensive approach to protecting sensitive data and operations throughout the system lifecycle, from boot to runtime to shutdown.

### System Security Hardening

#### Overview

```ascii
┌──────────────────────────────────────────────────┐
│           TEE Security Verification              │
│                                                  │
│    Hardware      Memory        Runtime           │
│    Features    Encryption    Measurements        │
│      │            │             │         │      │
│      └────────────┴─────────────┴─────────┘      │
│                     │                            │
│             TEE Attestation                      │
│                     │                            │
│    ┌────────────────┴────────────────┐          │
│    │               │                 │          │
│   TEE          Runtime           System         │
│  Checks        Controls          Audit          │
└──────────────────────────────────────────────────┘
```

#### TEE Security Features

1. Required Parameters
   ```bash
   memory_encryption=on      # TEE memory encryption
   cc.tee.enabled=1         # TEE mode enabled
   cc.tee.measurement_enforce=1 # Enforce measurements
   ```

2. Hardware Requirements
   ```bash
   CPU Features:
   ├── AMD SEV-SNP: Secure Encrypted Virtualization
   └── Intel TDX: Trust Domain Extensions
   
   TPM Requirements:
   └── TPM 2.0: Trusted Platform Module
   ```

#### Memory Protection

1. Mount Options
   ```ascii
   TEE Memory:
   ├── Encrypted: Hardware-level encryption
   ├── Isolated: Protected from host
   └── Measured: Runtime attestation
   ```

2. Memory Security
   - Hardware-enforced isolation
   - Encrypted memory pages
   - Secure key storage

#### Runtime Security

1. TEE Runtime
   ```ascii
   Runtime Protection:
   ├── Measured Launch: Verified boot
   ├── Runtime Attestation: Continuous verification
   └── Secure Storage: Protected data
   ```

2. Security Features
   - Hardware-based isolation
   - Runtime measurements
   - Secure key handling

#### Verification Mechanisms

1. Hardware Verification
   ```ascii
   Verification Chain:
   ├── CPU Features: SEV/TDX support
   ├── TPM Status: PCR measurements
   └── Memory Encryption: Hardware support
   ```

#### TEE Environment Verification

1. Hardware Checks
   ```ascii
   Required Features:
   ├── CPU: SEV or TDX support
   ├── TPM: Version 2.0
   └── Memory: Encryption enabled
   ```

2. Runtime Verification
   - Driver status checks
   - Memory permissions
   - Encryption verification

#### Implementation Benefits

1. Security Depth
   - Hardware-based security
   - TEE isolation
   - Runtime attestation

2. Attack Surface Reduction
   - Hardware-enforced boundaries
   - Encrypted memory
   - Measured execution

3. Runtime Protection
   - Continuous measurement
   - Hardware isolation
   - Secure key operations

#### Integration Points

```ascii
┌────────────────────────────────────────────────┐
│           Security Integration Flow            │
│                                               │
│ Installation ──► Boot Process ──► Runtime     │
│      │              │             │          │
│ Verification    Measurements   Monitoring     │
│      │              │             │          │
│      └──────────────┴─────────────┘          │
└────────────────────────────────────────────────┘
```

1. Installation Phase
   - Parameter configuration
   - System hardening
   - Initial verification

2. Boot Process
   - Parameter validation
   - TEE verification
   - Security measurements

3. Runtime Monitoring
   - Continuous verification
   - Resource monitoring
   - Security auditing

These hardening measures provide comprehensive system protection while maintaining the security properties required for confidential computing environments. 