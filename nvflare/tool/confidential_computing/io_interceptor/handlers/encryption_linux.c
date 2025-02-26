#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <syslog.h>
#include <fcntl.h>      // For O_RDONLY
#include <unistd.h>     // For read/close
#include <openssl/evp.h>
#include <openssl/err.h>
#include <openssl/rand.h>
#include "./encryption_handler.h"

struct cipher_ctx {
    EVP_CIPHER_CTX* ctx;
    uint8_t iv[IV_SIZE];
};

// Track encrypted file descriptors
static int encrypted_fds[MAX_ENCRYPTED_FDS] = {0};
static int num_encrypted_fds = 0;

// Move all OpenSSL implementations here:
// - is_encrypted_fd()
// - track_encrypted_fd()
// - untrack_encrypted_fd()
// - create_encryption_ctx()
// - destroy_encryption_ctx()
// - encrypt_data()
// - decrypt_data()
// - handle_encrypted_open()
// - handle_encrypted_open_flags()

// OpenSSL implementation 

bool is_encrypted_fd(int fd) {
    for (int i = 0; i < num_encrypted_fds; i++) {
        if (encrypted_fds[i] == fd) {
            return true;
        }
    }
    return false;
}

bool track_encrypted_fd(int fd) {
    if (num_encrypted_fds >= MAX_ENCRYPTED_FDS) {
        return false;
    }
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

// Move OpenSSL-specific functions
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

    if (RAND_bytes(ctx->key, KEY_SIZE) != 1) {
        unsigned long err = ERR_get_error();
        char err_msg[256];
        ERR_error_string_n(err, err_msg, sizeof(err_msg));
        fprintf(stderr, "OpenSSL key generation error: %s\n", err_msg);
        destroy_encryption_ctx(ctx);
        return NULL;
    }

    struct cipher_ctx* cctx = (struct cipher_ctx*)ctx->cipher_ctx;
    if (RAND_bytes(cctx->iv, IV_SIZE) != 1) {
        unsigned long err = ERR_get_error();
        char err_msg[256];
        ERR_error_string_n(err, err_msg, sizeof(err_msg));
        fprintf(stderr, "OpenSSL IV generation error: %s\n", err_msg);
        destroy_encryption_ctx(ctx);
        return NULL;
    }

    cctx->ctx = EVP_CIPHER_CTX_new();
    if (!cctx->ctx) {
        unsigned long err = ERR_get_error();
        char err_msg[256];
        ERR_error_string_n(err, err_msg, sizeof(err_msg));
        fprintf(stderr, "OpenSSL context creation error: %s\n", err_msg);
        destroy_encryption_ctx(ctx);
        return NULL;
    }

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
        if (cctx->ctx) EVP_CIPHER_CTX_free(cctx->ctx);
        OPENSSL_cleanse(cctx->iv, IV_SIZE);
        free(ctx->cipher_ctx);
    }

    free(ctx);
}

ssize_t encrypt_data(encryption_ctx_t* ctx, const void* data, size_t len) {
    struct cipher_ctx* cctx = (struct cipher_ctx*)ctx->cipher_ctx;
    
    if (!EVP_EncryptInit_ex(cctx->ctx, EVP_aes_256_gcm(), NULL, ctx->key, cctx->iv)) {
        return -1;
    }

    int outlen, tmplen;
    uint8_t* outbuf = malloc(len + EVP_MAX_BLOCK_LENGTH);
    if (!outbuf) return -1;

    if (!EVP_EncryptUpdate(cctx->ctx, outbuf, &outlen, data, len)) {
        free(outbuf);
        return -1;
    }

    if (!EVP_EncryptFinal_ex(cctx->ctx, outbuf + outlen, &tmplen)) {
        free(outbuf);
        return -1;
    }

    outlen += tmplen;
    ssize_t written = write(ctx->fd, outbuf, outlen);
    free(outbuf);
    
    return written;
}

ssize_t decrypt_data(encryption_ctx_t* ctx, void* data, size_t len) {
    struct cipher_ctx* cctx = (struct cipher_ctx*)ctx->cipher_ctx;
    
    if (!EVP_DecryptInit_ex(cctx->ctx, EVP_aes_256_gcm(), NULL, ctx->key, cctx->iv)) {
        return -1;
    }

    int outlen, tmplen;
    uint8_t* outbuf = malloc(len);
    if (!outbuf) return -1;

    if (!EVP_DecryptUpdate(cctx->ctx, outbuf, &outlen, data, len)) {
        free(outbuf);
        return -1;
    }

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

// TEE key management for Linux
bool initialize_encryption_keys(struct tee_keys* keys) {
    if (keys->initialized) {
        return true;
    }

    // Try to use hardware-based RNG first
    int urandom_fd = open("/dev/urandom", O_RDONLY);
    if (urandom_fd >= 0) {
        ssize_t bytes_read = read(urandom_fd, keys->master_key, sizeof(keys->master_key));
        close(urandom_fd);
        
        if (bytes_read == sizeof(keys->master_key)) {
            keys->initialized = true;
            return true;
        }
    }

    // Fallback to OpenSSL's RAND which may use different entropy sources
    if (RAND_bytes(keys->master_key, sizeof(keys->master_key)) != 1) {
        syslog(LOG_ERR, "Failed to generate master key in TEE");
        return false;
    }

    keys->initialized = true;
    return true;
}

bool derive_encryption_key(struct tee_keys* keys, const char* path) {
    EVP_MD_CTX* ctx = EVP_MD_CTX_new();
    if (!ctx) return false;

    bool success = false;
    if (EVP_DigestInit_ex(ctx, EVP_sha256(), NULL) &&
        EVP_DigestUpdate(ctx, keys->master_key, sizeof(keys->master_key)) &&
        EVP_DigestUpdate(ctx, path, strlen(path)) &&
        EVP_DigestFinal_ex(ctx, keys->file_key, NULL)) {
        success = true;
    }

    EVP_MD_CTX_free(ctx);
    return success;
}

void cleanup_encryption_keys(struct tee_keys* keys) {
    if (keys->initialized) {
        OPENSSL_cleanse(keys, sizeof(*keys));
    }
} 