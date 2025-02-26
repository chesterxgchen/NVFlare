# IO Interceptor Design

## 1. Architecture Overview

### Components
```
┌──────────────────────────────────────────┐
│              Application                 │
└───────────────────┬──────────────────────┘
                    │
┌───────────────────▼──────────────────────┐
│           IO Interceptor                 │
├──────────────┬──────────────┬────────────┤
│  Path        │ Encryption   │ Memory     │
│  Control     │ Handler      │ Handler    │
└──────────────┴──────────────┴────────────┘
```

### Key Components
1. Path Control: Access control and pattern matching
2. Encryption Handler: File encryption/decryption
3. Memory Handler: Secure memory operations

## 2. Pattern-Based Encryption Design

### Encryption Policy Structure
```c
typedef enum {
    ENCRYPT_READ_WRITE = 1,  // Encrypt both read/write (model files)
    ENCRYPT_WRITE_ONLY = 2   // Encrypt write, discard on read (logs)
} encrypt_policy_t;

// TEE-managed encryption keys
struct tee_keys {
    uint8_t master_key[32];    // Master key for this TEE session
    uint8_t file_key[32];      // Derived key for file encryption
    bool initialized;          // Set when keys are generated
};

typedef struct {
    char pattern[256];
    encrypt_policy_t policy;
} path_pattern_t;
```

### Pattern Matching Flow
```
File Operation Request
       │
       ▼
  Match Pattern ──────┐
       │             │
       ▼             ▼
  Block Write   Match Found
       │             │
       ▼             ▼
 Read Only     Check Policy
                    │
               ┌────┴────┐
               ▼         ▼
          Read-Write  Write-Only
               │         │
               ▼         ▼
          Encrypt/   Encrypt
          Decrypt    Write Only
```

### Key Management
```
TEE Start
    │
    ▼
Generate Master Key
    │
    ▼
Store in TEE Memory ───┐
    │                   │
    ▼                   ▼
Derive File Keys    TEE Restart
    │                   │
    ▼                   └─────┐
Encrypt/Decrypt         New  │
Operations             Keys  ▼
```

## 3. Implementation Details

### Pattern Management
- Maximum 128 patterns
- Glob pattern support (fnmatch)
- All writes must match a pattern
- Read-only for unmatched paths

### Encryption Contexts
```c
struct encryption_ctx {
    int fd;                // File descriptor
    uint8_t* key;         // Key derived from master
    size_t key_len;       // Key length
    void* cipher_ctx;     // Platform-specific context
    bool write_allowed;   // True if pattern matched
};
```

### Platform-Specific Implementation
```c
// Linux (OpenSSL)
struct cipher_ctx {
    EVP_CIPHER_CTX* ctx;
    uint8_t iv[IV_SIZE];
};

// macOS (CommonCrypto)
struct cipher_ctx {
    CCCryptorRef ctx;
    uint8_t iv[IV_SIZE];
};
```

## 4. File Operation Flow

### File Open Operation
```
fopen/open
    │
    ▼
Path Allowed?
    │
    ▼
Get Encryption Policy
    │
    ▼
Create Context if Needed
    │
    ▼
Track File Descriptor
    │
    ▼
Return Handle
```

### Read/Write Operations
```
read/write
    │
    ▼
Check File Descriptor
    │
    ▼
Get Encryption Context
    │
    ▼
Apply Policy
    │
┌───┴────┐
▼        ▼
Encrypt  Decrypt
Write    Read
```

## 5. Security Considerations

### Pattern Security
- Validate patterns before registration
- Prevent path traversal in patterns
- Safe pattern matching implementation
- Pattern update atomicity

### Key Management
- Per-file encryption keys
- Secure key generation
- Key cleanup on close
- IV uniqueness per operation

### Memory Protection
- Secure memory allocation
- Memory wiping after use
- Buffer overflow prevention
- Resource tracking

## 6. Performance Optimizations

### Pattern Matching
- Pattern caching
- Quick rejection paths
- Optimized glob matching
- Pattern ordering by frequency

### Encryption
- Buffer size optimization
- Context reuse when possible
- Minimal copying
- Efficient IV generation

## 7. Integration Points

### Configuration
```conf
# Encryption patterns
ENCRYPT_RW_PATHS="/workspace/models/*.pt,/workspace/checkpoints/*.ckpt"
ENCRYPT_WO_PATHS="/var/log/nvflare/*.log,/workspace/metrics/*.json"
```

### API Integration
```c
// Add encryption pattern
bool add_encryption_pattern(const char* pattern, encrypt_policy_t policy);

// Remove encryption pattern
bool remove_encryption_pattern(const char* pattern);

// Get path encryption policy
encrypt_policy_t get_path_encryption_policy(const char* path);
```

## 8. Monitoring and Debugging

### Logging
- Operation logging
- Pattern match results
- Encryption operations
- Error conditions

### Metrics
- Pattern match counts
- Encryption operations
- Performance timing
- Resource usage 