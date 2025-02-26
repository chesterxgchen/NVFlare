#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
#include <syslog.h>
#include <stdarg.h>
#include <time.h>
#include <limits.h>  // For PATH_MAX
#include <fnmatch.h>
#include "../handlers/encryption_handler.h"

#ifndef PATH_MAX
#define PATH_MAX 4096     // Default value if not defined
#endif

#include "interceptor.h"

// Original function pointers
static FILE* (*original_fopen)(const char*, const char*) = NULL;
static int (*original_open)(const char*, int, ...) = NULL;
static ssize_t (*original_write)(int, const void*, size_t) = NULL;
static ssize_t (*original_read)(int, void*, size_t) = NULL;
static int (*original_close)(int) = NULL;
static int (*original_unlink)(const char*) = NULL;

// Path control lists
static char* whitelist_paths[MAX_PATHS] = {NULL};
static char* system_paths[MAX_PATHS] = {NULL};
static char* tmpfs_paths[MAX_PATHS] = {NULL};
static int num_whitelist = 0;
static int num_system = 0;
static int num_tmpfs = 0;

// Audit logging
static FILE* audit_file = NULL;
static char audit_path[PATH_MAX] = "/var/log/nvflare/io_interceptor.log";

// Log levels for monitoring
#define MONITOR_LEVEL_PUBLIC  1  // Can be exposed outside TEE
#define MONITOR_LEVEL_PRIVATE 2  // Must stay in TEE

// Monitoring configuration
struct monitoring_config {
    int enabled;
    int sock_fd;
    char host[64];
    int port;
    char auth_token[256];
} monitor_cfg = {
    .enabled = 0,
    .sock_fd = -1,
    .host = "127.0.0.1",
    .port = 8125,
    .auth_token = ""
};

// Encryption pattern tracking
#define MAX_PATTERNS 128
static path_pattern_t encryption_patterns[MAX_PATTERNS];
static int num_patterns = 0;

// TEE key management
static struct tee_keys tee_keys = {0};

static bool initialize_tee_keys(void) {
    return initialize_encryption_keys(&tee_keys);
}

static bool derive_file_key(const char* path) {
    return derive_encryption_key(&tee_keys, path);
}

bool add_encryption_pattern(const char* pattern, encrypt_policy_t policy) {
    if (num_patterns >= MAX_PATTERNS) {
        return false;
    }
    strncpy(encryption_patterns[num_patterns].pattern, pattern, 255);
    encryption_patterns[num_patterns].pattern[255] = '\0';
    encryption_patterns[num_patterns].policy = policy;
    num_patterns++;
    return true;
}

bool remove_encryption_pattern(const char* pattern) {
    for (int i = 0; i < num_patterns; i++) {
        if (strcmp(encryption_patterns[i].pattern, pattern) == 0) {
            // Remove by shifting remaining elements
            for (int j = i; j < num_patterns - 1; j++) {
                encryption_patterns[j] = encryption_patterns[j + 1];
            }
            num_patterns--;
            return true;
        }
    }
    return false;
}

encrypt_policy_t get_path_encryption_policy(const char* path) {
    for (int i = 0; i < num_patterns; i++) {
        if (fnmatch(encryption_patterns[i].pattern, path, 0) == 0) {
            return encryption_patterns[i].policy;
        }
    }
    return ENCRYPT_NONE;
}

static bool should_encrypt_operation(const char* path, int mode) {
    encrypt_policy_t policy = get_path_encryption_policy(path);
    
    switch (policy) {
        case ENCRYPT_READ_WRITE:
            return true;
        case ENCRYPT_WRITE_ONLY:
            // Only encrypt write operations
            return (mode & O_WRONLY) || (mode & O_RDWR);
        case ENCRYPT_NONE:
        default:
            return false;
    }
}

static void log_monitoring_event(const char* path, const char* operation, const char* reason) {
    // Just log to syslog/audit file - monitoring handled by external tools
    syslog(LOG_INFO, "Operation: %s, Path: %s, Result: %s", 
           operation, path, reason);
}

const char* get_timestamp(void) {
    static char timestamp[32];
    time_t now = time(NULL);
    strftime(timestamp, sizeof(timestamp), "%Y-%m-%d %H:%M:%S", localtime(&now));
    return timestamp;
}

void init_audit_logging(void) {
    // Create log directory if it doesn't exist
    char* last_slash = strrchr(audit_path, '/');
    if (last_slash) {
        *last_slash = '\0';
        mkdir(audit_path, 0750);  // rwxr-x---
        *last_slash = '/';
    }
    
    // Open audit file
    audit_file = fopen(audit_path, "a");
    if (audit_file) {
        // Set permissions to rw-r-----
        fchmod(fileno(audit_file), 0640);
    }
}

// Logging configuration
#define LOG_IDENT "io_interceptor"
#define MAX_LOG_MSG 1024

// Log levels for different events
#define LOG_LEVEL_DENY    LOG_WARNING   // Access denied events
#define LOG_LEVEL_ENCRYPT LOG_INFO      // Encryption operations
#define LOG_LEVEL_ALLOW   LOG_DEBUG     // Allowed operations

void log_security_event(const char* path, const char* operation, const char* reason) {
    // Determine monitoring level
    int monitor_level = is_sensitive_operation(operation) ? 
                       MONITOR_LEVEL_PRIVATE : 
                       MONITOR_LEVEL_PUBLIC;

    // Only expose non-sensitive logs
    if (monitor_level == MONITOR_LEVEL_PUBLIC) {
        // Sanitize sensitive information
        char safe_path[PATH_MAX];
        sanitize_path_for_logs(path, safe_path);
        
        // Log sanitized info for monitoring
        log_monitoring_event(safe_path, operation, reason);
    }

    // Full logging inside TEE
    char msg[MAX_LOG_MSG];
    snprintf(msg, sizeof(msg), "Security: %s - Path: %s, Operation: %s, PID: %d, UID: %d", 
            reason, path, operation, getpid(), getuid());
    
    // Log to syslog
    openlog(LOG_IDENT, LOG_PID | LOG_NDELAY, LOG_AUTH);
    
    // Choose log level based on event type
    int level = strstr(reason, "denied") ? LOG_LEVEL_DENY :
                strstr(reason, "Encrypted") ? LOG_LEVEL_ENCRYPT :
                LOG_LEVEL_ALLOW;
    
    syslog(level, "%s", msg);
    closelog();
    
    // Also log to our audit file if configured
    if (audit_file) {
        fprintf(audit_file, "[%s] %s\n", get_timestamp(), msg);
        fflush(audit_file);
    }
}

// Path sanitization for logs
static void sanitize_path_for_logs(const char* path, char* safe_path) {
    if (!path || !safe_path) {
        return;
    }

    // Check if path contains sensitive directories
    const char* sensitive_dirs[] = {
        "/etc/nvflare/security",
        "/etc/ssl/private",
        "/etc/keys",
        "/root",
        NULL
    };

    // Check if path should be redacted
    for (const char** dir = sensitive_dirs; *dir; dir++) {
        if (strncmp(path, *dir, strlen(*dir)) == 0) {
            snprintf(safe_path, PATH_MAX, "<REDACTED>%s", 
                    path + strlen(*dir));  // Show only non-sensitive part
            return;
        }
    }

    // If not sensitive, copy as-is
    strncpy(safe_path, path, PATH_MAX - 1);
    safe_path[PATH_MAX - 1] = '\0';  // Ensure null termination
}

// Configuration
typedef struct {
    char* rw_patterns;  // Read-write encryption patterns
    char* wo_patterns;  // Write-only encryption patterns
} interceptor_config_t;

// Initialize with config file
bool init_interceptor_config(const char* config_path) {
    FILE* fp = fopen(config_path, "r");
    if (!fp) {
        syslog(LOG_ERR, "Failed to open config file: %s", config_path);
        return false;
    }

    char line[1024];
    while (fgets(line, sizeof(line), fp)) {
        // Skip comments and empty lines
        if (line[0] == '#' || line[0] == '\n') continue;

        char* key = strtok(line, "=");
        char* value = strtok(NULL, "\n");
        if (!key || !value) continue;

        // Trim whitespace
        while (*value == ' ') value++;

        if (strcmp(key, "ENCRYPT_RW_PATHS") == 0) {
            config.rw_patterns = strdup(value);
        } else if (strcmp(key, "ENCRYPT_WO_PATHS") == 0) {
            config.wo_patterns = strdup(value);
        }
    }

    fclose(fp);
    return true;
}

// Initialize interceptor
__attribute__((constructor))
static void init_interceptor(void) {
    // Initialize audit logging first
    init_audit_logging();

    // Initialize default system and tmpfs paths
    init_default_paths();

    // Initialize encryption patterns from config file
    const char* config_path = "/etc/nvflare/interceptor.conf";
    if (!init_interceptor_config(config_path)) {
        syslog(LOG_WARNING, "Failed to load config, using defaults");
    }

    // Load original functions
    original_fopen = dlsym(RTLD_NEXT, "fopen");
    original_open = dlsym(RTLD_NEXT, "open");
    original_write = dlsym(RTLD_NEXT, "write");
    original_read = dlsym(RTLD_NEXT, "read");
    original_close = dlsym(RTLD_NEXT, "close");
    original_unlink = dlsym(RTLD_NEXT, "unlink");
}

// Path validation
static bool handle_system_path(const char* path, int operation) {
    // Only allow read operations on system paths
    if (operation == O_RDONLY) {
        return true;
    }
    return false;
}

static bool handle_tmpfs_path(const char* path, int operation) {
    // Allow both read and write to tmpfs
    return true;
}

static bool is_path_allowed(const char* path, int operation) {
    // Check whitelist
    for (int i = 0; i < num_whitelist; i++) {
        if (strncmp(path, whitelist_paths[i], strlen(whitelist_paths[i])) == 0) {
            return true;
        }
    }
    
    // Check system paths
    for (int i = 0; i < num_system; i++) {
        if (strncmp(path, system_paths[i], strlen(system_paths[i])) == 0) {
            return handle_system_path(path, operation);
        }
    }
    
    // Check tmpfs paths
    for (int i = 0; i < num_tmpfs; i++) {
        if (strncmp(path, tmpfs_paths[i], strlen(tmpfs_paths[i])) == 0) {
            return handle_tmpfs_path(path, operation);
        }
    }
    
    return false;
}

// Intercepted functions
FILE* fopen(const char* path, const char* mode) {
    if (!is_path_allowed(path, get_operation_type(mode))) {
        log_security_event(path, mode, "Access denied - Path not allowed");
        errno = EPERM;
        return NULL;
    }
    
    // All writes must be encrypted
    if (strchr(mode, 'w') || strchr(mode, 'a')) {
        if (!initialize_tee_keys() || !derive_file_key(path)) {
            log_security_event(path, mode, "Failed to initialize encryption");
            errno = EIO;
            return NULL;
        }
        log_security_event(path, mode, "Encrypted file access");
        return handle_encrypted_open(path, mode);
    }
    
    // For reads, check if file is encrypted
    if (is_encrypted_path(path)) {
        if (!initialize_tee_keys() || !derive_file_key(path)) {
            log_security_event(path, mode, "Failed to initialize decryption");
            errno = EIO;
            return NULL;
        }
        return handle_encrypted_open(path, mode);
    }
    
    log_security_event(path, mode, "Access allowed");
    return original_fopen(path, mode);
}

int open(const char* path, int flags, ...) {
    int mode = 0;
    if (flags & O_CREAT) {
        va_list args;
        va_start(args, flags);
        mode = va_arg(args, int);
        va_end(args);
    }
    
    if (!is_path_allowed(path, get_operation_type_flags(flags))) {
        log_security_event(path, mode, "Access denied - Path not allowed");
        errno = EPERM;   // Operation not permitted (error code 1)
        return -1;
    }
    
    if (should_encrypt_operation(path, flags)) {
        // Log encrypted file access with flags
        char op_desc[64];
        snprintf(op_desc, sizeof(op_desc), "open(flags=0x%x)", flags);
        log_security_event(path, op_desc, "Encrypted file access");
        return handle_encrypted_open_flags(path, flags, mode);
    }
    
    // Log allowed access
    char op_desc[64];
    snprintf(op_desc, sizeof(op_desc), "open(flags=0x%x)", flags);
    log_security_event(path, op_desc, "Access allowed");
    return original_open(path, flags, mode);
}

ssize_t write(int fd, const void* buf, size_t count) {
    if (is_encrypted_fd(fd)) {
        log_security_event("<fd>", "write", "Encrypted file write");
        return handle_encrypted_write(fd, buf, count);
    }
    log_security_event("<fd>", "write", "Standard write");
    return original_write(fd, buf, count);
}

ssize_t read(int fd, void* buf, size_t count) {
    if (is_encrypted_fd(fd)) {
        log_security_event("<fd>", "read", "Encrypted file read");
        return handle_encrypted_read(fd, buf, count);
    }
    log_security_event("<fd>", "read", "Standard read");
    return original_read(fd, buf, count);
}

// Path registration functions
bool register_whitelist_path(const char* path) {
    if (num_whitelist >= MAX_PATHS) return false;
    whitelist_paths[num_whitelist++] = strdup(path);
    return true;
}

bool register_system_path(const char* path) {
    if (num_system >= MAX_PATHS) {
        return false;
    }
    system_paths[num_system] = strdup(path);
    if (system_paths[num_system] == NULL) {
        return false;
    }
    num_system++;
    return true;
}

bool register_tmpfs_path(const char* path) {
    if (num_tmpfs >= MAX_PATHS) {
        return false;
    }
    tmpfs_paths[num_tmpfs] = strdup(path);
    if (tmpfs_paths[num_tmpfs] == NULL) {
        return false;
    }
    num_tmpfs++;
    return true;
}

// Initialize default paths
static void init_default_paths(void) {
    // System paths - common read-only system directories
    register_system_path("/bin");
    register_system_path("/sbin");
    register_system_path("/lib");
    register_system_path("/lib64");
    register_system_path("/usr/bin");
    register_system_path("/usr/sbin");
    register_system_path("/usr/lib");
    register_system_path("/usr/lib64");
    register_system_path("/etc");  // System configuration files

    // Tmpfs paths - temporary file systems
    register_tmpfs_path("/tmp");
    register_tmpfs_path("/dev/shm");  // Shared memory
    register_tmpfs_path("/run");      // Runtime data
    register_tmpfs_path("/sys/fs/cgroup");
}

// Cleanup on unload
__attribute__((destructor))
static void cleanup_interceptor(void) {
    // Free config strings
    free(config.rw_patterns);
    free(config.wo_patterns);

    // Securely wipe TEE keys
    if (tee_keys.initialized) {
        cleanup_encryption_keys(&tee_keys);
    }

    if (audit_file) {
        fclose(audit_file);
        audit_file = NULL;
    }
} 