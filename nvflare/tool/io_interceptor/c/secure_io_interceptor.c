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
#include <time.h>
#include <signal.h>
#include <fnmatch.h>
#include <libgen.h>
#include <glob.h>
#include "secure_io_interceptor.h"

// Configuration
#define MAX_FDS 1024
#define MEMORY_THRESHOLD (400 * 1024 * 1024)  // 400MB
#define TEMP_PATH "/tmp/nvflare_secure_XXXXXX"
#define HASH_SUFFIX ".hash"
#define ENCRYPTED_FILE_SUFFIX ".enc"
#define SECURE_WIPE_PASSES 3  // Number of passes for secure deletion
#define BACKUP_SUFFIX ".bak"

#define ENCRYPTION_KEY_SIZE 32
#define IV_SIZE 16
#define BUFFER_SIZE 4096
#define PBKDF2_ITERATIONS 100000  // High iteration count for security
#define SALT_SIZE 32

// Add to existing defines
#define MIN_ENCRYPTION_LAYERS 3
#define MAX_ENCRYPTION_LAYERS 10
#define DEFAULT_MIN_PADDING 1024
#define DEFAULT_MAX_PADDING (1024 * 1024)

// Whitelist storage
static whitelist_path_t whitelist_paths[MAX_WHITELIST_PATHS];
static int num_whitelist_paths = 0;
static pthread_mutex_t whitelist_mutex = PTHREAD_MUTEX_INITIALIZER;

// File descriptor info structure
typedef struct {
    int fd;                  // File descriptor
    char* path;             // File path
    int is_protected;       // Whether this file needs protection
    size_t size;            // Current file size
    void* buffer;           // Memory buffer for small files
    int temp_fd;           // Temp file for large files
    char* temp_path;        // Path to temp file
    unsigned char* key;     // Encryption key
    EVP_CIPHER_CTX* cipher; // Encryption context
} fd_info;

static pthread_mutex_t interceptor_mutex = PTHREAD_MUTEX_INITIALIZER;
static int is_active = 0;
static char* safe_path = NULL;
static fd_info fd_table[MAX_FDS];

// Function pointer types
typedef int (*open_fn_t)(const char*, int, mode_t);
typedef ssize_t (*write_fn_t)(int, const void*, size_t);
typedef int (*close_fn_t)(int);
typedef void* (*mmap_fn_t)(void*, size_t, int, int, int, off_t);

// Store function pointers
static struct {
    open_fn_t open;
    write_fn_t write;
    close_fn_t close;
    mmap_fn_t mmap;
} original_functions = {0};

// Function pointers for interception
static open_fn_t current_open = NULL;
static write_fn_t current_write = NULL;
static close_fn_t current_close = NULL;
static mmap_fn_t current_mmap = NULL;

// Structure for file metadata
typedef struct {
    size_t original_size;
    unsigned char iv[IV_SIZE];
    unsigned char salt[SALT_SIZE];
    // Add checksum/signature fields here
} FileHeader;

// Global state for interrupt handling
static volatile sig_atomic_t interrupt_received = 0;

// Signal handler
static void handle_interrupt(int sig) {
    interrupt_received = 1;
}

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
    int hash_fd = original_functions.open(hash_path, O_WRONLY | O_CREAT, 0644);
    if (hash_fd >= 0) {
        original_functions.write(hash_fd, hash, hash_len);
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
    if (!original_functions.open) {
        original_functions.open = dlsym(RTLD_NEXT, "open");
        original_functions.write = dlsym(RTLD_NEXT, "write");
        original_functions.close = dlsym(RTLD_NEXT, "close");
        original_functions.mmap = dlsym(RTLD_NEXT, "mmap");
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
    
    int fd = original_functions.open(pathname, flags, mode);
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
    init_interceptor();

    // Find file info
    file_info* info = NULL;
    for (int i = 0; i < MAX_FILES; i++) {
        if (files[i].fd == fd) {
            info = &files[i];
            break;
        }
    }

    if (info && info->needs_protection) {
        switch (protect_mode) {
            case PROTECT_MODE_IGNORE:
                // Log warning for ignored path
                log_warning("Write ignored for non-whitelisted path: %s (size: %zu bytes)", 
                          info->path, count);
                return count;  // Pretend we wrote the data
                
            case PROTECT_MODE_ENCRYPT:
                if (is_path_allowed(info->path)) {
                    // Use checkpoint key for whitelisted paths
                    log_warning("Encrypting write with checkpoint key: %s (size: %zu bytes)", 
                              info->path, count);
                    return encrypt_with_checkpoint_key(fd, buf, count);
                } else {
                    // Use throwaway key for non-whitelisted paths
                    log_warning("Encrypting write with throwaway key: %s (size: %zu bytes)", 
                              info->path, count);
                    return encrypt_and_destroy(fd, buf, count);
                }
        }
    }

    return original_functions.write(fd, buf, count);
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
    return original_functions.close(fd);
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
    return original_functions.mmap(addr, length, prot, flags, fd, offset);
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

static int encrypt_data(const unsigned char* input, size_t input_len,
                       unsigned char* output, size_t* output_len,
                       const unsigned char* iv, const unsigned char* key) {
    EVP_CIPHER_CTX* ctx = EVP_CIPHER_CTX_new();
    if (!ctx) return -1;

    int len;
    *output_len = 0;

    if (EVP_EncryptInit_ex(ctx, EVP_aes_256_gcm(), NULL, key, iv) != 1 ||
        EVP_EncryptUpdate(ctx, output, &len, input, input_len) != 1) {
        EVP_CIPHER_CTX_free(ctx);
        return -1;
    }
    
    *output_len = len;

    if (EVP_EncryptFinal_ex(ctx, output + len, &len) != 1) {
        EVP_CIPHER_CTX_free(ctx);
        return -1;
    }

    *output_len += len;
    EVP_CIPHER_CTX_free(ctx);
    return 0;
}

static int decrypt_data(const unsigned char* input, size_t input_len,
                       unsigned char* output, size_t* output_len,
                       const unsigned char* iv, const unsigned char* key) {
    EVP_CIPHER_CTX* ctx = EVP_CIPHER_CTX_new();
    if (!ctx) return -1;

    int len;
    *output_len = 0;

    if (EVP_DecryptInit_ex(ctx, EVP_aes_256_gcm(), NULL, key, iv) != 1 ||
        EVP_DecryptUpdate(ctx, output, &len, input, input_len) != 1) {
        EVP_CIPHER_CTX_free(ctx);
        return -1;
    }

    *output_len = len;

    if (EVP_DecryptFinal_ex(ctx, output + len, &len) != 1) {
        EVP_CIPHER_CTX_free(ctx);
        return -1;
    }

    *output_len += len;
    EVP_CIPHER_CTX_free(ctx);
    return 0;
}

// Backup management functions
static int create_backup(const char* filepath) {
    char backup_path[PATH_MAX];
    snprintf(backup_path, PATH_MAX, "%s%s", filepath, BACKUP_SUFFIX);
    
    // Copy original file to backup
    FILE *src = fopen(filepath, "rb");
    if (!src) return SECURE_IO_SUCCESS; // No original file is OK
    
    FILE *dst = fopen(backup_path, "wb");
    if (!dst) {
        fclose(src);
        return SECURE_IO_ERROR_BACKUP;
    }
    
    char buffer[8192];
    size_t bytes;
    while ((bytes = fread(buffer, 1, sizeof(buffer), src)) > 0) {
        if (fwrite(buffer, 1, bytes, dst) != bytes) {
            fclose(src);
            fclose(dst);
            return SECURE_IO_ERROR_BACKUP;
        }
    }
    
    fclose(src);
    fclose(dst);
    return SECURE_IO_SUCCESS;
}

// Modify secure_save to handle interrupts and backups
int secure_save(const void* data, size_t size, const char* filepath) {
    if (!data || !filepath || size == 0) {
        return SECURE_IO_ERROR_PARAM;
    }
    
    // Setup interrupt handler
    struct sigaction sa, old_sa;
    sa.sa_handler = handle_interrupt;
    sigemptyset(&sa.sa_mask);
    sa.sa_flags = 0;
    sigaction(SIGINT, &sa, &old_sa);
    
    int ret = SECURE_IO_SUCCESS;
    FILE* fp = NULL;
    unsigned char* encrypted_data = NULL;
    char* enc_filepath = NULL;
    
    // Create backup first
    ret = create_backup(filepath);
    if (ret != SECURE_IO_SUCCESS) {
        goto cleanup;
    }
    
    // Rest of the encryption process...
    // ... (existing encryption code) ...
    
    if (interrupt_received) {
        ret = SECURE_IO_ERROR_INTERRUPT;
        goto cleanup;
    }
    
cleanup:
    if (ret != SECURE_IO_SUCCESS) {
        // Restore from backup on failure
        restore_from_backup(filepath);
    }
    
    // Cleanup
    if (encrypted_data) {
        secure_wipe_memory(encrypted_data, size + EVP_MAX_BLOCK_LENGTH);
        free(encrypted_data);
    }
    if (enc_filepath) free(enc_filepath);
    if (fp) fclose(fp);
    
    // Restore original signal handler
    sigaction(SIGINT, &old_sa, NULL);
    
    return ret;
}

// Restore function
int restore_from_backup(const char* filepath) {
    char backup_path[PATH_MAX];
    snprintf(backup_path, PATH_MAX, "%s%s", filepath, BACKUP_SUFFIX);
    
    // Check if backup exists
    struct stat st;
    if (stat(backup_path, &st) != 0) {
        return SECURE_IO_ERROR_BACKUP;
    }
    
    // Remove current file if it exists
    unlink(filepath);
    
    // Rename backup to original
    if (rename(backup_path, filepath) != 0) {
        return SECURE_IO_ERROR_RESTORE;
    }
    
    return SECURE_IO_SUCCESS;
}

// Cleanup function
void cleanup_backups(void) {
    char cmd[PATH_MAX + 50];
    snprintf(cmd, sizeof(cmd), "find %s -name '*%s' -delete", 
             safe_path ? safe_path : ".", BACKUP_SUFFIX);
    system(cmd);
}

int secure_load(const char* filepath, void* buffer, size_t buffer_size, size_t* data_size) {
    // Try with .enc extension first
    char* enc_filepath = malloc(strlen(filepath) + strlen(ENCRYPTED_FILE_SUFFIX) + 1);
    sprintf(enc_filepath, "%s%s", filepath, ENCRYPTED_FILE_SUFFIX);
    
    FILE* fp = fopen(enc_filepath, "rb");
    if (!fp) {
        // Try without extension as fallback
        fp = fopen(filepath, "rb");
        if (!fp) {
            free(enc_filepath);
            return SECURE_IO_ERROR_FILE;
        }
    }
    
    free(enc_filepath);

    // Read header
    FileHeader header;
    if (fread(&header, sizeof(header), 1, fp) != 1) {
        fclose(fp);
        return -4;
    }

    // Check buffer size
    if (buffer_size < header.original_size) {
        fclose(fp);
        return -5;
    }

    // Read encrypted data
    unsigned char* encrypted_data = malloc(header.original_size + EVP_MAX_BLOCK_LENGTH);
    if (!encrypted_data) {
        fclose(fp);
        return -6;
    }

    size_t encrypted_size = fread(encrypted_data, 1, header.original_size + EVP_MAX_BLOCK_LENGTH, fp);
    fclose(fp);

    // Decrypt data
    if (decrypt_data(encrypted_data, encrypted_size, buffer, data_size, header.iv, header.salt) != 0) {
        free(encrypted_data);
        return -7;
    }

    free(encrypted_data);
    return 0;
}

// Global mutex for thread safety
static pthread_mutex_t global_mutex = PTHREAD_MUTEX_INITIALIZER;
static pthread_rwlock_t fd_table_lock = PTHREAD_RWLOCK_INITIALIZER;
static int is_initialized = 0;

// Add to existing global variables
static struct {
    unsigned char* checkpoint_key;  // Key for whitelisted paths
    size_t key_size;
    int is_initialized;
    pthread_mutex_t mutex;
} runtime_key_mgr = {
    .checkpoint_key = NULL,
    .key_size = 0,
    .is_initialized = 0,
    .mutex = PTHREAD_MUTEX_INITIALIZER
};

// Modify existing init_secure_io
int init_secure_io(void) {
    int ret = SECURE_IO_SUCCESS;
    
    if (pthread_mutex_lock(&global_mutex) != 0) {
        return SECURE_IO_ERROR_LOCK;
    }
    
    if (!is_initialized) {
        // Initialize OpenSSL
        OpenSSL_add_all_algorithms();
        
        // Initialize function pointers
        original_functions.open = dlsym(RTLD_NEXT, "open");
        original_functions.write = dlsym(RTLD_NEXT, "write");
        original_functions.close = dlsym(RTLD_NEXT, "close");
        original_functions.mmap = dlsym(RTLD_NEXT, "mmap");
        
        if (!original_functions.open || !original_functions.write || !original_functions.close || !original_functions.mmap) {
            ret = SECURE_IO_ERROR_INIT;
            goto cleanup;
        }
        
        // Initialize fd_table
        memset(fd_table, 0, sizeof(fd_table));
        is_initialized = 1;
        
        // Add checkpoint key initialization
        runtime_key_mgr.checkpoint_key = malloc(ENCRYPTION_KEY_SIZE);
        if (RAND_bytes(runtime_key_mgr.checkpoint_key, ENCRYPTION_KEY_SIZE) != 1) {
            ret = SECURE_IO_ERROR_KEY;
            goto cleanup;
        }
        runtime_key_mgr.key_size = ENCRYPTION_KEY_SIZE;
        runtime_key_mgr.is_initialized = 1;
    }
    
cleanup:
    pthread_mutex_unlock(&global_mutex);
    return ret;
}

// Modify existing cleanup_secure_io
void cleanup_secure_io(void) {
    pthread_mutex_lock(&global_mutex);
    
    if (is_initialized) {
        disable_interceptor();
        EVP_cleanup();
        is_initialized = 0;
        
        // Add checkpoint key cleanup
        if (runtime_key_mgr.checkpoint_key) {
            secure_wipe_memory(runtime_key_mgr.checkpoint_key, 
                             runtime_key_mgr.key_size);
            free(runtime_key_mgr.checkpoint_key);
            runtime_key_mgr.checkpoint_key = NULL;
        }
        runtime_key_mgr.is_initialized = 0;
    }
    
    pthread_mutex_unlock(&global_mutex);
}

static fd_info* get_fd_info(int fd) {
    fd_info* info = NULL;
    
    if (pthread_rwlock_rdlock(&fd_table_lock) != 0) {
        return NULL;
    }
    
    for (int i = 0; i < MAX_FDS; i++) {
        if (fd_table[i].fd == fd) {
            info = &fd_table[i];
            break;
        }
    }
    
    pthread_rwlock_unlock(&fd_table_lock);
    return info;
}

// Add secure deletion function
static void secure_wipe_file(const char* filepath) {
    struct stat st;
    if (stat(filepath, &st) != 0) return;
    
    int fd = open(filepath, O_WRONLY);
    if (fd < 0) return;
    
    unsigned char* random_data = malloc(st.st_size);
    
    // Multiple overwrite passes
    for (int pass = 0; pass < SECURE_WIPE_PASSES; pass++) {
        // Different patterns each pass
        switch (pass) {
            case 0: memset(random_data, 0x00, st.st_size); break;  // zeros
            case 1: memset(random_data, 0xFF, st.st_size); break;  // ones
            case 2: RAND_bytes(random_data, st.st_size); break;    // random
        }
        
        if (write(fd, random_data, st.st_size) != st.st_size) {
            break;
        }
        fsync(fd);  // Ensure data is written to disk
    }
    
    free(random_data);
    close(fd);
    unlink(filepath);  // Finally delete the file
}

// Add secure memory wiping function
static void secure_wipe_memory(void* ptr, size_t size) {
    volatile unsigned char* p = (volatile unsigned char*)ptr;
    for (size_t i = 0; i < size; i++) {
        p[i] = 0;
    }
    // Additional passes with different patterns
    for (size_t i = 0; i < size; i++) {
        p[i] = 0xFF;
    }
    for (size_t i = 0; i < size; i++) {
        p[i] = 0x55;
    }
    for (size_t i = 0; i < size; i++) {
        p[i] = 0xAA;
    }
    // Final pass with zeros
    for (size_t i = 0; i < size; i++) {
        p[i] = 0;
    }
}

// Configuration
static protect_mode_t protect_mode = PROTECT_MODE_IGNORE;  // Default to ignore mode
static FILE* log_file = NULL;

// File tracking
typedef struct {
    int fd;
    char* path;
    int needs_protection;
} file_info;

static file_info files[MAX_FILES];

static void log_warning(const char* format, ...) {
    if (!log_file) return;
    
    time_t now;
    time(&now);
    char* time_str = ctime(&now);
    time_str[strlen(time_str)-1] = '\0';  // Remove newline
    
    fprintf(log_file, "[%s] WARNING: ", time_str);
    
    va_list args;
    va_start(args, format);
    vfprintf(log_file, format, args);
    va_end(args);
    
    fprintf(log_file, "\n");
    fflush(log_file);
}

static void init_interceptor(void) {
    if (!original_functions.open) {
        original_functions.open = dlsym(RTLD_NEXT, "open");
        original_functions.write = dlsym(RTLD_NEXT, "write");
        original_functions.close = dlsym(RTLD_NEXT, "close");
    }
}

// Enhanced path checking
static int is_path_allowed(const char* path) {
    char resolved_path[PATH_MAX];
    if (!realpath(path, resolved_path)) {
        return 0;  // Can't resolve path, consider it unsafe
    }

    pthread_mutex_lock(&whitelist_mutex);
    
    for (int i = 0; i < num_whitelist_paths; i++) {
        switch (whitelist_paths[i].type) {
            case PATH_TYPE_EXACT:
                // Exact path match
                if (strcmp(resolved_path, whitelist_paths[i].path) == 0) {
                    pthread_mutex_unlock(&whitelist_mutex);
                    return 1;
                }
                break;

            case PATH_TYPE_PREFIX:
                // Path prefix match
                if (strncmp(resolved_path, whitelist_paths[i].path, 
                           strlen(whitelist_paths[i].path)) == 0) {
                    pthread_mutex_unlock(&whitelist_mutex);
                    return 1;
                }
                break;

            case PATH_TYPE_PATTERN:
                // Pattern match using glob
                if (fnmatch(whitelist_paths[i].path, resolved_path, FNM_PATHNAME) == 0) {
                    pthread_mutex_unlock(&whitelist_mutex);
                    return 1;
                }
                break;
        }
    }

    pthread_mutex_unlock(&whitelist_mutex);
    return 0;
}

// Add path to whitelist
void add_whitelist_path(const char* path, path_match_type_t type) {
    if (!path) return;

    pthread_mutex_lock(&whitelist_mutex);
    
    if (num_whitelist_paths < MAX_WHITELIST_PATHS) {
        char resolved[PATH_MAX];
        
        // For exact and prefix matches, resolve the path
        if (type != PATH_TYPE_PATTERN && realpath(path, resolved)) {
            strncpy(whitelist_paths[num_whitelist_paths].path, resolved, MAX_PATH_LENGTH - 1);
        } else {
            strncpy(whitelist_paths[num_whitelist_paths].path, path, MAX_PATH_LENGTH - 1);
        }
        
        whitelist_paths[num_whitelist_paths].type = type;
        num_whitelist_paths++;
    }
    
    pthread_mutex_unlock(&whitelist_mutex);
}

void clear_whitelist_paths(void) {
    pthread_mutex_lock(&whitelist_mutex);
    num_whitelist_paths = 0;
    pthread_mutex_unlock(&whitelist_mutex);
}

// Configuration
static protect_config_t protect_config = {
    .num_encryption_layers = 3,
    .min_padding_size = DEFAULT_MIN_PADDING,
    .max_padding_size = DEFAULT_MAX_PADDING,
    .add_random_noise = 1
};

// Enhanced encryption that makes data unrecoverable
static ssize_t encrypt_and_write(int fd, const void* buf, size_t count) {
    ssize_t result = -1;
    unsigned char* encrypted = NULL;
    size_t encrypted_size = count;
    
    // Add random padding
    size_t padding_size = protect_config.min_padding_size + 
        (rand() % (protect_config.max_padding_size - protect_config.min_padding_size));
    encrypted_size += padding_size;
    
    encrypted = malloc(encrypted_size);
    if (!encrypted) goto cleanup;
    
    // Copy original data
    memcpy(encrypted, buf, count);
    
    // Add random padding
    RAND_bytes(encrypted + count, padding_size);
    
    // Multiple encryption layers with different random keys
    for (size_t layer = 0; layer < protect_config.num_encryption_layers; layer++) {
        unsigned char* key = malloc(32);
        unsigned char* iv = malloc(16);
        
        // Generate random key and IV
        RAND_bytes(key, 32);
        RAND_bytes(iv, 16);
        
        // Encrypt this layer
        EVP_CIPHER_CTX* ctx = EVP_CIPHER_CTX_new();
        EVP_EncryptInit_ex(ctx, EVP_aes_256_gcm(), NULL, key, iv);
        
        int outlen;
        unsigned char* temp = malloc(encrypted_size + EVP_MAX_BLOCK_LENGTH);
        EVP_EncryptUpdate(ctx, temp, &outlen, encrypted, encrypted_size);
        
        // Add random noise between layers if configured
        if (protect_config.add_random_noise) {
            size_t noise_size = rand() % 1024;
            unsigned char* noise = malloc(noise_size);
            RAND_bytes(noise, noise_size);
            memcpy(temp + outlen, noise, noise_size);
            outlen += noise_size;
            free(noise);
        }
        
        // Update for next layer
        memcpy(encrypted, temp, outlen);
        encrypted_size = outlen;
        
        // Clean up this layer
        free(temp);
        EVP_CIPHER_CTX_free(ctx);
        secure_wipe_memory(key, 32);
        secure_wipe_memory(iv, 16);
        free(key);
        free(iv);
    }
    
    // Write the final encrypted data
    result = original_functions.write(fd, encrypted, encrypted_size);
    
cleanup:
    if (encrypted) {
        secure_wipe_memory(encrypted, encrypted_size);
        free(encrypted);
    }
    return result;
}

// Intercept open
int open(const char* pathname, int flags, ...) {
    init_interceptor();
    
    mode_t mode = 0;
    if (flags & O_CREAT) {
        va_list args;
        va_start(args, flags);
        mode = va_arg(args, mode_t);
        va_end(args);
    }

    int fd = original_functions.open(pathname, flags, mode);
    if (fd >= 0 && (flags & O_WRONLY || flags & O_RDWR)) {
        // Track files opened for writing
        for (int i = 0; i < MAX_FILES; i++) {
            if (files[i].fd == 0) {
                files[i].fd = fd;
                files[i].path = strdup(pathname);
                files[i].needs_protection = !is_path_allowed(pathname);
                break;
            }
        }
    }
    return fd;
}

// Intercept write
ssize_t write(int fd, const void* buf, size_t count) {
    init_interceptor();

    // Find file info
    file_info* info = NULL;
    for (int i = 0; i < MAX_FILES; i++) {
        if (files[i].fd == fd) {
            info = &files[i];
            break;
        }
    }

    if (info && info->needs_protection) {
        switch (protect_mode) {
            case PROTECT_MODE_IGNORE:
                log_warning("Write ignored for non-whitelisted path: %s (size: %zu bytes)", 
                          info->path, count);
                return count;  // Pretend we wrote the data
                
            case PROTECT_MODE_ENCRYPT:
                if (is_path_allowed(info->path)) {
                    // Use checkpoint key for whitelisted paths
                    log_warning("Encrypting write with checkpoint key: %s (size: %zu bytes)", 
                              info->path, count);
                    return encrypt_with_checkpoint_key(fd, buf, count);
                } else {
                    // Use throwaway key for non-whitelisted paths
                    log_warning("Encrypting write with throwaway key: %s (size: %zu bytes)", 
                              info->path, count);
                    return encrypt_and_destroy(fd, buf, count);
                }
        }
    }

    return original_functions.write(fd, buf, count);
}

// Intercept close
int close(int fd) {
    init_interceptor();
    
    // Cleanup file tracking
    for (int i = 0; i < MAX_FILES; i++) {
        if (files[i].fd == fd) {
            free(files[i].path);
            memset(&files[i], 0, sizeof(file_info));
            break;
        }
    }
    
    return original_functions.close(fd);
}

// Public API
void set_protect_mode(protect_mode_t mode) {
    protect_mode = mode;
}

void set_log_file(const char* log_path) {
    if (log_file) {
        fclose(log_file);
        log_file = NULL;
    }
    if (log_path) {
        log_file = fopen(log_path, "a");
    }
}

void set_protect_config(const protect_config_t* config) {
    if (!config) return;
    
    protect_config.num_encryption_layers = 
        (config->num_encryption_layers < MIN_ENCRYPTION_LAYERS) ? MIN_ENCRYPTION_LAYERS :
        (config->num_encryption_layers > MAX_ENCRYPTION_LAYERS) ? MAX_ENCRYPTION_LAYERS :
        config->num_encryption_layers;
        
    protect_config.min_padding_size = config->min_padding_size;
    protect_config.max_padding_size = config->max_padding_size;
    protect_config.add_random_noise = config->add_random_noise;
}

// Restore original functions
void restore_original_io(void) {
    current_open = original_functions.open;
    current_write = original_functions.write;
    current_close = original_functions.close;
    current_mmap = original_functions.mmap;
} 