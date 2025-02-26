#ifndef IO_INTERCEPTOR_H
#define IO_INTERCEPTOR_H

#include <stdbool.h>
#include <stdio.h>

#define MAX_PATHS 1024

// Operation types
typedef enum {
    OP_READ,
    OP_WRITE,
    OP_DELETE,
    OP_MODIFY
} operation_type_t;

// Path types
typedef enum {
    PATH_WHITELIST,
    PATH_SYSTEM,
    PATH_TMPFS,
    PATH_BLOCKED
} path_type_t;

// Encryption policy types
typedef enum {
    ENCRYPT_NONE = 0,
    ENCRYPT_READ_WRITE = 1,  // Both encryption and decryption
    ENCRYPT_WRITE_ONLY = 2   // Only encrypt writes
} encrypt_policy_t;

// Path pattern configuration
typedef struct {
    char pattern[256];
    encrypt_policy_t policy;
} path_pattern_t;

// Function declarations
bool register_whitelist_path(const char* path);
bool register_system_path(const char* path);
bool register_tmpfs_path(const char* path);

// Internal functions (implemented in interceptor.c)
bool is_path_allowed(const char* path, int operation);
bool handle_system_path(const char* path, int operation);
bool handle_tmpfs_path(const char* path, int operation);
bool is_encrypted_path(const char* path);
bool is_encrypted_fd(int fd);
FILE* handle_encrypted_open(const char* path, const char* mode);
int handle_encrypted_open_flags(const char* path, int flags, mode_t mode);
ssize_t handle_encrypted_write(int fd, const void* buf, size_t count);
ssize_t handle_encrypted_read(int fd, void* buf, size_t count);
int get_operation_type(const char* mode);
int get_operation_type_flags(int flags);

// Configure encryption patterns
bool add_encryption_pattern(const char* pattern, encrypt_policy_t policy);
bool remove_encryption_pattern(const char* pattern);
encrypt_policy_t get_path_encryption_policy(const char* path);

#endif /* IO_INTERCEPTOR_H */ 