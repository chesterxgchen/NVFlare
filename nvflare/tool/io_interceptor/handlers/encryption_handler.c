#include <openssl/evp.h>
#include <openssl/rand.h>
#include <string.h>
#include <stdlib.h>
#include "encryption_handler.h"

#define IV_SIZE 16
#define KEY_SIZE 32

struct cipher_ctx {
    EVP_CIPHER_CTX* ctx;
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

    // Generate random key
    if (RAND_bytes(ctx->key, KEY_SIZE) != 1) {
        destroy_encryption_ctx(ctx);
        return NULL;
    }

    // Generate random IV
    struct cipher_ctx* cctx = (struct cipher_ctx*)ctx->cipher_ctx;
    if (RAND_bytes(cctx->iv, IV_SIZE) != 1) {
        destroy_encryption_ctx(ctx);
        return NULL;
    }

    // Initialize OpenSSL cipher context
    cctx->ctx = EVP_CIPHER_CTX_new();
    if (!cctx->ctx) {
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