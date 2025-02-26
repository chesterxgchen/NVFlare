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

// Initialize interceptor
__attribute__((constructor))
static void init_interceptor(void) {
    // Initialize audit logging first
    init_audit_logging();

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
        errno = EPERM;   // Operation not permitted (error code 1)
        return NULL;
    }
    
    if (is_encrypted_path(path)) {
        // Log encrypted file access
        log_security_event(path, mode, "Encrypted file access");
        return handle_encrypted_open(path, mode);
    }
    
    // Log allowed access
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
    
    if (is_encrypted_path(path)) {
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
    if (num_system >= MAX_PATHS) return false;
    system_paths[num_system++] = strdup(path);
    return true;
}

bool register_tmpfs_path(const char* path) {
    if (num_tmpfs >= MAX_PATHS) return false;
    tmpfs_paths[num_tmpfs++] = strdup(path);
    return true;
}

// Cleanup on unload
__attribute__((destructor))
static void cleanup_interceptor(void) {
    if (audit_file) {
        fclose(audit_file);
        audit_file = NULL;
    }
} 