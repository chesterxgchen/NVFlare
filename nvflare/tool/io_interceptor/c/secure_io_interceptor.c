#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <sys/mman.h>
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>
#include <pthread.h>
#include <openssl/evp.h>
#include <openssl/aes.h>
#include <openssl/rand.h>

// Configuration
#define MAX_FDS 1024
#define MEMORY_THRESHOLD (400 * 1024 * 1024)  // 400MB
#define TEMP_PATH "/tmp/nvflare_secure_XXXXXX"
#define HASH_SUFFIX ".hash"

typedef struct {
    int fd;
    char* path;
    int is_protected;
    size_t size;
    void* buffer;              // Memory buffer for small files
    int temp_fd;              // Temp file for large files
    char* temp_path;
    unsigned char* key;       // Encryption key
    EVP_CIPHER_CTX* cipher;   // Encryption context
} fd_info;

static pthread_mutex_t interceptor_mutex = PTHREAD_MUTEX_INITIALIZER;
static int is_active = 0;
static char* safe_path = NULL;
static fd_info fd_table[MAX_FDS];

// Original function pointers
static int (*original_open)(const char*, int, mode_t) = NULL;
static ssize_t (*original_write)(int, const void*, size_t) = NULL;
static int (*original_close)(int) = NULL;
static void* (*original_mmap)(void*, size_t, int, int, int, off_t) = NULL;

static void init_crypto(fd_info* info) {
    info->key = malloc(32);  // 256-bit key
    RAND_bytes(info->key, 32);
    info->cipher = EVP_CIPHER_CTX_new();
    EVP_EncryptInit_ex(info->cipher, EVP_aes_256_gcm(), NULL, info->key, NULL);
}

static void cleanup_fd_info(fd_info* info) {
    if (info->buffer) {
        // Secure memory cleanup
        memset(info->buffer, 0, info->size);
        free(info->buffer);
    }
    if (info->temp_path) {
        unlink(info->temp_path);
        free(info->temp_path);
    }
    if (info->path) free(info->path);
    if (info->key) {
        memset(info->key, 0, 32);
        free(info->key);
    }
    if (info->cipher) EVP_CIPHER_CTX_free(info->cipher);
    memset(info, 0, sizeof(fd_info));
}

static void write_hash_file(const char* path, const void* data, size_t size) {
    char hash_path[PATH_MAX];
    snprintf(hash_path, PATH_MAX, "%s%s", path, HASH_SUFFIX);
    
    // Create hash
    EVP_MD_CTX* mdctx = EVP_MD_CTX_new();
    unsigned char hash[EVP_MAX_MD_SIZE];
    unsigned int hash_len;
    
    EVP_DigestInit_ex(mdctx, EVP_sha256(), NULL);
    EVP_DigestUpdate(mdctx, data, size);
    EVP_DigestFinal_ex(mdctx, hash, &hash_len);
    
    // Write hash file
    int hash_fd = original_open(hash_path, O_WRONLY | O_CREAT, 0644);
    if (hash_fd >= 0) {
        original_write(hash_fd, hash, hash_len);
        close(hash_fd);
    }
    EVP_MD_CTX_free(mdctx);
}

static fd_info* get_fd_info(int fd) {
    for (int i = 0; i < MAX_FDS; i++) {
        if (fd_table[i].fd == fd) return &fd_table[i];
    }
    return NULL;
}

// Intercept open
int open(const char* pathname, int flags, ...) {
    if (!original_open) {
        original_open = dlsym(RTLD_NEXT, "open");
        original_write = dlsym(RTLD_NEXT, "write");
        original_close = dlsym(RTLD_NEXT, "close");
        original_mmap = dlsym(RTLD_NEXT, "mmap");
    }
    
    mode_t mode = 0;
    if (flags & O_CREAT) {
        va_list args;
        va_start(args, flags);
        mode = va_arg(args, mode_t);
        va_end(args);
    }

    pthread_mutex_lock(&interceptor_mutex);
    
    // Check if write operation to protected path
    if (is_active && (flags & O_WRONLY || flags & O_RDWR)) {
        if (!safe_path || strncmp(pathname, safe_path, strlen(safe_path)) != 0) {
            // Initialize new fd_info
            fd_info* info = NULL;
            for (int i = 0; i < MAX_FDS; i++) {
                if (fd_table[i].fd == 0) {
                    info = &fd_table[i];
                    break;
                }
            }
            
            if (info) {
                info->path = strdup(pathname);
                info->is_protected = 1;
                info->size = 0;
                info->buffer = malloc(8192);  // Initial buffer
                init_crypto(info);
                
                // Create temp file if needed
                char temp_template[] = TEMP_PATH;
                info->temp_fd = mkstemp(temp_template);
                if (info->temp_fd >= 0) {
                    info->temp_path = strdup(temp_template);
                }
                
                info->fd = info->temp_fd;  // Return temp fd
                pthread_mutex_unlock(&interceptor_mutex);
                return info->fd;
            }
        }
    }
    
    int fd = original_open(pathname, flags, mode);
    if (fd >= 0) {
        fd_info* info = NULL;
        for (int i = 0; i < MAX_FDS; i++) {
            if (fd_table[i].fd == 0) {
                info = &fd_table[i];
                info->fd = fd;
                info->path = strdup(pathname);
                info->is_protected = 0;
                break;
            }
        }
    }
    
    pthread_mutex_unlock(&interceptor_mutex);
    return fd;
}

// Intercept write
ssize_t write(int fd, const void* buf, size_t count) {
    pthread_mutex_lock(&interceptor_mutex);
    fd_info* info = get_fd_info(fd);
    
    if (info && info->is_protected) {
        info->size += count;
        
        if (info->size <= MEMORY_THRESHOLD) {
            // Keep in memory
            info->buffer = realloc(info->buffer, info->size);
            memcpy(info->buffer + info->size - count, buf, count);
        } else {
            // Write to temp file with encryption
            unsigned char* encrypted = malloc(count + EVP_MAX_BLOCK_LENGTH);
            int outlen;
            EVP_EncryptUpdate(info->cipher, encrypted, &outlen, buf, count);
            ssize_t written = original_write(info->temp_fd, encrypted, outlen);
            free(encrypted);
            
            if (written < 0) {
                pthread_mutex_unlock(&interceptor_mutex);
                return -1;
            }
        }
        
        pthread_mutex_unlock(&interceptor_mutex);
        return count;
    }
    
    pthread_mutex_unlock(&interceptor_mutex);
    return original_write(fd, buf, count);
}

// Intercept close
int close(int fd) {
    pthread_mutex_lock(&interceptor_mutex);
    fd_info* info = get_fd_info(fd);
    
    if (info && info->is_protected) {
        // Write hash file
        write_hash_file(info->path, 
                       info->buffer ? info->buffer : "", 
                       info->size);
        
        cleanup_fd_info(info);
        pthread_mutex_unlock(&interceptor_mutex);
        return 0;
    }
    
    pthread_mutex_unlock(&interceptor_mutex);
    return original_close(fd);
}

// Intercept mmap
void* mmap(void* addr, size_t length, int prot, int flags, int fd, off_t offset) {
    pthread_mutex_lock(&interceptor_mutex);
    fd_info* info = get_fd_info(fd);
    
    if (info && info->is_protected && (prot & PROT_WRITE)) {
        pthread_mutex_unlock(&interceptor_mutex);
        errno = EACCES;
        return MAP_FAILED;
    }
    
    pthread_mutex_unlock(&interceptor_mutex);
    return original_mmap(addr, length, prot, flags, fd, offset);
}

// Public API
void set_safe_path(const char* path) {
    pthread_mutex_lock(&interceptor_mutex);
    if (safe_path) free(safe_path);
    safe_path = strdup(path);
    pthread_mutex_unlock(&interceptor_mutex);
}

void enable_interceptor() {
    pthread_mutex_lock(&interceptor_mutex);
    is_active = 1;
    pthread_mutex_unlock(&interceptor_mutex);
}

void disable_interceptor() {
    pthread_mutex_lock(&interceptor_mutex);
    is_active = 0;
    // Cleanup all fd_info
    for (int i = 0; i < MAX_FDS; i++) {
        if (fd_table[i].fd != 0) {
            cleanup_fd_info(&fd_table[i]);
        }
    }
    pthread_mutex_unlock(&interceptor_mutex);
} 