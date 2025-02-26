#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <CommonCrypto/CommonCrypto.h>
#include <CommonCrypto/CommonRandom.h>
#include "encryption_handler.h"

struct cipher_ctx {
    CCCryptorRef ctx;
    uint8_t iv[IV_SIZE];
};

// Track encrypted file descriptors
static int encrypted_fds[MAX_ENCRYPTED_FDS] = {0};
static int num_encrypted_fds = 0;

// Implement CommonCrypto versions of:
// - is_encrypted_fd()
// - track_encrypted_fd()
// - untrack_encrypted_fd()
// - create_encryption_ctx()
// - destroy_encryption_ctx()
// - encrypt_data()
// - decrypt_data()
// - handle_encrypted_open()
// - handle_encrypted_open_flags()

// Port existing functions to use CommonCrypto
// Including create_encryption_ctx, destroy_encryption_ctx,
// encrypt_data, decrypt_data, etc.

bool is_encrypted_fd(int fd) {
    for (int i = 0; i < num_encrypted_fds; i++) {
        if (encrypted_fds[i] == fd) return true;
    }
    return false;
}

bool track_encrypted_fd(int fd) {
    if (num_encrypted_fds >= MAX_ENCRYPTED_FDS) return false;
    encrypted_fds[num_encrypted_fds++] = fd;
    return true;
}

void untrack_encrypted_fd(int fd) {
    for (int i = 0; i < num_encrypted_fds; i++) {
        if (encrypted_fds[i] == fd) {
            for (int j = i; j < num_encrypted_fds - 1; j++) {
                encrypted_fds[j] = encrypted_fds[j + 1];
            }
            num_encrypted_fds--;
            break;
        }
    }
}

encryption_ctx_t* create_encryption_ctx(int fd, const char* path) {
    encryption_ctx_t* ctx = calloc(1, sizeof(encryption_ctx_t));
    if (!ctx) return NULL;

    ctx->fd = fd;
    ctx->key = malloc(KEY_SIZE);
    ctx->key_len = KEY_SIZE;
    ctx->cipher_ctx = calloc(1, sizeof(struct cipher_ctx));

    if (!ctx->key || !ctx->cipher_ctx) {
        destroy_encryption_ctx(ctx);
        return NULL;
    }

    // Generate random key
    if (CCRandomGenerateBytes(ctx->key, KEY_SIZE) != kCCSuccess) {
        fprintf(stderr, "CommonCrypto key generation failed\n");
        destroy_encryption_ctx(ctx);
        return NULL;
    }

    // Generate random IV
    struct cipher_ctx* cctx = (struct cipher_ctx*)ctx->cipher_ctx;
    if (CCRandomGenerateBytes(cctx->iv, IV_SIZE) != kCCSuccess) {
        fprintf(stderr, "CommonCrypto IV generation failed\n");
        destroy_encryption_ctx(ctx);
        return NULL;
    }

    // Create encryption context
    CCCryptorStatus status = CCCryptorCreate(
        kCCEncrypt,
        kCCAlgorithmAES,
        kCCOptionPKCS7Padding,
        ctx->key,
        ctx->key_len,
        cctx->iv,
        &cctx->ctx
    );

    if (status != kCCSuccess) {
        fprintf(stderr, "CommonCrypto context creation failed\n");
        destroy_encryption_ctx(ctx);
        return NULL;
    }

    return ctx;
}

void destroy_encryption_ctx(encryption_ctx_t* ctx) {
    if (!ctx) return;

    if (ctx->key) {
        memset(ctx->key, 0, ctx->key_len);
        free(ctx->key);
    }

    if (ctx->cipher_ctx) {
        struct cipher_ctx* cctx = (struct cipher_ctx*)ctx->cipher_ctx;
        if (cctx->ctx) CCCryptorRelease(cctx->ctx);
        memset(cctx->iv, 0, IV_SIZE);
        free(ctx->cipher_ctx);
    }

    free(ctx);
}

ssize_t encrypt_data(encryption_ctx_t* ctx, const void* data, size_t len) {
    struct cipher_ctx* cctx = (struct cipher_ctx*)ctx->cipher_ctx;
    
    size_t outlen = len + kCCBlockSizeAES128;
    uint8_t* outbuf = malloc(outlen);
    if (!outbuf) return -1;

    size_t written = 0;
    CCCryptorStatus status = CCCryptorUpdate(
        cctx->ctx,
        data,
        len,
        outbuf,
        outlen,
        &written
    );

    if (status != kCCSuccess) {
        free(outbuf);
        return -1;
    }

    ssize_t result = write(ctx->fd, outbuf, written);
    free(outbuf);
    
    return result;
}

ssize_t decrypt_data(encryption_ctx_t* ctx, void* data, size_t len) {
    struct cipher_ctx* cctx = (struct cipher_ctx*)ctx->cipher_ctx;
    
    size_t outlen = len;
    uint8_t* outbuf = malloc(outlen);
    if (!outbuf) return -1;

    size_t written = 0;
    CCCryptorStatus status = CCCryptorUpdate(
        cctx->ctx,
        data,
        len,
        outbuf,
        outlen,
        &written
    );

    if (status != kCCSuccess) {
        free(outbuf);
        return -1;
    }

    memcpy(data, outbuf, written);
    free(outbuf);
    
    return written;
}

FILE* handle_encrypted_open(const char* path, const char* mode) {
    FILE* fp = original_fopen(path, mode);
    if (!fp) return NULL;
    
    int fd = fileno(fp);
    if (!track_encrypted_fd(fd)) {
        fclose(fp);
        return NULL;
    }
    
    encryption_ctx_t* ctx = create_encryption_ctx(fd, path);
    if (!ctx) {
        untrack_encrypted_fd(fd);
        fclose(fp);
        return NULL;
    }
    
    return fp;
}

int handle_encrypted_open_flags(const char* path, int flags, mode_t mode) {
    int fd = original_open(path, flags, mode);
    if (fd < 0) return -1;
    
    if (!track_encrypted_fd(fd)) {
        close(fd);
        return -1;
    }
    
    encryption_ctx_t* ctx = create_encryption_ctx(fd, path);
    if (!ctx) {
        untrack_encrypted_fd(fd);
        close(fd);
        return -1;
    }
    
    return fd;
}

// TEE key management for Mac
bool initialize_encryption_keys(struct tee_keys* keys) {
    if (keys->initialized) {
        return true;
    }

    // Generate master key using CommonCrypto
    if (CCRandomGenerateBytes(keys->master_key, sizeof(keys->master_key)) != kCCSuccess) {
        syslog(LOG_ERR, "Failed to generate master key in TEE");
        return false;
    }

    keys->initialized = true;
    return true;
}

bool derive_encryption_key(struct tee_keys* keys, const char* path) {
    CCHmacContext ctx;
    CCHmacInit(&ctx, kCCHmacAlgSHA256, keys->master_key, sizeof(keys->master_key));
    CCHmacUpdate(&ctx, path, strlen(path));
    CCHmacFinal(&ctx, keys->file_key);
    return true;
}

void cleanup_encryption_keys(struct tee_keys* keys) {
    if (keys->initialized) {
        memset_s(keys, sizeof(*keys), 0, sizeof(*keys));
    }
}

// CommonCrypto implementation 