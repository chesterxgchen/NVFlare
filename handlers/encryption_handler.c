#include <openssl/evp.h>
#include <openssl/rand.h>
#include "io_interceptor.h"

#define KEY_SIZE 32
#define IV_SIZE 12
#define TAG_SIZE 16

static struct {
    uint8_t checkpoint_key[KEY_SIZE];
    EVP_CIPHER_CTX *ctx;
    bool initialized;
} handler_state = {0};

static io_handler_t encryption_handler = {
    .init = encryption_init,
    .cleanup = encryption_cleanup,
    .handle_write = encryption_write,
    .handle_read = encryption_read
};

static void encryption_init(void) {
    if (!handler_state.initialized) {
        RAND_bytes(handler_state.checkpoint_key, KEY_SIZE);
        handler_state.ctx = EVP_CIPHER_CTX_new();
        handler_state.initialized = true;
    }
}

static void encryption_cleanup(void) {
    if (handler_state.initialized) {
        EVP_CIPHER_CTX_free(handler_state.ctx);
        OPENSSL_cleanse(handler_state.checkpoint_key, KEY_SIZE);
        handler_state.initialized = false;
    }
}

static ssize_t encryption_write(int fd, const void* buf, size_t count) {
    uint8_t iv[IV_SIZE];
    uint8_t tag[TAG_SIZE];
    uint8_t *ciphertext = malloc(count + TAG_SIZE);
    
    RAND_bytes(iv, IV_SIZE);
    
    EVP_EncryptInit_ex(handler_state.ctx, EVP_aes_256_gcm(), NULL, 
                       handler_state.checkpoint_key, iv);
    
    int len;
    EVP_EncryptUpdate(handler_state.ctx, ciphertext, &len, buf, count);
    
    int final_len;
    EVP_EncryptFinal_ex(handler_state.ctx, ciphertext + len, &final_len);
    
    EVP_CIPHER_CTX_ctrl(handler_state.ctx, EVP_CTRL_GCM_GET_TAG, 16, tag);
    
    // Write IV || Ciphertext || Tag
    write(fd, iv, IV_SIZE);
    write(fd, ciphertext, len + final_len);
    write(fd, tag, TAG_SIZE);
    
    free(ciphertext);
    return count;
}

static ssize_t encryption_read(int fd, void* buf, size_t count) {
    uint8_t iv[IV_SIZE];
    uint8_t tag[TAG_SIZE];
    
    // Read IV
    if (read(fd, iv, IV_SIZE) != IV_SIZE) {
        return -1;
    }
    
    // Read encrypted data
    uint8_t *ciphertext = malloc(count);
    ssize_t read_size = read(fd, ciphertext, count);
    if (read_size < 0) {
        free(ciphertext);
        return -1;
    }
    
    // Read tag
    if (read(fd, tag, TAG_SIZE) != TAG_SIZE) {
        free(ciphertext);
        return -1;
    }
    
    // Decrypt
    EVP_DecryptInit_ex(handler_state.ctx, EVP_aes_256_gcm(), NULL,
                       handler_state.checkpoint_key, iv);
    
    int len;
    EVP_DecryptUpdate(handler_state.ctx, buf, &len, ciphertext, read_size);
    
    EVP_CIPHER_CTX_ctrl(handler_state.ctx, EVP_CTRL_GCM_SET_TAG, TAG_SIZE, tag);
    
    int final_len;
    if (EVP_DecryptFinal_ex(handler_state.ctx, (uint8_t*)buf + len, &final_len) <= 0) {
        free(ciphertext);
        return -1;
    }
    
    free(ciphertext);
    return len + final_len;
} 