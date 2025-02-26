#ifndef ENCRYPTION_HANDLER_H
#define ENCRYPTION_HANDLER_H

#include <stdbool.h>
#include <stdint.h>
#include <sys/types.h>

// Common definitions and interfaces
#define IV_SIZE 16
#define KEY_SIZE 32
#define MAX_ENCRYPTED_FDS 1024

// Encryption context
typedef struct encryption_ctx {
    int fd;                     // File descriptor
    uint8_t* key;              // Encryption key
    size_t key_len;            // Key length
    void* cipher_ctx;          // Cipher context
} encryption_ctx_t;

// Function declarations
encryption_ctx_t* create_encryption_ctx(int fd, const char* path);
void destroy_encryption_ctx(encryption_ctx_t* ctx);
ssize_t encrypt_data(encryption_ctx_t* ctx, const void* data, size_t len);
ssize_t decrypt_data(encryption_ctx_t* ctx, void* data, size_t len);

// Check if file descriptor is for encrypted file
bool is_encrypted_fd(int fd);

// Track encrypted file descriptors
bool track_encrypted_fd(int fd);
void untrack_encrypted_fd(int fd);

// Handle encrypted file operations
FILE* handle_encrypted_open(const char* path, const char* mode);
int handle_encrypted_open_flags(const char* path, int flags, mode_t mode);
ssize_t handle_encrypted_read(int fd, void* buf, size_t count);
ssize_t handle_encrypted_write(int fd, const void* buf, size_t count);

// Original function pointers from interceptor
extern FILE* (*original_fopen)(const char*, const char*);
extern int (*original_open)(const char*, int, ...);
extern int (*original_close)(int);

// TEE key management
struct tee_keys {
    uint8_t master_key[32];
    uint8_t file_key[32];
    bool initialized;
};

// Platform-specific key management functions
bool initialize_encryption_keys(struct tee_keys* keys);
bool derive_encryption_key(struct tee_keys* keys, const char* path);
void cleanup_encryption_keys(struct tee_keys* keys);

#endif /* ENCRYPTION_HANDLER_H */ 