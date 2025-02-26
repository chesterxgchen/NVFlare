# NVFLARE Confidential Computing Security

## Overview

This document describes the security architecture of NVFLARE's confidential computing implementation, focusing on the integration between IO Interceptor and System Hardening components.

## Component Integration

### 1. Security Boundaries

```
┌──────────────────────────────────────┐
│         Confidential VM              │
│                                      │
│  ┌─────────────┐    ┌─────────────┐  │
│  │     IO      │    │   System    │  │
│  │ Interceptor │    │  Hardening  │  │
│  └─────────────┘    └─────────────┘  │
│     Storage/Memory     Network/Host   │
└──────────────────────────────────────┘
```

#### IO Interceptor Scope
- File I/O protection
- Memory operations security
- System call interception
- Storage encryption

#### System Hardening Scope
- Network security configuration
- Port and traffic management
- System lockdown
- Runtime protection

### 2. Configuration Management

#### **Network Security Configuration** (`security.conf`)
```bash
# FL Communication ports (comma-separated)
FL_PORTS="8002,8003"

# Allowed networks (CIDR notation, comma-separated)
ALLOWED_NETWORKS="10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"

# Connection limits
MAX_CONNECTIONS_FL=20
MAX_CONNECTIONS_ADMIN=5

# Rate limiting
RATE_LIMIT="100/minute"
```

#### **Configuration Validation**
     - Port range validation
     - Network CIDR format checking
     - Connection limit verification
     - Rate limit syntax validation


### 3. Security Flow

#### Initialization Sequence
1. Load security configuration
2. Apply system hardening rules
3. Initialize IO interceptor
4. Validate security settings

#### Runtime Protection
- **System Hardening**
  - Network traffic control based on configuration
  - Port access management
  - Network isolation enforcement
  - Connection tracking for FL ports

- **IO Interceptor**
  - File operation protection
  - Secure memory management
  - Storage encryption handling

### 4. Security Validation

#### Validation Tools
```bash
# Validate system hardening
./validate_security.sh

# Test IO protection
./test_io_security.sh
```

#### Security Checks
- Configuration validation
- Port accessibility checks
- Network isolation verification
- Rate limiting validation
- Network port status
- File permission verification
- Memory protection validation
- System call interception checks
  

### 5. Monitoring and Logging

 #### **IO Interceptor Logs**
    - File operation events
    - Memory allocation tracking
    - Security violations
  
#### **System Hardening Logs**
    - Network access attempts

    - Port scanning detection
    - Traffic anomalies
    - Rate limit violations
    - Connection tracking events
  
## Security Considerations

### Protected Assets
- FL model data
- Training artifacts
- System configuration
- Runtime memory
- Network communications

### Threat Model
- Network-based attacks
- File system attacks
- Memory-based attacks
- Side-channel attacks
