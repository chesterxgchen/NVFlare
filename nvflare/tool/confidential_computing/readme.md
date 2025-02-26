# NVFlare IO Interceptor


## Table of Contents

1. Goals and Overview
   - Purpose and Objectives
   - Integration with TEE
   - Protection Scope

2. Risk Analysis
   - Security Requirements
   - Threat Categories
   - Attack Surface Analysis
   - OEM Partition Analysis
     - Architecture
     - Build vs Runtime Context
     - Security Analysis
   - Detailed Attack Vectors Analysis
   - Comprehensive Mitigation Strategy
   - Risk Summary and Recommendations

3. Protection Measures
   - Memory Protection Strategy
   - I/O Protection Strategy
     - File Operation Security
     - System Call Interception

4. Implementation
   - Architecture
   - Components
     - Core Interceptor
     - Encryption Handler
     - Memory Handler
   - Implementation Strategy
     - OS Protection
     - Model Protection
     - Pattern Protection

5. Performance Analysis
   - Storage Protection Comparison
   - Performance & Protection Analysis

6. Usage Guide
   - Network Lockdown Setup
   - Monitoring
   - Validation
   - Troubleshooting

7. Risk Areas Not Covered
   - Memory & TEE Risks
   - I/O Related Risks
   - Build-time Risks
 
### Purpose and Objectives
A system-level IO protection mechanism designed to complement VM-based Trusted Execution Environments (TEEs) like Intel TDX and AMD SEV-SNP by securing I/O operations that are not protected by memory encryption.

### Protection Scope
- File I/O operations
- Memory operations
- System call interception

## 2. Risk Analysis

### Risk Categories and Mitigations

#### TEE Protection Analysis

| Protection Type | TEE Coverage | Remaining Risk |
|----------------|--------------|----------------|
| Memory Content | ✓ Protected | None - Encrypted memory |
| Memory Integrity | ✓ Protected | None - Integrity checks |
| Memory Isolation | ✓ Protected | None - Hardware isolation |
| Cache Timing | ✗ Limited | Timing side-channels |
| Power Analysis | ✗ Limited | Power side-channels |
| Resource Sharing | ✗ Limited | Contention channels |

| Category | Risk | Level | Mitigation |
|----------|------|-------|------------|
| **Memory & TEE** |
| Side-channel | **Cache Timing:**<br>- Requires physical access<br>- Sophisticated hardware attack<br>- Limited data extraction | LOW | **TEE Protection:**<br>- Hardware isolation<br>- Memory encryption<br>- Cache isolation |
| Execution Timing | - Algorithm behavior leakage<br>- Control flow exposure<br>- Operation complexity | HIGH | - Operation batching<br>- Random delays<br>- Constant-time algorithms |
| Cross-VM | Cross-VM memory attacks | HIGH | IOMMU<br>- Memory isolation<br>- VM pinning |
| Speculative | Speculative execution attacks | HIGH | CPU mitigations |
| **I/O Operations** |
| **Build Process** |
| Image | - Malicious code injection<br>- Backdoor insertion<br>- Security bypass | CRITICAL | Secure boot chain |
| Configuration | - Security misconfiguration<br>- Policy bypass<br>- Access control failure | HIGH | Config encryption |
| Supply Chain | Supply chain attacks | HIGH | Build verification |

These risks are addressed through:
- Comprehensive security requirements
- Multi-layer protection strategy
- Continuous monitoring and validation
- Regular security assessments

### Security Requirements

1. **Build and Runtime Security**:

   | Requirement | Purpose | Description |
   |------------|---------|-------------|
   | Build Signature | Build integrity | Verify build signature |
   | Attestation | Runtime proof | Include in TEE attestation |
   | Runtime Integrity | Monitoring | Continuous integrity checks |
   | Image Signing | Image integrity | Sign all build artifacts |
   | Integrity Monitoring | Runtime security | Continuous integrity verification |

2. **OEM Protection**:

   | Component | Requirement | Description |
   |-----------|------------|-------------|
   | Boot Measurement | Expected measurement | 32-byte boot measurement validation |
   | Signature | Verify signature | Signature verification for binaries |
   | Configuration | Encrypt config | Configuration file encryption |

3. **Launch Protection**:

   | Component | Requirement | Description |
   |-----------|------------|-------------|
   | Binary Control | Whitelist binaries | List of allowed executables |
   | Runtime Check | Continuous verification | Ongoing integrity checks |
   | Config Loading | Secure loading | Secure configuration handling |

4. **Side-Channel Attack**

4.1 **Why Side-Channels Matter**:
   - TEE protects memory content but not access patterns
   - Shared hardware resources remain observable
   - Timing differences can leak information
   - Power consumption can be monitored

4.2 **Cache Side-Channel Attack**

- **How it works**:
  - Attacker and victim share CPU cache lines
  - Attacker measures memory access times
  - Fast access = cache hit (victim accessed data)
  - Slow access = cache miss (victim didn't access)
- **What can be leaked**:
  - Memory access patterns
  - Cryptographic keys
  - Model architecture details
  - **Example**: Attacker can determine which model layers are active by monitoring cache access patterns

4.3. **Memory Bus Attack**
- **How it works**:
  - Attacker monitors memory bus activity
  - Measures timing and frequency of memory accesses
  - Observes data transfer patterns
- **What can be leaked**:
  - Data transfer sizes
  - Memory access frequency
  - Workload characteristics
- **Example**: Attacker can infer batch size and model structure from memory transfer patterns

4.4 **Execution Timing Attack**

    - **How it works**:
        - Attacker measures operation completion time
        - Different data causes different execution paths
        - Timing variations leak information

    - **What can be leaked**:
        - Control flow paths
        - Data-dependent operations
        - Algorithm behavior
    - **Example**: Attacker can infer model complexity from operation timing

4.4 Mitigation Effectiveness

| Attack Type | Mitigation | Effectiveness | Trade-off |
|-------------|------------|---------------|-----------|
| Cache | Cache partitioning | High | Performance impact |
| Cache | Constant-time ops | High | Code complexity |
| Memory Bus | Access batching | Medium | Latency increase |
| Memory Bus | Dummy accesses | Medium | Bandwidth waste |
| Timing | Random delays | Medium | Performance impact |
| Timing | Operation batching | High | Response latency |

### Threat Categories
- Runtime Memory Threats
- I/O Operation Threats
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

### OEM Partition Analysis
#### Architecture
```
┌────────────────────────────────────────────────────┐
│                  Confidential VM                   │
│                                                    │
│  ┌──────────────┐    ┌──────────┐    ┌─────────┐  │
│  │ OEM Partition│    │ root-fs  │    │ tmp-fs  │  │
│  │ (launcher)   │    │(sealed)  │    │(volatile│  │
│  └──────┬───────┘    └────┬─────┘    └────┬────┘  │
│         │                 │                │       │
│         └─────────────────┘                │       │
│                     │                      │       │
│              Host Storage                  │       │
└──────────────────────────────────────────────────────┘
```

#### Build vs Runtime Context
| Phase | Traditional Risk | In Self-Built Image |
|-------|-----------------|---------------------|
| Build Time | HIGH | LOW (Controlled) |
| Distribution | HIGH | LOW (Signed) |
| Runtime | MEDIUM | LOW (TEE Protected) |

#### Security Analysis
| Component | Risk Level | Attack Vector | Mitigation |
|-----------|------------|---------------|------------|
| Launcher Binary | LOW | Binary tampering | Measured at boot |
| Config Files | MEDIUM | Configuration leak | Encrypt sensitive |
| Static Assets | LOW | Asset modification | Integrity check |

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
System Calls  | Pattern hiding + batching
Temp Files    | Memory-only + secure cleanup


3. **System Integration**
    - Works with system hardening
    - Complements TEE protection
    - Focus on I/O and memory security

### Risk Summary and Recommendations

| Priority | Component | Risk | Mitigation |
|----------|-----------|------|------------|
| P0 | Model Data | Extraction | Encryption |
| P0 | Runtime Memory | Page Exposure | TEE + Wipe |
| P1 | Filesystem | Data Residue | Secure Delete |
| P1 | System Calls | Timing Analysis | Randomization |
| P2 | Build Process | Image Tampering | Signing |

### Implementation Requirements

1. **Core Security Features**:

   | Feature | Requirement | Purpose |
   |---------|------------|---------|
   | Encryption Layers | Minimum 3 | Multi-layer protection |
   | Padding | Random size | Hide data patterns |
   | Traffic Noise | Enabled | Traffic pattern obfuscation |
   | Memory Cleanup | Secure wipe | Remove sensitive data |

2. **Monitoring Requirements**:

   | Component | Metrics to Monitor |
   |-----------|-------------------|
   | Memory | Page faults, swaps |
   | I/O | Patterns, timing |
   | System | Call patterns |

3. **Deployment Checklist**:

   - [ ] TEE Enabled
   - [ ] I/O Intercepted
   - [ ] Memory Protected

### Runtime I/O Attack Analysis

```
┌──────────────────────────────────────────────────────┐
│                   I/O Attack Surface                  │
│                                                      │
│    OS Level                  Application Level       │
│  ┌──────────┐               ┌──────────────┐         │
│  │ Page/Swap│               │ Model Save   │         │
│  │ VMEXIT   │               │ Checkpoints  │         │
│  │ tmp-fs   │               │ Gradients    │         │
│  └─────┬────┘               └──────┬───────┘         │
│        │                          │                  │
│        └──────────────────────────┘                  │
│                     │                                │
│              Host Monitoring                         │
└──────────────────────────────────────────────────────┘
```

#### 1. OS-Level I/O Risks


Operation Type | Risk Description | Mitigation Strategy
---------------|------------------|-------------------
Page Files | Memory pages written to untrusted storage | - Encrypt page content<br>- Secure page cleanup<br>- Minimize swapping
VMEXIT Events | Host can observe timing and frequency of exits | - Batch operations<br>- Add random delays<br>- Noise injection
tmp-fs Access | Temporary data exposed through filesystem | - Memory-only tmp-fs<br>- Encrypted if needed<br>- Secure wipe


#### 2. Model Theft Prevention


Risk Scenario | Attack Method | Protection Measure
---------------|---------------|-------------------
Direct Save | Save to unprotected directory | - Whitelist paths<br>- Encrypt all saves<br>- Path validation
Checkpointing | Capture intermediate model states | - Secure checkpoints<br>- Encrypted storage<br>- Clean old states
Gradient Capture | Collect training progress data | - Encrypt gradients<br>- Secure aggregation<br>- Memory-only ops


#### 3. I/O Pattern Monitoring


Pattern Type | Information Leaked | Countermeasure
--------------|-------------------|----------------
Size Patterns | - Model architecture<br>- Layer dimensions<br>- Batch sizes | - Fixed size padding<br>- Random padding<br>- Size obfuscation
Timing Patterns | - Training progress<br>- Iteration count<br>- Layer complexity | - Random delays<br>- Operation batching<br>- Noise injection
Access Patterns | - Training phase<br>- Model structure<br>- Data organization | - Pattern hiding<br>- Random access<br>- Access batching


#### Implementation Strategy

1. **OS Protection**:
 
   | Feature | Purpose | Strategy |
   |---------|---------|----------|
   | Page Encryption | Page file protection | Encrypt swapped pages |
   | Swap Management | Reduce page outs | Minimize swapping |
   | Secure Buffer | Sensitive data protection | Keep in TEE memory |

2. **Model Protection**:

   | Feature | Purpose | Strategy |
   |---------|---------|----------|
   | Whitelist Paths | Control save locations | Define allowed paths |
   | Encryption Layers | Data protection | Multiple encryption |
   | Checkpoint Security | Protect model states | Secure checkpoint handling |

3. **Pattern Protection**:

   | Feature | Purpose | Strategy |
   |---------|---------|----------|
   | Size Padding | Hide data size | Minimum padding size |
   | Timing | Hide operations | Random delays |
   | Access Patterns | Hide behavior | Pattern obfuscation |

This approach:
- Provides comprehensive I/O protection
- Covers multiple attack vectors
- Maintains clear security boundaries
- Enables easy auditing

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

### I/O Interceptor Usage

#### 1. Basic Setup
```python
# Example PyTorch training script
import torch
from io_interceptor import IOInterceptor, ProtectionMode

# Initialize secure I/O with configuration
io_interceptor = IOInterceptor(
    whitelist_paths=[
        "/workspace/checkpoints",
        "/workspace/models"
    ],
    protection_mode=ProtectionMode.ENCRYPT,
    random_padding=True
)

model = MyModel()

# Use context manager for specific protection settings
with io_interceptor.protect():
    # Case 1: Save to whitelisted path - ALLOWED & ENCRYPTED
    torch.save(model.state_dict(), '/workspace/checkpoints/model.pt')

# Different protection mode for different operations
with io_interceptor.protect(mode=ProtectionMode.IGNORE):
    # Case 2: Save to non-whitelisted path - IGNORED with WARNING
    torch.save(model.state_dict(), '/tmp/model.pt')

# System files not affected
with open('/etc/hosts', 'r') as f:
    content = f.read()
```

#### 2. Protection Modes
```python
from io_interceptor import IOInterceptor, ProtectionMode

# Configure different protection modes
io_interceptor = IOInterceptor(
    whitelist_paths=["/workspace/checkpoints"],
    protection_mode=ProtectionMode.ENCRYPT  # Default mode
)

# Use ENCRYPT mode
with io_interceptor.protect():
    torch.save(model, "model.pt")  # Encrypted with checkpoint key

# Use IGNORE mode
with io_interceptor.protect(mode=ProtectionMode.IGNORE):
    torch.save(model, "temp.pt")  # Write ignored, warning logged
```

#### 3. Path Configuration
```bash
# Single path
export IO_WHITELIST_PATH=/workspace/checkpoints

# Multiple paths
export IO_WHITELIST_PATH=/workspace/checkpoints:/workspace/models

# Pattern matching
export IO_WHITELIST_PATH=/workspace/checkpoints/*.pt:/workspace/models/*
```

#### 4. Validation
```bash
# Test whitelist paths
./test_io.sh --test-whitelist

# Verify encryption
./test_io.sh --verify-encryption

# Check protection mode
./test_io.sh --check-mode
```

#### 5. Troubleshooting
```bash
# Check interceptor logs
tail -f /var/log/io_interceptor.log

# Verify interceptor loading
ldd /path/to/application | grep interceptor

# Temporarily disable for testing
unset LD_PRELOAD
```

### Network Lockdown Setup

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


<!-- ## Quick Start

### Apply Security Settings
```bash
# Apply security configuration
sudo ./secure_build.sh

# Verify configuration
sudo ./validate_security.sh
``` -->

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

## 7. Risk Areas Not Covered

### Scope of Current Implementation
Our implementation provides:
- System call interception for I/O operations
- Path-based access control
- Encryption for non-whitelisted paths
- Basic pattern hiding

### Residual Risks (Outside Current Scope)
| Risk Category | Risk | Impact | Risk Level | Mitigation Strategy |
|--------------|------|---------------|-------------------|-------------------|
| **Memory & TEE** |
| Side-channel | **Cache Timing:**<br>- Requires physical access<br>- Sophisticated hardware attack<br>- Limited data extraction | LOW | **TEE Protection:**<br>- Hardware isolation<br>- Memory encryption<br>- Cache isolation |
| **Build Process** |
| Image | - Malicious code injection<br>- Backdoor insertion<br>- Security bypass | CRITICAL | Secure boot chain |
| Configuration | - Security misconfiguration<br>- Policy bypass<br>- Access control failure | HIGH | Config encryption |
| Supply Chain | Supply chain attacks | HIGH | Build verification |

Note: These risks are outside the scope of the I/O interceptor because:
- Our interceptor works at system call level
- Can't protect against bugs in ML frameworks
- Can't fix flaws in TEE vendor code
- Application logic must be secured separately

#### Note on side-channel attack

##### Attack Prerequisites in TEE:
* Attacker needs to be co-located in same physical machine
* Must bypass TEE isolation
* Must have precise timing measurements
* Must know what to look for in patterns

##### TEE Protection:
* Memory is encrypted
* Cache lines are isolated
* Memory bus is protected
* Hardware-level isolation

##### Realistic Attack Difficulty:
* Very sophisticated attack
* Requires hardware expertise
* Needs physical access
* Hard to extract meaningful data

### Network Security

#### Port Configuration
```
┌──────────────────────────────────────┐
│         Confidential VM              │
│                                      │
│  FL Ports        Monitoring   Attestation
│  8002 ◄──┐      9090 ◄──┐   9000 ◄──┐
│  8003 ◄──┤      9102 ◄──┤   9001 ◄──┤
│          │      8125 ◄──┘   9002 ◄──┘
│          │                           │
└──────────┼───────────────────────────┘
            │
┌──────────┴───────────────────────────┐
│         Network Security             │
│  - Port-specific access control      │
│  - Network isolation                 │
│  - Rate limiting                     │
│  - Connection tracking               │
└──────────────────────────────────────┘
```

#### Security Measures
- SSH disabled by default
- Network access restricted by CIDR
- Rate limiting per service type
- Connection limits enforced
- Traffic monitoring enabled