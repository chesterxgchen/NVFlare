# NVFlare IO Interceptor

A system-level IO protection mechanism designed to complement VM-based Trusted Execution Environments (TEEs) like Intel TDX and AMD SEV-SNP by securing I/O operations that are not protected by memory encryption.

## Security Model & Threat Analysis

### 1. TEE Protection Gaps

VM-based TEEs provide:
- ✅ Memory encryption
- ✅ Memory integrity
- ✅ VM isolation
- ❌ I/O protection
- ❌ Side-channel protection

### 2. Attack Vectors & Mitigations

#### a. Direct I/O Observation
**Risk**: 
- Hypervisor can observe file operations
- Host OS can monitor I/O patterns
- Data leakage during file operations

**Mitigations**:
```c
// Multi-layer encryption with noise
static protect_config_t protect_config = {
    .num_encryption_layers = 3,      // Multiple encryption layers
    .min_padding_size = 1024,        // Random padding
    .max_padding_size = 1048576,     // Up to 1MB
    .add_random_noise = 1            // Inter-layer noise
};
```

## Overview

The IO Interceptor provides a low-level security layer by:
1. Intercepting system calls (`open`, `write`, `mmap`, etc.)
2. Protecting against unauthorized model/data saves
3. Supporting encryption and hash verification
4. Working universally with all languages and frameworks

## Directory Structure

## Risk Analysis in VM-based TEE

### Architecture & Attack Surface

```
     ┌──────────────────────────────────────────┐
     │            Confidential VM               │
     │  ┌────────────────┐  ┌────────────────┐ │
     │  │   ML Training  │  │  IO            │ │
     │  │   Workload    ─┼──▶  Interceptor   │ │
     │  └────────────────┘  └────────────────┘ │
     │            │                │           │
     │    Memory (Protected)   I/O (Exposed)   │
     └────────────│────────────────│───────────┘
                  │                │
     ┌───────────▼────────────────▼───────────┐
     │           Hypervisor                    │
     │  ✓ Can't read VM memory                │
     │  ✗ Can observe I/O patterns            │
     │  ✗ Can monitor syscalls               │
     └──────────────────────────────────────────┘
```

### Risk Categories

```
1. Memory Protection
   TEE         [████████████] Protected
   I/O Buffer  [████░░░░░░░░] Partially Exposed
   Disk I/O    [░░░░░░░░░░░░] Exposed

2. Side Channels
   File Size   [░░░░░░░░░░░░] Exposed
   I/O Timing  [░░░░░░░░░░░░] Exposed
   Page Faults [████░░░░░░░░] Partially Protected

3. Attack Points
    ┌─────────────┐    ┌──────────────┐    ┌────────────┐
    │ ML Training │ ─> │ I/O syscalls │ ─> │ Host/Hyper │
    └─────────────┘    └──────────────┘    └────────────┘
         Safe             Vulnerable          Untrusted
```

### Critical Vulnerabilities

1. **VMEXIT/VMGEXIT Monitoring**
```
   ML Process ──[VMEXIT]──> Host OS
                  │
                  └─> ⚠️ I/O pattern analysis
                  └─> ⚠️ Timing attacks
                  └─> ⚠️ Syscall tracing
```

2. **Memory Exposure During I/O**
```
   Protected Memory ──> I/O Buffer ──> Disk
        │                  │            │
        Safe           Vulnerable    Exposed
   [███████████]    [████░░░░░░]  [░░░░░░░]
```

3. **Side-Channel Leakage**
```
   Model Training
        │
   ┌────┴───────┐
   │   │   │    │
   │   │   │    │
   ▼   ▼   ▼    ▼
   Size Time Pages I/O
    ⚠️   ⚠️    ⚠️   ⚠️
```

### Memory Security in TEE Context

```
     ┌──────────────────────────────────────────────────┐
     │                Confidential VM                   │
     │                                                 │
     │  ┌─────────────┐    ┌───────────┐   ┌───────┐  │
     │  │ Application │    │ Temp/Swap │   │ I/O   │  │
     │  │   Memory    │───>│  Memory   │──>│ Buffs │  │
     │  └─────────────┘    └───────────┘   └───────┘  │
     │        ✓                 ⚠️             ✗       │
     └──────────────────────────────────────────────────┘
     
     ✓ = Protected by TEE
     ⚠️ = Potentially exposed during swapping/paging
     ✗ = Exposed during I/O operations
```

**Why Memory Wiping in TEE?**
1. **Memory Swapping**:
   - Even in TEE, memory pages can be swapped
   - Swap files are outside TEE protection
   - Sensitive data could persist in swap

2. **Page Migration**:
   - During I/O, pages move between protection domains
   - Data can be exposed during transitions
   - Need to ensure clean transitions

3. **Memory Reuse**:
   - TEE protects current memory state
   - But not previous contents after free()
   - Important for key material security

### Understanding VMEXIT in TEE

```
      ┌─────────────────────────────────────────┐
      │            Confidential VM              │
      │                                         │
      │  ┌──────────┐         ┌────────────┐   │
      │  │ Guest    │ VMEXIT  │ Privileged │   │
      │  │ Code     │─────────▶ Operations │   │
      │  └──────────┘         └────────────┘   │
      └───────────────────────────│────────────┘
                                   │
      ┌───────────────────────────▼────────────┐
      │              Hypervisor                 │
      │     (Can observe VMEXIT frequency,     │
      │      timing, and operation type)       │
      └─────────────────────────────────────────┘
```

**VMEXIT Explained**:
1. **What is VMEXIT?**
   - CPU state transition from guest (VM) to host mode
   - Required for privileged operations (I/O, page faults, etc.)
   - Exposes timing and operation patterns to hypervisor

2. **VMEXIT Triggers**:
```
Operation Type     | Protection Status    | Risk Level
------------------|---------------------|------------
Memory Access     | Protected by TEE    | Low
I/O Operations   | Requires VMEXIT     | High
Page Faults      | Requires VMEXIT     | Medium
System Calls     | May require VMEXIT  | Medium
```

### Memory Paging and Swap Space

```
      ┌────────────────────────────────────────┐
      │           Confidential VM              │
      │                                        │
      │   ┌─────────┐                         │
      │   │ Memory  │      ┌──────────────┐   │
      │   │ Pages   │─────▶│ Page Tables  │   │
      │   └─────────┘      └──────┬───────┘   │
      │                           │           │
      └───────────────────────────│───────────┘
                                   │
                          VMEXIT   │
                                   ▼
      ┌─────────────────────────────────────┐
      │           Host System               │
      │  ┌─────────────────────────────┐   │
      │  │         Swap Space          │   │
      │  │ (Outside TEE Protection)    │   │
      │  └─────────────────────────────┘   │
      └─────────────────────────────────────┘
```

**Memory Management in TEE**:

1. **Page States**:
```
Location        | Protection         | Interceptor Coverage
----------------|-------------------|---------------------
Active Memory   | TEE Protected     | Not needed
Page Tables     | TEE Protected     | Not needed
Swap Space      | Not Protected     | ✓ Intercepts paging
I/O Buffers     | Not Protected     | ✓ Intercepts I/O
```

2. **Swap Space Risks**:
- Located outside TEE boundary
- Managed by host OS
- Can be accessed by privileged host processes
- May contain sensitive data residue

3. **IO Interceptor's Role**:
```c
// Intercept both explicit I/O and implicit paging
if (is_paging_operation(fd)) {
    // Encrypt before page-out
    encrypt_page_content();
} else if (is_io_operation(fd)) {
    // Normal I/O encryption
    encrypt_io_content();
}
```

### Protection Strategy

```
Operation          | Risk                  | Mitigation
-------------------|----------------------|------------------
Explicit I/O      | VMEXIT monitoring    | Noise injection
Page Swapping     | Data exposure        | Page encryption
System Calls      | Pattern analysis     | Batching/padding
Memory Allocation | Page table attacks   | Secure cleanup
```

### Network Security Considerations

```
     ┌─────────────────────────────────────┐
     │          Confidential VM            │
     │                                     │
     │   ┌──────────┐      ┌──────────┐   │
     │   │ App Code │      │ Network  │   │
     │   │ (Sealed) │─────▶│ Stack    │   │
     │   └──────────┘      └────┬─────┘   │
     │                          │          │
     └──────────────────────────┼──────────┘
                                │
                          ┌─────▼─────┐
                          │  Network  │
                          │ (Exposed) │
                          └───────────┘
```

**Network Risks in Hardened CC VM**:

1. **Port Exposure**:
```
Risk Level | Port Type              | Mitigation
-----------|-----------------------|------------------
HIGH       | Management Ports      | Block completely
MEDIUM     | Service Ports        | Strict ACLs
LOW        | Required App Ports   | Minimal exposure
```

2. **Build-time vs Runtime**:
```
┌─────────────────┐    ┌──────────────────┐
│   Build Time    │    │     Runtime      │
├─────────────────┤    ├──────────────────┤
│ - Code loading  │    │ - Network locks  │
│ - Verification  │ ─> │ - Port controls  │
│ - Sealing      │    │ - Access limits  │
└─────────────────┘    └──────────────────┘
```

3. **Network Hardening Requirements**:
- Disable unnecessary services
- Restrict outbound connections
- Implement network namespaces
- Use encrypted protocols only

### Hardened CC VM Image Recommendations

```
Security Layer    | Implementation
------------------|----------------------------------
Application      | Sealed during build
Memory           | Protected by TEE + secure wipe
Network          | Minimal ports + strict filtering
Storage          | Encrypted I/O + integrity checks
System Calls     | Intercepted and validated
```

**Build Process Security**:
```
1. Base Image Hardening
    └─> Remove unnecessary services
        └─> Lock down network
            └─> Load application
                └─> Seal image
```

### Mitigation Strategy

```
┌────────────────────┐
│ Defense Layers     │
├────────────────────┤
│ 1. Encryption     ─┼─> Multiple layers, different keys
│ 2. Padding        ─┼─> Random sizes, noise injection
│ 3. Timing         ─┼─> Random delays, batch operations
│ 4. Memory         ─┼─> Secure wipe, minimal exposure
└────────────────────┘
```

### Security Recommendations

```
Priority  Risk                Mitigation
─────────────────────────────────────────
HIGH     I/O Pattern         Randomization
HIGH     Memory Exposure     Minimal Buffer
HIGH     Side Channels       Noise Injection
MEDIUM   Timing Analysis     Random Delays
MEDIUM   Size Analysis       Fixed Padding
LOW      Page Faults        Prefetching
```

### Implementation Details

#### 1. Multi-Layer Protection
```c
static protect_config_t protect_config = {
    .num_encryption_layers = 3,      // Multiple encryption layers
    .min_padding_size = 1024,        // Random padding
    .max_padding_size = 1048576,     // Up to 1MB
    .add_random_noise = 1            // Inter-layer noise
};
```

#### 2. Memory Security
```c
static void cleanup_fd_info(fd_info* info) {
    if (info->buffer) {
        memset(info->buffer, 0, info->size);  // Secure wipe
        free(info->buffer);
    }
    if (info->key) {
        memset(info->key, 0, 32);
        free(info->key);
    }
}
```

#### 3. Side-Channel Mitigation
```c
// Add random delays and noise
size_t padding_size = protect_config.min_padding_size + 
    (rand() % (protect_config.max_padding_size - protect_config.min_padding_size));

if (protect_config.add_random_noise) {
    size_t noise_size = rand() % 1024;
    RAND_bytes(noise, noise_size);
}
```

## Usage in TEE Environment

```bash
# Build with TEE support
gcc -O2 -D_FORTIFY_SOURCE=2 -fstack-protector-strong secure_io_interceptor.c -o libsecureio.so

# Configure protection
export NVFLARE_ENCRYPTION_LAYERS=5
export NVFLARE_MIN_PADDING=4096
export NVFLARE_ADD_NOISE=1

# Run with protection
LD_PRELOAD=./libsecureio.so your_ml_program
```

## Limitations

1. **Cannot Protect Against**:
   - Physical memory attacks
   - Hardware-level monitoring
   - Kernel compromises
   - Zero-day TEE vulnerabilities

2. **Performance Impact**:
   - Encryption overhead per layer
   - Random padding overhead
   - System call interception delay

3. **TEE Integration Limits**:
   - VMEXIT/VMGEXIT overhead
   - Shared memory constraints
   - Resource limitations