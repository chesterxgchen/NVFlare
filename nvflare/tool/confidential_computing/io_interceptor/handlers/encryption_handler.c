#include <stdio.h>
#ifdef __APPLE__
#include <CommonCrypto/CommonCrypto.h>
#else
#include <openssl/evp.h>
#include <openssl/err.h>
#include <openssl/rand.h>
#endif
#include <string.h>
#include <stdlib.h>
#include <stdbool.h>
#include <sys/types.h>
#include "encryption_handler.h"

#define IV_SIZE 16
#define KEY_SIZE 32

// Track encrypted file descriptors
#define MAX_ENCRYPTED_FDS 1024
static int encrypted_fds[MAX_ENCRYPTED_FDS] = {0};
static int num_encrypted_fds = 0;

#ifndef EVP_MAX_BLOCK_LENGTH
#define EVP_MAX_BLOCK_LENGTH 32
#endif

bool is_encrypted_fd(int fd) {
    // Check if fd is in our tracked list
    for (int i = 0; i < num_encrypted_fds; i++) {
        if (encrypted_fds[i] == fd) {
            return true;
        }
    }
    return false;
}

// Add fd to tracking when opening encrypted file
bool track_encrypted_fd(int fd) {
    if (num_encrypted_fds >= MAX_ENCRYPTED_FDS) {
        return false;
    }
    encrypted_fds[num_encrypted_fds++] = fd;
    return true;
}

// Remove fd when closing encrypted file
void untrack_encrypted_fd(int fd) {
    for (int i = 0; i < num_encrypted_fds; i++) {
        if (encrypted_fds[i] == fd) {
            // Remove by shifting remaining elements
            for (int j = i; j < num_encrypted_fds - 1; j++) {
                encrypted_fds[j] = encrypted_fds[j + 1];
            }
            num_encrypted_fds--;
            break;
        }
    }
}

struct cipher_ctx {
#ifdef __APPLE__
    CCCryptorRef ctx;
#else
    EVP_CIPHER_CTX* ctx;
#endif
    uint8_t iv[IV_SIZE];
};

encryption_ctx_t* create_encryption_ctx(int fd, const char* path) {
    encryption_ctx_t* ctx = calloc(1, sizeof(encryption_ctx_t));
    if (!ctx) return NULL;

    // Initialize context
    ctx->fd = fd;
    ctx->key = malloc(KEY_SIZE);
    ctx->key_len = KEY_SIZE;
    ctx->cipher_ctx = calloc(1, sizeof(struct cipher_ctx));

    if (!ctx->key || !ctx->cipher_ctx) {
        destroy_encryption_ctx(ctx);
        return NULL;
    }

#ifdef __APPLE__
    // Generate random key using CommonCrypto
    if (CCRandomGenerateBytes(ctx->key, KEY_SIZE) != kCCSuccess) {
        destroy_encryption_ctx(ctx);
        return NULL;
    }

    // Generate random IV
    struct cipher_ctx* cctx = (struct cipher_ctx*)ctx->cipher_ctx;
    if (CCRandomGenerateBytes(cctx->iv, IV_SIZE) != kCCSuccess) {
        destroy_encryption_ctx(ctx);
        return NULL;
    }

    // Create CommonCrypto context
    CCCryptorStatus status = CCCryptorCreate(
        kCCEncrypt,             // Operation
        kCCAlgorithmAES,        // Algorithm
        kCCOptionPKCS7Padding,  // Options
        ctx->key,               // Key
        KEY_SIZE,               // Key length
        cctx->iv,               // IV
        &cctx->ctx              // Context
    );
    if (status != kCCSuccess) {
        destroy_encryption_ctx(ctx);
        return NULL;
    }
#else
    // Generate random key using OpenSSL
    if (RAND_bytes(ctx->key, KEY_SIZE) != 1) {
        unsigned long err = ERR_get_error();
        char err_msg[256];
        ERR_error_string_n(err, err_msg, sizeof(err_msg));
        fprintf(stderr, "OpenSSL key generation error: %s\n", err_msg);
        destroy_encryption_ctx(ctx);
        return NULL;
    }

    // Generate random IV
    struct cipher_ctx* cctx = (struct cipher_ctx*)ctx->cipher_ctx;
    if (RAND_bytes(cctx->iv, IV_SIZE) != 1) {
        unsigned long err = ERR_get_error();
        char err_msg[256];
        ERR_error_string_n(err, err_msg, sizeof(err_msg));
        fprintf(stderr, "OpenSSL IV generation error: %s\n", err_msg);
        destroy_encryption_ctx(ctx);
        return NULL;
    }

    // Initialize OpenSSL cipher context
    cctx->ctx = EVP_CIPHER_CTX_new();
    if (!cctx->ctx) {
        unsigned long err = ERR_get_error();
        char err_msg[256];
        ERR_error_string_n(err, err_msg, sizeof(err_msg));
        fprintf(stderr, "OpenSSL context creation error: %s\n", err_msg);
        destroy_encryption_ctx(ctx);
        return NULL;
    }
#endif

    return ctx;
}

void destroy_encryption_ctx(encryption_ctx_t* ctx) {
    if (!ctx) return;

    if (ctx->key) {
        OPENSSL_cleanse(ctx->key, ctx->key_len);
        free(ctx->key);
    }

    if (ctx->cipher_ctx) {
        struct cipher_ctx* cctx = (struct cipher_ctx*)ctx->cipher_ctx;
        if (cctx->ctx) {
            EVP_CIPHER_CTX_free(cctx->ctx);
        }
        OPENSSL_cleanse(cctx->iv, IV_SIZE);
        free(ctx->cipher_ctx);
    }

    free(ctx);
}

ssize_t encrypt_data(encryption_ctx_t* ctx, const void* data, size_t len) {
    struct cipher_ctx* cctx = (struct cipher_ctx*)ctx->cipher_ctx;
    
    // Initialize encryption
    if (!EVP_EncryptInit_ex(cctx->ctx, EVP_aes_256_gcm(), NULL, ctx->key, cctx->iv)) {
        return -1;
    }

    // Allocate output buffer
    int outlen, tmplen;
    uint8_t* outbuf = malloc(len + EVP_MAX_BLOCK_LENGTH);
    if (!outbuf) return -1;

    // Encrypt data
    if (!EVP_EncryptUpdate(cctx->ctx, outbuf, &outlen, data, len)) {
        free(outbuf);
        return -1;
    }

    // Finalize encryption
    if (!EVP_EncryptFinal_ex(cctx->ctx, outbuf + outlen, &tmplen)) {
        free(outbuf);
        return -1;
    }

    outlen += tmplen;
    
    // Write encrypted data
    ssize_t written = write(ctx->fd, outbuf, outlen);
    free(outbuf);
    
    return written;
}

ssize_t decrypt_data(encryption_ctx_t* ctx, void* data, size_t len) {
    struct cipher_ctx* cctx = (struct cipher_ctx*)ctx->cipher_ctx;
    
    // Initialize decryption
    if (!EVP_DecryptInit_ex(cctx->ctx, EVP_aes_256_gcm(), NULL, ctx->key, cctx->iv)) {
        return -1;
    }

    // Allocate output buffer
    int outlen, tmplen;
    uint8_t* outbuf = malloc(len);
    if (!outbuf) return -1;

    // Decrypt data
    if (!EVP_DecryptUpdate(cctx->ctx, outbuf, &outlen, data, len)) {
        free(outbuf);
        return -1;
    }

    // Finalize decryption
    if (!EVP_DecryptFinal_ex(cctx->ctx, outbuf + outlen, &tmplen)) {
        free(outbuf);
        return -1;
    }

    outlen += tmplen;
    memcpy(data, outbuf, outlen);
    free(outbuf);
    
    return outlen;
}

FILE* handle_encrypted_open(const char* path, const char* mode) {
    // Open file using original function
    FILE* fp = original_fopen(path, mode);
    if (!fp) {
        return NULL;
    }
    
    // Get file descriptor and track it
    int fd = fileno(fp);
    if (!track_encrypted_fd(fd)) {
        fclose(fp);
        return NULL;
    }
    
    // Create encryption context
    encryption_ctx_t* ctx = create_encryption_ctx(fd, path);
    if (!ctx) {
        untrack_encrypted_fd(fd);
        fclose(fp);
        return NULL;
    }
    
    return fp;
}

int handle_encrypted_open_flags(const char* path, int flags, mode_t mode) {
    // Open file using original function
    int fd = original_open(path, flags, mode);
    if (fd < 0) {
        return -1;
    }
    
    // Track encrypted fd
    if (!track_encrypted_fd(fd)) {
        close(fd);
        return -1;
    }
    
    // Create encryption context
    encryption_ctx_t* ctx = create_encryption_ctx(fd, path);
    if (!ctx) {
        untrack_encrypted_fd(fd);
        close(fd);
        return -1;
    }
    
    return fd;
} 