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
   - Network Security & Port Management
   - Risk Summary and Recommendations

3. Protection Measures
   - Memory Protection Strategy
   - I/O Protection Strategy
     - File Operation Security
     - System Call Interception
   - Network Protection Strategy
     - Port Management
     - Traffic Shaping
     - Protocol Security

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

**Why Side-Channels Matter**:
- TEE protects memory content but not access patterns
- Shared hardware resources remain observable
- Timing differences can leak information
- Power consumption can be monitored

#### Side-Channel Attack Details

1. **Cache Side-Channel Attack**
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

2. **Memory Bus Attack**
   - **How it works**:
     - Attacker monitors memory bus activity
     - Measures timing and frequency of memory accesses
     - Observes data transfer patterns
   - **What can be leaked**:
     - Data transfer sizes
     - Memory access frequency
     - Workload characteristics
   - **Example**: Attacker can infer batch size and model structure from memory transfer patterns

3. **Execution Timing Attack**
   - **How it works**:
     - Attacker measures operation completion time
     - Different data causes different execution paths
     - Timing variations leak information
   - **What can be leaked**:
     - Control flow paths
     - Data-dependent operations
     - Algorithm behavior
   - **Example**: Attacker can infer model complexity from operation timing

#### Mitigation Effectiveness

| Attack Type | Mitigation | Effectiveness | Trade-off |
|-------------|------------|---------------|-----------|
| Cache | Cache partitioning | High | Performance impact |
| Cache | Constant-time ops | High | Code complexity |
| Memory Bus | Access batching | Medium | Latency increase |
| Memory Bus | Dummy accesses | Medium | Bandwidth waste |
| Timing | Random delays | Medium | Performance impact |
| Timing | Operation batching | High | Response latency |

| Category | Risk | Level | Mitigation |
|----------|------|-------|------------|
| **Memory & TEE** |
| Cache Side-channel | - Model architecture leakage<br>- Training pattern exposure<br>- Potential key extraction | CRITICAL | - Cache partitioning<br>- Cache line padding<br>- Constant-time operations |
| Memory Bus | - Data size leakage<br>- Workload pattern exposure<br>- Memory access timing | HIGH | - Memory access randomization<br>- Dummy accesses<br>- Access batching |
| Execution Timing | - Algorithm behavior leakage<br>- Control flow exposure<br>- Operation complexity | HIGH | - Operation batching<br>- Random delays<br>- Constant-time algorithms |
| Cross-VM | Cross-VM memory attacks | HIGH | IOMMU<br>- Memory isolation<br>- VM pinning |
| Speculative | Speculative execution attacks | HIGH | CPU mitigations |
| **I/O Operations** |
| Application | - Higher level app vulnerabilities<br>- Framework-specific issues | MEDIUM | Requires application-level fixes |
| Data Format | - Buffer overflows<br>- Data corruption<br>- System crashes | HIGH | Format verification |
| Exfiltration | Covert channel data leaks | HIGH | I/O monitoring |
| **Network Protocol** |
| Attestation | - Protocol-level vulnerabilities | MEDIUM | Requires TEE vendor fixes |
| Protocol | - Session hijacking<br>- Data manipulation<br>- Service disruption | HIGH | Nonce + timestamps |
| ML Protocol | Custom ML protocol vulnerabilities | HIGH | Protocol hardening |
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
   | Build ID | Identification | 32-byte unique build identifier |
   | Runtime Integrity | Monitoring | Continuous integrity checks |
   | Reproducible Builds | Build verification | Ensure build reproducibility |
   | Build Environment | Environment security | Attestation of build environment |
   | Source Verification | Code integrity | Verify source code authenticity |
   | Image Signing | Image integrity | Sign all build artifacts |
   | Version Control | Build tracking | Track all build versions |
   | Artifact Tracking | Supply chain | Track build artifact lineage |
   | Integrity Monitoring | Runtime security | Continuous integrity verification |
   | Attestation Chain | Security proof | Complete attestation inclusion |
   | Version Verification | Runtime verification | Verify running version |

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

The port lockdown approach:

1. **Default Policy**: Block all incoming and outgoing traffic
2. **Essential Ports**:
   | Port | Purpose |
   |------|---------|
   | 8002 | ML Training Communication |
   | 8003 | ML Training Communication |
   | 8443 | Secure ML Operations |
   | 9443 | TEE Attestation |

3. **Connection Rules**:
   - Allow incoming connections only to essential ports
   - Allow outgoing responses from services
   - Allow established connections
   - Drop all other traffic

This configuration ensures:
- Minimal attack surface
- Only required ports are open
- Secure communication channels
- No unauthorized access

#### Runtime Network Validation

1. **Port Configuration**:
   | Requirement | Setting | Purpose |
   |------------|---------|---------|
   | Allowed Ports | 8002, 8003, 8443, 9443 | Essential service ports |
   | Block Other Ports | Yes | Prevent unauthorized access |
   | Log Blocked Attempts | Yes | Security monitoring |

2. **Service Control**:
   | Service | Status | Reason |
   |---------|--------|--------|
   | SSH | Disabled | No remote access needed |
   | HTTP | Disabled | No web services |
   | Management | Disabled | No remote management |

This approach:
- Clearly defines network security requirements
- Easy to understand and audit
- Separates policy from implementation
- Maintainable documentation

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
   | Network | Traffic analysis |
   | System | Call patterns |

3. **Deployment Checklist**:
   - [ ] TEE Enabled
   - [ ] I/O Intercepted
   - [ ] Network Secured
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
| Cache Side-channel | - Model architecture leakage<br>- Training pattern exposure<br>- Potential key extraction | CRITICAL | Requires CPU/hardware support |
| Memory Bus | - Data size leakage<br>- Workload pattern exposure<br>- Memory access timing | HIGH | Requires hardware support |
| **I/O Operations** |
| Application | - Higher level app vulnerabilities<br>- Framework-specific issues | MEDIUM | Requires application-level fixes |
| **Network Protocol** |
| Attestation | - Protocol-level vulnerabilities | MEDIUM | Requires TEE vendor fixes |

Note: These risks are outside the scope of the I/O interceptor and require:
- Hardware vendor support
- Application-level security
- TEE vendor implementation
- Framework-specific fixes

Risk Level Legend:
- CRITICAL: Immediate business impact, requires urgent mitigation
- HIGH: Significant impact, requires planned mitigation
- MEDIUM: Moderate impact, should be addressed
- LOW: Minor impact, can be accepted with monitoring
 