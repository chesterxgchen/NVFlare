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
#include "interceptor.h"

// Original function pointers
static FILE* (*original_fopen)(const char*, const char*) = NULL;
static int (*original_open)(const char*, int, mode_t) = NULL;
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

// Initialize interceptor
__attribute__((constructor))
static void init_interceptor(void) {
    // Load original functions
    original_fopen = dlsym(RTLD_NEXT, "fopen");
    original_open = dlsym(RTLD_NEXT, "open");
    original_write = dlsym(RTLD_NEXT, "write");
    original_read = dlsym(RTLD_NEXT, "read");
    original_close = dlsym(RTLD_NEXT, "close");
    original_unlink = dlsym(RTLD_NEXT, "unlink");
}

// Path validation
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
        errno = EACCES;
        return NULL;
    }
    
    if (is_encrypted_path(path)) {
        return handle_encrypted_open(path, mode);
    }
    
    return original_fopen(path, mode);
}

int open(const char* path, int flags, ...) {
    mode_t mode = 0;
    if (flags & O_CREAT) {
        va_list args;
        va_start(args, flags);
        mode = va_arg(args, mode_t);
        va_end(args);
    }
    
    if (!is_path_allowed(path, get_operation_type_flags(flags))) {
        errno = EACCES;
        return -1;
    }
    
    if (is_encrypted_path(path)) {
        return handle_encrypted_open_flags(path, flags, mode);
    }
    
    return original_open(path, flags, mode);
}

ssize_t write(int fd, const void* buf, size_t count) {
    if (is_encrypted_fd(fd)) {
        return handle_encrypted_write(fd, buf, count);
    }
    return original_write(fd, buf, count);
}

ssize_t read(int fd, void* buf, size_t count) {
    if (is_encrypted_fd(fd)) {
        return handle_encrypted_read(fd, buf, count);
    }
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