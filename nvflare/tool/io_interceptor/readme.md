# NVFlare IO Interceptor

## Table of Contents

1. **Goals and Overview**
   - Purpose and Objectives
   - Integration with TEE
   - Protection Scope

2. **Risk Analysis**
   - Attack Surface Analysis
   - System Architecture
   - Risk Categories & Mitigations
   - OEM Partition Analysis
   - Detailed Attack Vectors

3. **Protection Measures**
   - Memory Protection Strategy
   - I/O Protection Strategy
   - Network Protection Strategy

4. **Implementation**
   - Architecture
   - Components
     - Core Interceptor
     - Encryption Handler
     - Memory Handler

5. **Performance Analysis**
   - Memory Impact
   - I/O Performance
   - Optimization Tips
   - Monitoring

6. **Usage Guide**
   - Basic Setup
   - Path Protection
   - Secure Memory Usage
   - File Encryption
   - Troubleshooting

7. **Risk Areas Not Covered**
   - Memory & TEE Risks
   - I/O Related Risks
   - Network Protocol Risks
   - Build-time Risks

### Purpose and Objectives
A system-level IO protection mechanism designed to complement VM-based Trusted Execution Environments (TEEs) like Intel TDX and AMD SEV-SNP by securing I/O operations that are not protected by memory encryption.

### Integration with TEE
- Complement TEE memory protection
- Secure I/O operations outside TEE
- Integrate with TEE attestation

### Protection Scope
- File I/O operations
- Memory operations
- Network I/O
- System call interception

## 2. Risk Analysis

### Threat Categories
- Runtime Memory Threats
- I/O Operation Threats
- Network Communication Threats
- Build/Deploy Time Threats

### Attack Surface Analysis
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

VM-based TEEs provide:
- ✅ Memory encryption
- ✅ Memory integrity
- ✅ VM isolation
- ❌ I/O protection
- ❌ Side-channel protection

### 2. System Architecture & Attack Surface

```
┌────────────────────────────────────────────┐
│               Confidential VM              │
│                                           │
│    ┌──────────┐        ┌──────────┐      │
│    │ root-fs  │        │ tmp-fs   │      │
│    │ (sealed) │        │(volatile)│      │
│    └────┬─────┘        └────┬─────┘      │
│         │                   │            │
│    ┌────▼─────┐      ┌─────▼────┐       │
│    │ App Code │      │ Runtime  │       │
│    │ (sealed) │      │ Data     │       │
│    └────┬─────┘      └─────┬────┘       │
│         │                  │            │
└─────────┼──────────────────┼────────────┘
                │                  │
┌─────────▼──────────────────▼────────────┐
│              Host System                 │
│                                         │
│  ┌─────────────┐    ┌──────────────┐   │
│  │ Storage I/O │    │ Network I/O  │   │
│  └─────────────┘    └──────────────┘   │
└─────────────────────────────────────────┘
```

### 3. Risk Categories & Mitigations

| Component | Risk Level | Attack Vector | Mitigation |
|-----------|------------|---------------|------------|
| root-fs | LOW | Integrity tampering | Sealed at build |
| tmp-fs | HIGH | Data exposure | IO intercept |
| Memory Pages | MEDIUM | Page swapping | Encryption |
| Network I/O | HIGH | Pattern analysis | Noise inject |

**Filesystem Types in TEE**:

1. **root-fs (Root Filesystem)**:

| Characteristic | Status | Recommendation |
|---------------|--------|----------------|
| Immutability | Sealed at build | No runtime changes |
| Encryption | VM encrypted | Additional layer not needed |
| Integrity | Measured/signed | Verified at boot |
| Access Pattern | Read-only | Predictable I/O |

2. **tmp-fs (Temporary Filesystem)**:

| Characteristic | Status | Protection Needed |
|---------------|--------|-------------------|
| Volatility | In-memory | ✓ Memory wiping |
| Encryption | Not by default | ✓ IO interception |
| Access Pattern | Dynamic | ✓ Pattern hiding |
| Persistence | None | ✓ Secure cleanup |

**Protection Requirements**:

| Filesystem | TEE Protection | Additional Security Needed |
|------------|---------------|--------------------------|
| root-fs | ✓ Full | × Already protected |
| tmp-fs | Partial | ✓ IO interception |
| swap | × None | ✓ Full protection |

### OEM Partition Analysis

```
┌────────────────────────────────────────────────────┐
│                  Confidential VM                   │
│                                                    │
│  ┌──────────────┐    ┌──────────┐    ┌─────────┐  │
│  │ OEM Partition│    │ root-fs  │    │ tmp-fs  │  │
│  │ (launcher)   │    │(sealed)  │    │(volatile│  │
│  └──────┬───────┘    └────┬─────┘    └────┬────┘  │
│         │                 │                │       │
│         └─────────────────┘                │
│                     │                                │
│              Host Storage                     │
└──────────────────────────────────────────────────────┘
```

| Partition Type | Protection Level | Risk Assessment |
|----------------|-----------------|------------------|
| OEM           | Measured+Sealed  | Launch Time Only |
| root-fs       | Full TEE        | Runtime Protected |
| tmp-fs        | Dynamic         | Needs Protection |



#### OEM Partition Security Analysis

| Component | Risk Level | Attack Vector | Mitigation |
|-----------|------------|---------------|------------|
| Launcher Binary | LOW | Binary tampering | Measured at boot |
| Config Files | MEDIUM | Configuration leak | Encrypt sensitive |
| Static Assets | LOW | Asset modification | Integrity check |

#### Launch Sequence Protection

| Stage | Protection Mechanism |
|-------|-------------------|
| 1. Boot Measurement | - TEE measures OEM partition<br>- Validates against expected value |
| 2. Launch Time | - Launcher loaded into TEE memory<br>- Config decrypted in secure memory |
| 3. Runtime | - Binary runs from protected memory<br>- Original partition not accessed |

#### Risk Mitigation Requirements

```c
typedef struct {
    struct {
        uint8_t expected_measurement[32];  // Expected boot measurement
        bool verify_signature;             // Signature verification
        bool encrypt_config;               // Config encryption
    } oem_protection;

    struct {
        char* allowed_binaries[MAX_BINS];  // Whitelisted binaries
        bool runtime_verification;         // Continuous verification
        bool secure_config_loading;        // Secure config handling
    } launch_protection;
} oem_security_config_t;
```

#### Security Recommendations for OEM Partition

1. **Build Time**:
```
- Sign all binaries
- Encrypt sensitive configurations
- Include measurement in attestation
```

2. **Launch Time**:
```
- Verify partition measurement
- Load into protected memory
- Clear sensitive data after launch
```

3. **Runtime**:
```
- No writes to OEM partition
- Access only during launch
- Monitor for tampering attempts
```

### Detailed Attack Vectors Analysis

```
┌─────────────────────────────────────────────────────┐
│                   Attack Surface                     │
│                                                     │
│    Runtime                     Build/Deploy         │
│    ┌──────────┐               ┌──────────┐         │
│    │ I/O Ops  │               │ Image    │         │
│    │ Network  │               │ Integrity│         │
│    │ Memory   │               │ Supply   │         │
│    └──────────┘               └──────────┘         │
└─────────────────────────────────────────────────────┘
```

1. **Runtime Attacks**

Attack Type          | Risk Level | Detection     | Prevention
--------------------|------------|---------------|-------------
Memory Inspection   | LOW        | TEE Protected | N/A
I/O Monitoring     | HIGH       | Pattern Det.  | Encryption+Noise
Network Analysis   | HIGH       | Traffic Mon.  | Traffic Shaping
Side Channels      | MEDIUM     | Timing Mon.   | Randomization


2. **Build/Deploy Attacks**

Attack Type          | Risk Level | Detection     | Prevention
--------------------|------------|---------------|-------------
Image Tampering     | LOW        | Measurement   | Signing
Supply Chain        | MEDIUM     | Attestation   | Verification
Configuration Leak  | MEDIUM     | Config Scan   | Encryption


### Comprehensive Mitigation Strategy

1. **Memory Protection**
```
┌────────────────────────────┐
│      Memory Hierarchy      │
├────────────────────────────┤
│ TEE Memory    │ Protected  │
│ Swap Space    │ Encrypt    │
│ I/O Buffers   │ Intercept  │
│ Temp Files    │ Secure Wipe│
└────────────────────────────┘
```

2. **I/O Protection**

Operation     | Strategy
--------------|----------------------------------
File Write    | Multi-layer encryption + padding
Network I/O   | Traffic shaping + encryption
System Calls  | Pattern hiding + batching
Temp Files    | Memory-only + secure cleanup


3. **Network Protection**

Layer         | Protection Measure
--------------|----------------------------------
Application   | Data encryption
Transport     | TLS 1.3 + certificate pinning
Network       | Traffic shaping
Physical      | Network isolation


### Network Security & Port Management

| Direction | Port Range | Traffic Type | Default Policy |
|-----------|------------|--------------|----------------|
| Inbound | 8002,8003 | ML Training | DROP |
| Inbound | 8443,9443 | Operations | DROP |
| Outbound | Dynamic | Response Traffic | DROP |

#### Policy Justification

| Direction | Default | Reason |
|-----------|---------|---------|
| Inbound | DROP | Block unauthorized connection attempts |
| Outbound | DROP | Prevent unauthorized data exfiltration |

#### Required Traffic Flow

| Port | Inbound | Outbound | Reason |
|------|---------|----------|---------|
| 8002 | Client requests | Training responses | ML Training |
| 8003 | Training data | Results/Metrics | ML Training |
| 8443 | Secure operations | Operation responses | ML Ops |
| 9443 | Attestation reqs | Attestation proofs | TEE Security |

#### Complete Port Lockdown Configuration

```bash
# 1. Default Policy: Block All
iptables -P INPUT DROP
iptables -P FORWARD DROP
iptables -P OUTPUT DROP

# 2. Allow Essential Ports
ALLOWED_PORTS=(
    8002    # ML Training Communication
    8003    # ML Training Communication
    8443    # Secure ML Operations
    9443    # TEE Attestation
)

# Allow whitelisted ports
for port in "${ALLOWED_PORTS[@]}"; do
    # Allow incoming connections to our services
    iptables -A INPUT -p tcp --dport $port -j ACCEPT
    # Allow outgoing responses from our services
    iptables -A OUTPUT -p tcp --sport $port -j ACCEPT

    # Allow outgoing connections for client operations
    iptables -A OUTPUT -p tcp --dport $port -j ACCEPT
    # Allow incoming responses to our client requests
    iptables -A INPUT -p tcp --sport $port -j ACCEPT
done

# 3. Allow established connections
iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
iptables -A OUTPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
```

#### Runtime Network Validation

```c
typedef struct {
    struct {
        uint16_t allowed_ports[4];     // [8002,8003,8443,9443]
        bool block_all_other_ports;    // true
        bool log_blocked_attempts;     // true
    } port_config;

    struct {
        bool disable_ssh;              // true
        bool disable_http;             // true
        bool disable_management;       // true
    } service_control;
} network_lockdown_t;
```

#### Security Enforcement

| Service Category | Status | Enforcement Method |
|-----------------|--------|-------------------|
| SSH Access | ❌ | Port block + service disable |
| Web Services | ❌ | Port block + no daemon |
| Management | ❌ | Port block + no tools |
| ML Training | ✅ | Ports 8002,8003 |
| ML Operations | ✅ | Port 8443 |
| TEE Attestation | ✅ | Port 9443 |

### Risk Summary and Recommendations

| Priority | Component | Risk | Mitigation |
|----------|-----------|------|------------|
| P0 | Model Data | Extraction | Encryption |
| P0 | Runtime Memory | Page Exposure | TEE + Wipe |
| P0 | Network Traffic | Pattern Analysis | Shaping |
| P1 | Filesystem | Data Residue | Secure Delete |
| P1 | System Calls | Timing Analysis | Randomization |
| P2 | Build Process | Image Tampering | Signing |

### Implementation Requirements

1. **Core Security Features**
```c
typedef struct {
    int num_encryption_layers;    // Minimum 3 layers
    size_t min_padding;          // Random padding
    bool enable_noise;           // Traffic shaping
    bool secure_cleanup;         // Memory wiping
} security_config_t;
```

2. **Monitoring Requirements**
```
Component     | Metrics to Monitor
--------------|--------------------
Memory        | Page faults, swaps
I/O           | Patterns, timing
Network       | Traffic analysis
System        | Call patterns
```

3. **Deployment Checklist**
```
┌─────────────────────┐
│ Security Checklist  │
├─────────────────────┤
│ □ TEE Enabled      │
│ □ I/O Intercepted  │
│ □ Network Secured  │
│ □ Memory Protected │
└─────────────────────┘
```

### Runtime I/O Attack Analysis

```
┌──────────────────────────────────────────────────────┐
│                   I/O Attack Surface                  │
│                                                      │
│    OS Level                  Application Level       │
│  ┌──────────┐              ┌──────────────┐         │
│  │ Page/Swap│              │ Model Save   │         │
│  │ VMEXIT   │              │ Checkpoints  │         │
│  │ tmp-fs   │              │ Gradients    │         │
│  └─────┬────┘              └──────┬───────┘         │
│        │                          │                  │
│        └──────────────────────────┘                  │
│                     │                                │
│              Host Monitoring                         │
└──────────────────────────────────────────────────────┘
```

#### 1. OS-Level I/O Risks

```
Operation Type | Risk Description | Mitigation Strategy
---------------|------------------|-------------------
Page Files | Memory pages written to untrusted storage | - Encrypt page content<br>- Secure page cleanup<br>- Minimize swapping
VMEXIT Events | Host can observe timing and frequency of exits | - Batch operations<br>- Add random delays<br>- Noise injection
tmp-fs Access | Temporary data exposed through filesystem | - Memory-only tmp-fs<br>- Encrypted if needed<br>- Secure wipe
```

#### 2. Model Theft Prevention

```
Risk Scenario | Attack Method | Protection Measure
---------------|---------------|-------------------
Direct Save | Save to unprotected directory | - Whitelist paths<br>- Encrypt all saves<br>- Path validation
Checkpointing | Capture intermediate model states | - Secure checkpoints<br>- Encrypted storage<br>- Clean old states
Gradient Capture | Collect training progress data | - Encrypt gradients<br>- Secure aggregation<br>- Memory-only ops
```

#### 3. I/O Pattern Monitoring

```
Pattern Type | Information Leaked | Countermeasure
--------------|-------------------|----------------
Size Patterns | - Model architecture<br>- Layer dimensions<br>- Batch sizes | - Fixed size padding<br>- Random padding<br>- Size obfuscation
Timing Patterns | - Training progress<br>- Iteration count<br>- Layer complexity | - Random delays<br>- Operation batching<br>- Noise injection
Access Patterns | - Training phase<br>- Model structure<br>- Data organization | - Pattern hiding<br>- Random access<br>- Access batching
```

#### Implementation Strategy

```c
// I/O Protection Configuration
typedef struct {
    struct {
        bool encrypt_pages;        // Page file protection
        bool minimize_swapping;    // Reduce page outs
        size_t secure_buffer_size; // Keep sensitive data in memory
    } os_protection;

    struct {
        char* whitelist_paths[MAX_PATHS];  // Allowed save locations
        int encryption_layers;             // Multiple encryption
        bool secure_checkpoints;           // Protect checkpoints
    } model_protection;

    struct {
        size_t min_padding;        // Minimum size padding
        size_t random_delay;       // Timing randomization
        bool pattern_hiding;       // Hide access patterns
    } pattern_protection;
} io_protection_config_t;
```

### OEM Partition Analysis

#### Build vs Runtime Context

```
┌────────────────────────────────────────┐
│        Confidential VM Image           │
│                                        │
│    Build Time         Runtime          │
│  ┌────────────┐    ┌──────────────┐   │
│  │ OEM Part   │    │ OEM in TEE   │   │
│  │ Assembly   │───>│ (Protected)  │   │
│  └────────────┘    └──────────────┘   │
│                                        │
└────────────────────────────────────────┘
```

#### Risk Assessment for Self-Built Image

```
Phase          | Traditional Risk | In Self-Built Image
---------------|-----------------|-------------------
Build Time     | HIGH            | LOW (Controlled)
Distribution   | HIGH            | LOW (Signed)
Runtime        | MEDIUM          | LOW (TEE Protected)
```

#### Remaining Considerations

```
Component     | Risk Factor        | Still Needed?
--------------|-------------------|-------------
Measurement   | Supply Chain      | YES (Attestation)
Encryption    | Config Protection | NO (Built-in)
Monitoring    | Runtime Tampering | YES (Integrity)
```

#### Modified Security Requirements

```c
typedef struct {
    struct {
        bool verify_build_signature;    // Build integrity
        bool include_in_attestation;    // Runtime proof
    } oem_protection;

    struct {
        uint8_t build_id[32];          // Build identification
        bool runtime_integrity;         // Integrity monitoring
    } launch_protection;
} oem_security_config_t;
```

#### Revised Security Recommendations

1. **Build Process Security**:
```
- Reproducible builds
- Build environment attestation
- Source code verification
```

2. **Image Security**:
```
- Image signing
- Version control
- Build artifact tracking
```

3. **Runtime Verification**:
```
- Integrity monitoring
- Attestation inclusion
- Version verification
```

### Storage Protection Analysis: IO Interceptor vs dm-verity

### Storage Protection Strategy Comparison

```
┌──────────────────────────────────────────────────────┐
│               Protection Approaches                   │
│                                                      │
│    dm-verity          IO Interceptor    TEE Native  │
│  ┌──────────┐        ┌──────────┐     ┌──────────┐  │
│  │ Block    │        │ Selective │     │ Memory   │  │
│  │ Level    │        │   I/O    │     │ Encrypt  │  │
│  └────┬─────┘        └────┬─────┘     └────┬─────┘  │
│       │                    │            │        │
│  All Blocks         Critical Paths    Protected Mem  │
│   40% OH              5-10% OH          ~0% OH       │
└──────────────────────────────────────────────────────┘
```

#### Performance & Protection Analysis

```
Aspect         | dm-verity | IO Interceptor | TEE Native
---------------|-----------|----------------|------------
Read Overhead  | 40%       | 5-10%          | ~0%
Write Support  | No        | Yes            | Yes
Granularity    | Block     | File/Path      | Page
Runtime Cost   | High      | Medium         | Low
Memory Usage   | High      | Selective      | Optimized
```

#### Protection Coverage

```
Location          | Protection Method    | Overhead | Risk Level
------------------|---------------------|----------|------------
root-fs          | TEE Measurement     | ~0%      | Low
OEM Partition    | Build Signature     | ~0%      | Low
tmp-fs           | IO Interception     | 5-10%    | Medium
Model Storage    | Selective Encrypt   | 5-10%    | High
Swap Space       | Page Encryption     | 5-10%    | High
```

#### Optimized Hybrid Approach

```
┌────────────────────────────────────────────┐
│            Protection Layers               │
│                                           │
│ Static Content        Dynamic Content     │
│ ┌──────────┐         ┌──────────┐        │
│ │TEE Native│         │ IO       │        │
│ │Protection│         │Intercept │        │
│ └──────────┘         └──────────┘        │
│     ~0% OH            5-10% OH           │
└────────────────────────────────────────────┘
```

#### Implementation Recommendations

1. **Static Content (root-fs, OEM)**:
```
- Use TEE measurement
- Build-time signing
- No runtime overhead
```

2. **Dynamic Content (tmp-fs, models)**:
```
- Selective interception
- Path-based protection
- Minimal performance impact
```

3. **Memory Management**:
```
- Use TEE memory encryption
- Selective page protection
- Optimized swap handling
```

#### Security vs Performance Trade-offs

```
Protection Method | Security Level | Performance Impact | Use Case
-----------------|----------------|-------------------|----------
TEE Native       | High           | Minimal           | Static
IO Intercept     | High           | Low-Medium        | Dynamic
dm-verity        | High           | High              | Not Needed
```

### Performance Analysis & Benchmarks

```
┌──────────────────────────────────────────────────┐
│           Protection Method Overhead              │
│                                                  │
│    Operation Type     dm-verity    IO Intercept  │
│    ┌──────────┐      ┌───────┐    ┌─────────┐   │
│    │ Read     │──────│  40%  │    │   5%    │   │
│    │ Write    │──────│  N/A  │    │  10%    │   │
│    │ Random   │──────│  45%  │    │   8%    │   │
│    └──────────┘      └───────┘    └─────────┘   │
└──────────────────────────────────────────────────┘
```

#### Overhead Breakdown by Operation

```
Operation      | dm-verity | IO Interceptor | Notes
---------------|-----------|----------------|------------------------
Sequential Read| 40%       | 5%             | Batch processing helps
Random Read    | 45%       | 8%             | Page cache friendly
Write          | N/A       | 10%            | Selective encryption
Metadata Ops   | 35%       | 2%             | Minimal interception
```

#### Performance Optimization Techniques

```
Technique           | Benefit           | Implementation
--------------------|------------------|------------------
Selective Protection| 30% improvement  | Path-based rules
Batch Processing    | 20% improvement  | Operation queuing
Cache Optimization  | 15% improvement  | TEE-aware caching
```

#### Real-world Impact Analysis

```
Workload Type    | dm-verity      | IO Interceptor | Performance Gain
-----------------|----------------|----------------|----------------
ML Training      | 40% slowdown   | 8% slowdown    | 32% faster
Model Inference  | 35% slowdown   | 5% slowdown    | 30% faster
Data Loading     | 42% slowdown   | 7% slowdown    | 35% faster
```

#### Memory Usage Comparison

```
Component        | dm-verity    | IO Interceptor
-----------------|--------------|---------------
Runtime Memory   | 256MB+       | 50MB baseline
Page Cache       | Required     | Optional
Hash Storage     | Full disk    | Selected paths
```

### Storage Protection Analysis: IO Interceptor vs dm-verity

### Performance & Protection Comparison

```
┌──────────────────────────────────────────┐
│        Storage Protection Methods        │
│                                         │
│   dm-verity          IO Interceptor     │
│  ┌─────────┐         ┌──────────┐      │
│  │ Block   │         │ Selective│      │
│  │ Level   │         │   I/O    │      │
│  └─────────┘         └──────────┘      │
│      │                    │            │
│  All Blocks         Critical Paths      │
│   40% OH              5-10% OH         │
└──────────────────────────────────────────┘
```

#### Key Differences
```
Feature          | dm-verity         | IO Interceptor
-----------------|------------------|----------------
Protection Level | Block-level hash | File-level crypto
Write Support    | Read-only        | Read-write
Memory Usage     | High (hash tree) | Low (selective)
Runtime Changes  | Not allowed      | Supported
```

#### Workload Impact
```
ML Operation     | dm-verity Impact | IO Interceptor
-----------------|-----------------|----------------
Model Loading    | 40% slower      | 5% slower
Checkpointing    | Not supported   | 10% overhead
Training I/O     | 40% slower      | 8% slower
```

#### Recommendation
For ML workloads in TEE:
- Use IO Interceptor for better performance
- Maintain equivalent security through TEE integration
- Enable dynamic operations (checkpointing, saves)
```

### Network Traffic Shaping Analysis

```
┌────────────────────────────────────────────────┐
│               Traffic Shaping                  │
│                                               │
│  Original Traffic       Shaped Traffic        │
│  ┌──────────┐          ┌──────────┐          │
│  │ ML Data  │    →     │Randomized│          │
│  │ Patterns │          │ Patterns │          │
│  └──────────┘          └──────────┘          │
│                                              │
│  • Burst transfers     • Constant rate       │
│  • Predictable size    • Random padding      │
│  • Regular timing      • Variable delays     │
└────────────────────────────────────────────────┘
```

#### Traffic Pattern Obfuscation

```
Pattern Type    | Risk                  | Shaping Technique
----------------|----------------------|------------------
Size Pattern    | Model structure leak | Fixed-size packets
Timing Pattern  | Operation inference  | Random delays
Burst Pattern   | Batch size leak      | Traffic spreading
```

#### Implementation Methods

```c
typedef struct {
    struct {
        size_t min_packet_size;     // Force minimum size
        size_t random_padding;      // Add random padding
        bool normalize_size;        // Use fixed sizes
    } size_control;

    struct {
        uint32_t min_delay_ms;      // Minimum delay
        uint32_t max_delay_ms;      // Maximum delay
        bool randomize_timing;      // Add random delays
    } timing_control;

    struct {
        size_t buffer_size;         // Burst control buffer
        float rate_limit;           // Transfer rate limit
        bool spread_traffic;        // Distribute bursts
    } burst_control;
} traffic_shaping_config_t;
```

#### Shaping Techniques

1. **Size Normalization**:
```
- Pad all packets to fixed size
- Add random padding
- Split large transfers
```

2. **Timing Randomization**:
```
- Add random delays
- Vary transmission rates
- Break predictable patterns
```

3. **Burst Control**:
```
- Buffer and spread traffic
- Rate limiting
- Randomize batch sizes
```

#### Security vs Performance Trade-offs

```
Shaping Level | Security Gain | Performance Impact
--------------|--------------|-------------------
Minimal      | Low          | 5% overhead
Standard     | Medium       | 10-15% overhead
Aggressive   | High         | 20-25% overhead
```

### Core Dump Security Analysis

```
┌────────────────────────────────────────────────┐
│               Core Dump Risks                  │
│                                               │
│  Protected Memory       Core Dump File        │
│  ┌──────────┐          ┌──────────┐          │
│  │ ML Model │    →     │ Memory   │          │
│  │ Keys     │          │ Snapshot │          │
│  │ Data     │          │ (Exposed)│          │
│  └──────────┘          └──────────┘          │
│                                              │
│  TEE Protection        No Protection         │
│  └──────────────────────────────────────────┘
```

#### Core Dump Security Risks

```
Component     | Risk Description        | Impact Level
--------------|------------------------|-------------
Model State   | Full memory exposure   | Critical
Crypto Keys   | Key material leaked    | Critical
Runtime Data  | Training data exposed  | High
TEE Memory    | Protected data leaked  | Critical
```

#### Comprehensive Core Dump Prevention

```
┌────────────────────────────────────────────────┐
│           Core Dump Prevention Layers          │
│                                               │
│  Kernel Level        Application Level        │
│  ┌──────────┐        ┌──────────────┐        │
│  │sysctl    │        │prctl() calls │        │
│  │settings  │        │              │        │
│  └──────────┘        └──────────────┘        │
│       │                     │                 │
│  System-wide          Process-specific        │
│ └────────────────────────────────────────┘
```

#### Multi-Layer Prevention Strategy

```bash
# 1. Kernel-Level Prevention
## Disable core dumps completely
sysctl -w kernel.core_pattern=|/bin/false
sysctl -w kernel.core_pipe_limit=0
sysctl -w fs.suid_dumpable=0

## Restrict core dump permissions
sysctl -w kernel.core_uses_pid=0
sysctl -w kernel.core_setuid=0

# 2. Process-Level Prevention
## Using prctl
prctl(PR_SET_DUMPABLE, 0)
prctl(PR_SET_PTRACER, 0)

## Using resource limits
ulimit -c 0
setrlimit(RLIMIT_CORE, {0, 0})
```

#### Filesystem Hardening

```bash
# Protect core pattern file
chattr +i /proc/sys/kernel/core_pattern
mount -o remount,ro /proc/sys/kernel/

# Restrict core dump directory
chmod 000 /var/crash/
chmod 000 /var/lib/systemd/coredump/
```

#### Runtime Monitoring

```c
typedef struct {
    struct {
        bool monitor_core_pattern;    // Watch for changes
        bool monitor_sysctl;         // Watch sysctl changes
        bool monitor_ulimit;         // Watch ulimit changes
    } core_monitoring;

    struct {
        void (*pattern_change_handler)(void);  // Handle changes
        void (*dump_attempt_handler)(void);    // Handle attempts
        bool log_all_attempts;                // Logging control
    } handlers;

    struct {
        char* allowed_patterns[MAX_PATTERNS];  // Whitelist
        bool enforce_whitelist;               // Enforce policy
        bool alert_on_violation;             // Alert control
    } policy;
} core_dump_monitor_t;
```

#### Crash Handling Without Core Dumps

```c
void secure_crash_handler(int signal) {
    // 1. Secure memory cleanup
    secure_wipe_sensitive_memory();
    
    // 2. Minimal logging (no memory dumps)
    log_crash_minimal_info();
    
    // 3. Secure process termination
    secure_process_exit();
}
```

### Attack Surface Categorization

```
┌──────────────────────────────────────────────────────┐
│                  Protection Domains                   │
│                                                      │
│ 1. Memory & TEE Protection                          │
│    ├── Runtime Memory Security                      │
│    ├── Resource Control (CPU, Memory limits)        │
│    └── Core Dump Prevention                         │
│                                                      │
│ 2. I/O & Storage Protection                         │
│    ├── Disk Modification Prevention                 │
│    ├── Input Validation & Sanitization             │
│    └── Privacy Controls                            │
│                                                      │
│ 3. Network & Protocol Security                      │
│    ├── Port & Access Control                       │
│    ├── Attestation Protocol Security               │
│    └── Traffic Pattern Protection                  │
└──────────────────────────────────────────────────────┘
```

Attack Mapping:
```
| Attack Vector | Protection Domain |
|---------------|-------------------|
| Disk Mod | I/O Protection |
| Network Int | Network Security |  
| Resource Mod | Memory & TEE |
```

#### Coverage Analysis

```
Attack Vector        | Protection Domain   | Implementation Status
--------------------|--------------------|-----------------
Disk Modification   | I/O Protection     | ✓ Implemented
Network Intercept   | Network Security   | ✓ Implemented
Resource Control    | Memory & TEE       | ✓ Implemented
Attestation Attack  | Network Security   | ✓ Implemented
Input Validation    | I/O Protection     | ✓ Implemented
Privacy Control     | I/O Protection     | ✓ Implemented
```

### Build Image Security Analysis

```
┌────────────────────────────────────────────────┐
│             Build Image Security               │
│                                               │
│  Build Time           Runtime                 │
│  ┌──────────┐        ┌──────────┐           │
│  │Source    │        │Image     │           │
│  │Integrity ├───────>│Integrity │           │
│  └──────────┘        └──────────┘           │
│       │                   │                  │
│  Supply Chain        Measurement            │
│  Protection          Verification           │
└────────────────────────────────────────────────┘
```

#### Build Time Security Controls

```
Component         | Risk                | Protection Measure
------------------|--------------------|-----------------
Base Image        | Supply chain       | Signed base image
Dependencies      | Malicious packages | Verified sources
Build Environment | Tampering          | Secure pipeline
Build Scripts     | Injection attacks  | Code review + sign
```

#### Image Hardening Requirements

```
Layer              | Hardening Measure          | Verification
-------------------|---------------------------|-------------
OS Layer           | Minimal base image        | Size check
System Utils       | Remove unnecessary tools  | Tool audit
Security Config    | Strict default settings  | Config scan
Application Layer  | Read-only filesystem     | Mount check
```

#### Runtime Verification

```c
typedef struct {
    struct {
        uint8_t image_measurement[32];  // Expected measurement
        uint8_t build_signature[64];    // Build signature
        char* build_id;                 // Build identifier
    } image_identity;

    struct {
        bool verify_base_image;         // Base image check
        bool verify_packages;           // Package verification
        bool enforce_read_only;         // RO filesystem
    } runtime_controls;
} image_security_t;
```

#### Build Pipeline Security

```
Stage          | Security Measure        | Validation
---------------|------------------------|------------
Source         | Signed commits         | Git verify
Dependencies   | Lock files + checksums | Hash verify
Build Env      | Isolated + attested   | TEE verify
Output         | Signed + measured     | PCR check
```

#### Security Best Practices

1. **Source Control**:
```
- Use signed commits
- Protected branches
- Code review enforcement
- Automated security scans
```

2. **Build Process**:
```
- Reproducible builds
- Minimal base image
- Package verification
- Layer optimization
```

3. **Runtime Protection**:
```
- Read-only filesystem
- Measured launch
- Runtime attestation
- Integrity monitoring
```

### Resource Control Protection Details

```
┌────────────────────────────────────────────────┐
│            Resource Control Security           │
│                                               │
│  Static Limits         Runtime Monitoring     │
│  ┌──────────┐         ┌──────────────┐       │
│  │Memory Cap│         │Resource      │       │
│  │CPU Bound │         │Usage Tracking│       │
│  │Disk Quote│         │Anomaly Check │       │
│  └──────────┘         └──────────────┘       │
└────────────────────────────────────────────────┘
```

#### Resource Control Mechanisms

```
Resource Type | Static Limit        | Runtime Protection
--------------|--------------------|-----------------
Memory        | Max 80% of TEE mem | Monitor page faults
CPU           | Max 90% usage      | Track CPU spikes
Storage       | Fixed quota        | Watch I/O patterns
Network       | Bandwidth cap      | Monitor throughput
```

#### Protection Against Resource-Based Attacks

```
Attack Vector     | Risk              | Mitigation
------------------|------------------|------------------
Memory Exhaustion | OOM condition    | Hard memory limits
CPU Starvation   | DoS attempt      | CPU quota enforce
Disk Flooding    | Storage overflow | Strict quotas
Network Flood    | Bandwidth abuse  | Rate limiting
```

#### Implementation

```c
typedef struct {
    struct {
        size_t max_memory_mb;      // Memory limit
        int max_cpu_percent;       // CPU limit
        size_t max_storage_gb;     // Storage quota
        size_t max_bandwidth_mbps; // Network limit
    } static_limits;

    struct {
        uint32_t check_interval_ms;    // Monitor frequency
        float threshold_percent;       // Alert threshold
        bool enforce_hard_limits;      // Force termination
    } runtime_controls;

    struct {
        void (*resource_violation_handler)(void);  // Handle violations
        void (*alert_handler)(void);              // Handle alerts
        bool log_violations;                      // Audit logging
    } handlers;
} resource_control_t;
```

### Security Risk Matrix

| Risk Category | Operations | Risk Level | TEE Coverage | Additional Measure |
|---------------|------------|-----------|--------------|------------------|
| Memory & TEE | Runtime Memory | Critical | ✓ Full | None needed |
| | Resource Ctrl | High | Partial | Resource Monitoring |
| | Core Dumps | Critical | × None | Multi-layer Block |
| | Debug/Crash | Critical | × None | Dump Prevention |
| | Page Files | Critical | × None | Encrypt + Lock |
| CPU & State | VMEXIT Events | High | Partial | Pattern Hiding |
| | CPU Usage | Medium | Partial | Rate Limiting |
| | State Trans. | High | Partial | Batch Operations |
| I/O & Storage | Disk Access | High | × None | IO Interception |
| | Model Save | Critical | × None | Encrypt + Validate |
| | Temp Files | Medium | Partial | TEE Memory tmpfs |
| Network | ML Training | High | × None | Port Control |
| | Attestation | Critical | Partial | Protocol Valid |
| | Traffic Shape | Medium | × None | Pattern Hiding |
| Build & Deploy | Image Build | High | ✓ Full | Signing |
| | OEM Partition | Medium | ✓ Full | Seal at Build |
| | Config Files | High | × None | Encrypt+Integrity |
| Input/Privacy | Data Input | High | × None | Format Validation |
| | | Privacy Bounds | Critical | × None | Privacy Controls |
| | | Data Skew | Medium | × None | Statistical Check |

Notes:
- Risk Level: Critical > High > Medium > Low
- TEE Coverage: ✓ Full = Native TEE Protection, Partial = Some TEE Support, × None = No TEE Protection
- All protections undergo continuous validation
```

### Tmpfs in TEE Memory

```
┌────────────────────────────────────────────────┐
│               TEE Memory Space                 │
│                                               │
│  Protected Memory     tmpfs (RAM-based)       │
│  ┌──────────┐        ┌──────────────┐        │
│  │App Data  │        │Temp Files    │        │
│  │ML Model  │        │Swap Space    │        │
│  └──────────┘        └──────────────┘        │
│       ✓                     △                 │
│    TEE Protected        TEE Protected          │
│                      (until swap-out)        │
│       └──────────────────────────────────────┘
```

#### Memory Mapping Considerations

```
Location      | Protection Status | Risk Factor
--------------|------------------|-------------
RAM tmpfs     | TEE Protected    | Safe while in memory
Swap Space    | Exposed          | Risk during swap-out
Disk Fallback | Exposed          | Risk if memory full
```

#### Implementation Requirements

```bash
# Mount tmpfs with strict memory limits
mount -t tmpfs -o size=2G,nr_inodes=10k,mode=1700,noexec,nosuid tmpfs /tmp

# Prevent swap-out of tmpfs
mlock("/tmp", MS_LOCK)

# Monitor memory pressure
vm.min_free_kbytes=524288    # Maintain memory headroom
vm.swappiness=0              # Minimize swapping
```

### Configuration Files Security

```
┌────────────────────────────────────────────────┐
│               System Configuration             │
│                                               │
│    Inside TEE              Outside TEE        │
│  ┌──────────┐            ┌──────────┐        │
│  │App Config│            │OS Config │        │
│  │(Runtime) │            │(System)  │        │
│  └──────────┘            └──────────┘        │
│  TEE Protected           Need Protection      │
│ └────────────────────────────────────────────────┘
```

#### Configuration Types & Protection

```
Config Type     | Location     | Protection Needed
----------------|-------------|------------------
OS Config       | Outside TEE | Encrypt + Integrity
Network Config  | Outside TEE | Encrypt + Integrity
System Services | Outside TEE | Encrypt + Integrity
App Runtime     | Inside TEE  | Native Protection
```

#### Protection Requirements

```
Operation       | Risk            | Mitigation
----------------|----------------|-------------
Config Read     | Exposure       | Encryption
Config Modify   | Tampering      | Integrity Check
Config Load     | Race Condition | Atomic Updates
```

### Privacy Bounds Protection

```
┌────────────────────────────────────────────────┐
│               Privacy Controls                  │
│                                               │
│  Training Data         Model Access           │
│  ┌──────────┐         ┌──────────────┐       │
│  │PII Limits│         │Access Bounds │       │
│  │Data Mins │         │Query Limits  │       │
│  └──────────┘         └──────────────┘       │
└────────────────────────────────────────────────┘
```

#### Privacy Bounds Definition

```
Boundary Type    | Description                  | Protection Measure
-----------------|------------------------------|------------------
Data Minimization| Limit PII/sensitive data    | Data filtering
Access Control   | Restrict model access       | Query rate limits
Output Control   | Prevent data leakage       | Result sanitization
```

#### Implementation Examples

```c
typedef struct {
    struct {
        bool filter_pii;           // Remove personal data
        size_t min_batch_size;     // Minimum aggregation
        float noise_level;         // Differential privacy
    } data_controls;

    struct {
        uint32_t max_queries;      // Query rate limiting
        float confidence_thresh;   // Output thresholding
        bool sanitize_results;     // Clean model outputs
    } access_controls;
} privacy_bounds_t;
```

### Page File Security Analysis

```
┌────────────────────────────────────────────────┐
│               Memory Management                │
│                                               │
│  TEE Memory           Page Files              │
│  ┌──────────┐        ┌──────────────┐        │
│  │Protected │───┐    │Swap Space    │        │
│  │Memory    │   └───>│(Unprotected) │        │
│  └──────────┘        └──────────────┘        │
│       ✓                     ✗                 │
│    Encrypted          Outside TEE             │
│       └──────────────────────────────────────┘
```

#### Page File Risks

| Component | Location | Risk Level | Protection Status |
|-----------|----------|------------|------------------|
| Swap Space | Host Storage | Critical | × Not TEE Protected |
| Page File | Host Storage | Critical | × Not TEE Protected |
| Memory Pages | Host Storage | Critical | × Not TEE Protected |

#### Required Protections

```
Operation | Risk | Mitigation |
|-----------|------|------------|
| Page-out | Memory exposure | Encrypt before swap |
| Page-in | Data tampering | Integrity check |
| Swap Space | Data persistence | Secure wipe |
```

#### Implementation Strategy

```c
typedef struct {
    struct {
        bool disable_swap;          // Prevent swapping
        bool encrypt_pages;         // Encrypt if swapped
        bool secure_wipe;          // Clean after use
    } page_protection;

    struct {
        size_t reserved_memory;     // Keep in TEE
        bool lock_pages;           // Prevent page-out
        bool monitor_pressure;     // Watch memory use
    } memory_control;
} page_security_t;
```

#### Security Recommendations

1. **Primary Strategy**: Prevent Paging
```bash
# Disable swap
swapoff -a

# Lock pages in memory
mlockall(MCL_CURRENT | MCL_FUTURE)

# Set strict limits
vm.swappiness = 0
```

2. **Fallback Strategy**: Secure Paging
```bash
# Encrypt swap
cryptsetup luksFormat /dev/swap

# Secure wipe
shred -u /swapfile

# Monitor usage
vmstat -s
```

### Tool Organization

| Phase | Tool | Core Features |
|-------|------|--------------|
| 1 | IO Interceptor | - Path control<br>- TEE integration<br>- Encryption<br>- Memory management |
| 2 | Network Lock | - Port control<br>- Traffic shaping<br>- Protocol validation |
| 3 | Privacy Control | - Data filtering<br>- Access control<br>- Query limiting |
| 4 | CPU Manager | - VMEXIT protection<br>- Resource quotas |

### Development Priority & Dependencies

```
Phase | Tool             | Core Features
------|-----------------|--------------------
1     | IO Interceptor  | - Path control
       |                 | - TEE integration
       |                 | - Encryption
       |                 | - Memory management

2     | Network Lock    | - Port control
       |                 | - Traffic shaping
       |                 | - Protocol validation

3     | Privacy Control | - Data filtering
       |                 | - Access control
       |                 | - Query limiting

4     | CPU Manager     | - VMEXIT protection
       |                 | - Resource quotas
```

### Usage Examples

#### 1. Setting Up Network Lockdown
```bash
# Install required packages
sudo apt-get install iptables iptables-persistent

# Apply network rules
sudo ./setup_network_rules.sh

# Verify rules are active
sudo iptables -L

# Make rules persistent across reboots
sudo netfilter-persistent save
```

#### 2. Monitoring Network Activity
```bash
# Start monitoring in a separate terminal
sudo ./monitor_network.sh

# Check for violations
sudo tail -f /var/log/syslog | grep "BLOCKED"
```

#### 3. Validating Security Rules
```bash
# Run validation tests
sudo ./validate_security.sh

# Test specific port
nc -zv localhost 8002  # Should succeed
nc -zv localhost 22    # Should fail
```

### Troubleshooting Guide

#### Common Issues and Solutions

1. **ML Training Connection Failed**
```bash
# Check if rules are loaded
sudo iptables -L

# Verify port is allowed
sudo iptables -L | grep "8002"

# Temporarily allow for testing
sudo iptables -I INPUT -p tcp --dport 8002 -j ACCEPT
```

2. **Rules Not Persisting After Reboot**
```bash
# Save rules explicitly
sudo iptables-save > /etc/iptables/rules.v4

# Install persistent service
sudo apt-get install iptables-persistent
sudo netfilter-persistent save
```

3. **Blocked Legitimate Traffic**
```bash
# Check logs for blocked connections
sudo tail -f /var/log/syslog | grep "DROP"

# Temporarily disable rules for testing
sudo ./setup_network_rules.sh --disable

# Re-enable rules
sudo ./setup_network_rules.sh
```

4. **Emergency Access**
```bash
# Reset all rules (use with caution)
sudo iptables -F
sudo iptables -P INPUT ACCEPT
sudo iptables -P OUTPUT ACCEPT

# Re-apply rules after fixing issue
sudo ./setup_network_rules.sh
```

#### Validation Checklist
```
□ Required ports (8002,8003,8443,9443) are open
□ All other ports are blocked
□ Rules persist after reboot
□ Monitoring shows expected traffic
□ No unauthorized connections
```

#### Monitoring and Debugging
```bash
# Watch network connections
watch -n1 'netstat -tuln'

# Monitor dropped packets
sudo iptables -L -v

# Check connection attempts
sudo tcpdump -i any port 8002
```

### Usage Guide

#### Basic Setup
```bash
# Build and install
cd nvflare/tool/io_interceptor
make
sudo make install

# Enable interception for any program
export LD_PRELOAD=/usr/lib/libiointerceptor.so
```

#### Path Protection Configuration
```c
// Allow specific directories
register_whitelist_path("/path/to/training/data");
register_whitelist_path("/path/to/models");

// Configure system paths (read-only)
register_system_path("/etc/nvflare");

// Set temporary storage
register_tmpfs_path("/tmp/nvflare");
```

#### Secure Memory Usage
```c
// For sensitive data processing
memory_ctx_t* ctx = allocate_secure_memory(1024 * 1024, MEM_TEE);
if (ctx) {
    // Use the secure memory
    process_sensitive_data(ctx->addr, ctx->size);
    
    // Securely wipe and free
    free_secure_memory(ctx);
}
```

#### File Encryption
```c
// Automatic encryption for sensitive files
FILE* f = fopen("/path/to/sensitive/data", "w");
if (f) {
    fwrite(data, size, 1, f);
    fclose(f);  // Data is automatically encrypted
}
```

## Performance Considerations

### Memory Impact
- **Locked Memory**: Each locked memory region reduces available system memory
- **Encryption Overhead**: ~2-5% CPU overhead for encrypted file operations
- **Memory Limits**: Configure based on available TEE memory:
  ```bash
  # Example configuration
  export NVFLARE_MAX_LOCKED_MEM=1G    # Max locked memory
  export NVFLARE_MAX_TMPFS_SIZE=2G    # Max tmpfs size
  ```

### I/O Performance
- **File Operations**: 
  - Encrypted: 10-15% overhead
  - Unencrypted: 1-2% overhead
- **Memory Operations**:
  - Locked memory: Negligible impact
  - Encrypted memory: 5-10% overhead

### Optimization Tips
1. **Minimize Encrypted I/O**:
   - Use whitelist paths for non-sensitive data
   - Batch small I/O operations

2. **Memory Management**:
   - Pre-allocate secure memory when possible
   - Release unused secure memory promptly

3. **File Handling**:
   - Use appropriate path types (system vs tmpfs)
   - Consider buffer sizes for encrypted I/O

### Monitoring
```bash
# Check memory usage
cat /proc/meminfo | grep -i lock

# Monitor I/O performance
iostat -x 1

# Track encryption overhead
perf stat -e cycles,instructions,cache-misses ./your_program
```

## 3. Protection Measures

### Memory Protection Strategy
- TEE Integration for memory security
- Page file encryption and control
- Core dump prevention
- Resource limits and monitoring

### I/O Protection Strategy
- File operation security
  - Path-based access control
  - Encryption for sensitive data
  - Secure temporary storage
- System call interception
  - LD_PRELOAD mechanism
  - Operation validation
  - Pattern hiding

### Network Protection Strategy
- Port management and access control
- Traffic shaping and pattern hiding
- Protocol security measures

## 4. Implementation

### Architecture
The IO interceptor is implemented in C using LD_PRELOAD to intercept all I/O operations at the library level.

#### Components
1. **Core Interceptor** (`core/interceptor.c`)
   - Intercepts system I/O calls
   - Path validation
   - Integration with handlers

2. **Encryption Handler** (`handlers/encryption_handler.c`)
   - AES-256-GCM encryption
   - Key management
   - Encryption contexts

3. **Memory Handler** (`handlers/memory_handler.c`)
   - TEE memory allocation
   - Memory locking
   - Secure wiping

## 5. Performance Analysis

## 6. Usage Guide

## 7. Risk Areas Not Covered

### Memory & TEE Risks
- Side-channel attacks within TEE
- Cross-VM memory attacks
- Speculative execution attacks

### I/O Related Risks
- Application-level parsing vulnerabilities
- Malicious input data format attacks
- Data exfiltration through covert channels

### Network Protocol Risks
- Malformed attestation messages
- Protocol-level replay attacks
- Custom ML protocol vulnerabilities

### Build-time Risks
- Image tampering before TEE measurement
- Configuration injection during build
- Supply chain attacks