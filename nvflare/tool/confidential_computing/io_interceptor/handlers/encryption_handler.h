#ifndef ENCRYPTION_HANDLER_H
#define ENCRYPTION_HANDLER_H

#include <stdbool.h>
#include <stdint.h>
#include <sys/types.h>

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

#endif /* ENCRYPTION_HANDLER_H */ 