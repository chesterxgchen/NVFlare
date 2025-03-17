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

Security Trilemma:
┌─────────────────┐         ┌─────────────────┐
│ Portable Keys   │ ────────│ Secure at Rest  │
│                 │         │                  │
└────────┬────────┘         └────────┬────────┘
         │                           │
         │         ┌─────────┐       │
         └─────────│Tamper   │───────┘
                   │Resistant│
                   └─────────┘





We can't solve this perfectly with just technical measures. We need to consider:


1. The trust model between companies


2. The business process of image delivery


3. Acceptable risk levels

Here's a potential approach combining technical and process controls:

# Proposed Solution


1. Split Trust Model
Company A (Builder)        Company B (Runner)
┌──────────────┐          ┌──────────────┐
│ Build Image  │──────────│ Run Image    │
│ Part 1 Keys  │   +     │ Part 2 Keys  │
└──────────────┘          └──────────────┘







2. Key Ceremony Process

  1. Company A generates Part 1 of key material
  2. Company B generates Part 2 of key material
  3. Both parts required for decryption
  4. Neither company has complete key

  Key Exchange Process:
┌────────────────┐     ┌────────────────┐
│  Company A     │     │  Company B     │
│  Key Part 1    │     │  Key Part 2    │
└───────┬────────┘     └───────┬────────┘
        │                      │
        │  Secure Exchange    │
        └──────────┬──────────┘
                   │
         ┌─────────▼─────────┐
         │  Legal Agreement  │
         │  Defines Process  │
         └─────────┬─────────┘
                   │
         ┌─────────▼─────────┐
         │ Runtime Assembly  │
         
         └───────────────────┘



$ Secure IP Protection Design
1. Multi-Party Key Exchange Architecture


Offline Process:
┌────────────────┐                  ┌────────────────┐
│ Model Owner    │                  │ Data Owner     │
│ (Server)       │◄─── Offline ────►│ (Client)       │
└───────┬────────┘    Exchange     └───────┬────────┘
        │                                   │
        │                                   │
    Base Keys                           Base Keys
        │                                   │
        ▼                                   ▼
┌────────────────┐                  ┌────────────────┐
│ Server CVM     │◄─── Runtime ────►│ Client CVM    │
│ DH Exchange    │     Exchange     │ DH Exchange    │
└────────────────┘                  └────────────────┘



2. Low-Level DH Implementation


class SecureKeyExchange:
    def __init__(self):
        # Embedded during build, different for Server/Client
        self.base_key = get_build_time_key()
        
        # Early boot DH components
        self.dh_params = {
            'generator': g,
            'prime': p,
            # Embedded in read-only sections
            'validation': validation_params
        }
    
    def early_boot_exchange(self):
        """
        Runs very early in boot process
        Implemented in assembly/low-level code
        """
        # Generate DH components
        private_key = generate_private()
        public_key = generate_public(private_key)
        
        # Exchange happens through FL protocol
        shared_secret = perform_dh_exchange(
            private_key,
            received_public,
            self.dh_params
        )
        
        return derive_final_key(
            shared_secret,
            self.base_key
        )
3. Anti-Tampering Measures

class TamperProtection:
    def protect_dh_exchange(self):
        # Multiple validation layers
        validations = [
            # Assembly-level checks
            verify_code_segment(),
            verify_dh_parameters(),
            
            # Runtime checks
            verify_computation_results(),
            verify_key_derivation(),
            
            # Protocol checks
            verify_exchange_sequence(),
            verify_peer_identity()
        ]
        
        # Any failure triggers shutdown
        if not all(validations):
            secure_shutdown()


4. Key Derivation Chain

Key Hierarchy:
┌────────────────┐
│ Offline Keys   │
│ (Per Party)    │
└───────┬────────┘
        │
        ▼
┌────────────────┐
│ DH Exchange    │
│ Components     │
└───────┬────────┘
        │
        ▼
┌────────────────┐
│ Runtime Keys   │
│ (Session)      │
└────────────────┘

5. Implementation Protection
 


 Low-level DH implementation example
; Hard to modify without breaking functionality

section .text
    global dh_exchange
    
dh_exchange:
    ; Integrity check on code segment
    call verify_code_integrity
    jnz fail_secure
    
    ; Load parameters from read-only segment
    mov rdi, [dh_params]
    call validate_params
    jnz fail_secure
    
    ; Perform exchange
    call generate_dh_components
    call exchange_keys
    call derive_final
    
    ; Validate results
    call verify_results
    jnz fail_secure
    
    ret


### Key Security Properties:
1. Offline Component:
   - Pre-shared keys distributed securely
   - Different keys for Server/Client
   - Offline process reduces attack surface
2. Runtime Exchange:
   - Low-level DH implementation
   - Hard-coded parameters in read-only sections
   - Multiple validation layers
3. Anti-Tampering:
   - Even if code is modified, key derivation likely fails
   - Multiple integrity checks
   - Fail-secure design
4. Limitations (Being Honest):
   - Can't prevent all tampering
   - Focus on making tampering very difficult
   - Make invalid modifications fail secure
5. Benefits:
   - No network dependency for key exchange
   - Reduced trust requirements
   - Layered protection approach
   - Practical implementation possible

CVM Image Layout:
┌───────────────────────────────┐
│ Read-Only Area (Clear Text)   │
│  ├── Boot Code               │
│  ├── DH Exchange Code        │
│  ├── FLARE Communication Code│
│  └── Signatures              │
├───────────────────────────────┤
│ Encrypted Area               │
│  ├── FL Model Code          │
│  ├── Model Weights          │
│  ├── Training Logic         │
│  └── Sensitive Data         │
└───────────────────────────────┘

Security Model:
1. FLARE communication code:
   - Can be read (not secret)
   - Must not be tampered
   - Verified by signatures
2. Critical IP:
   - Must remain encrypted
   - Protected by derived keys
   - Only accessible after valid boot


This means:
   - 1. We're not protecting FLARE code confidentiality
   - 2. We're protecting FLARE code integrity
   - 3. We're protecting model/data confidentiality


Build-time Protection:
┌────────────────────────────┐
│ ✓ IP Protected at Rest    │
│ ✓ No Plain Text IP        │
│ ✓ Tamper-Resistant Design │
│ ✓ Clean Trust Chain       │
└────────────────────────────┘



Build Time:                          Runtime:
┌────────────────────────┐           ┌────────────────────────┐
│ 1. Generate           │           │ 1. Boot Clear Text    │
│    - DH Parameters    │           │ 2. FLARE Starts       │
│    - Public Keys      │──────────►│ 3. DH Key Exchange    │
│ 2. Encrypt IP with    │           │ 4. Derive Final Key   │
│    Combined Key       │           │ 5. Decrypt IP/Models  │
└────────────────────────┘           └────────────────────────┘

class BuildTimeProtection:
    def build_secure_image(self):
        # Generate DH components
        dh_params = {
            'server_pub': generate_server_public(),
            'client_pub': generate_client_public(),
            'params': generate_dh_params()
        }
        
        # Clear text (signed)
        clear_text = {
            '/boot': 'boot_code',
            '/flare': 'flare_code',
            '/dh_params': dh_params,  # Public components only
            '/signatures': 'code_signatures'
        }
        
        # Encrypted with combined key
        encrypted = {
            '/model': 'model_code',
            '/weights': 'weights',
            '/training': 'training_logic'
        }
        
        # 1. Sign clear components
        sign_components(clear_text)
        
        # 2. Encrypt IP (needs both build and runtime keys)
        encrypt_sensitive_components(encrypted)



Key Points:
- No sensitive keys in image
- Only public DH components embedded
- Final decryption key derived from:
  - Build-time public components
  - Runtime DH exchange
- IP protection requires both parts






Build Time:                         Runtime:
┌────────────────────┐             ┌────────────────────┐
│ 1. Generate       │             │ 1. Boot Clear Text │
│    - DH Base Keys │             │    - DH Code       │
│    - Parameters   │             │    - Public Params │
│                   │             │                    │
│ 2. Derive Initial │             │ 2. DH Exchange     │
│    LUKS Key       │──────────────►   Complete Key    │
│                   │             │    Generation      │
│ 3. Encrypt Disk   │             │                    │
│    with LUKS      │             │ 3. Derive LUKS Key │
└────────────────────┘             │    Unlock Disk    │
                                  └────────────────────┘

class KeyManagement:
    def build_time_setup(self):
        # Generate DH components
        dh_params = generate_dh_params()
        server_pub = generate_server_pub()
        client_pub = generate_client_pub()
        
        # Initial key derivation for LUKS
        initial_key = derive_initial_key(
            dh_params, 
            server_pub, 
            client_pub
        )
        
        # Setup LUKS with derived key
        setup_luks_encryption(initial_key)
        
        # Store only public components
        store_components(dh_params, server_pub, client_pub)
    
    def runtime_unlock(self):
        # Load public components
        dh_params = load_dh_params()
        pub_key = load_public_key()
        
        # Perform DH exchange
        shared_secret = perform_dh_exchange(
            dh_params,
            pub_key
        )
        
        # Derive final LUKS key
        luks_key = derive_luks_key(
            shared_secret,
            dh_params
        )
        
        # Unlock LUKS partition
        unlock_luks_partition(luks_key)




DH + LUKS Flow:
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ DH Exchange  │────►│ Key          │────►│ LUKS         │
│ Components   │     │ Derivation   │     │ Unlock       │
└──────────────┘     └──────────────┘     └──────────────┘










# 1. Try to read CVM disk image directly
$ sudo dd if=/var/lib/libvirt/images/unprotected_cvm.img of=dump1.img
# Result: Can read raw data

$ sudo dd if=/var/lib/libvirt/images/protected_cvm.img of=dump2.img
# Result: Only encrypted data visible

# 2. Try to mount CVM disk
$ sudo kpartx -av unprotected_cvm.img
$ sudo mount /dev/mapper/loop0p1 /mnt/test
# Result: Can see files

$ sudo kpartx -av protected_cvm.img
$ sudo mount /dev/mapper/loop0p1 /mnt/test
# Result: Encrypted, can't mount

# 3. Memory dump from host
$ sudo virsh dump unprotected_cvm mem.dump
# Result: Memory contents visible

$ sudo virsh dump protected_cvm mem.dump
# Result: TEE protected memory not accessible









