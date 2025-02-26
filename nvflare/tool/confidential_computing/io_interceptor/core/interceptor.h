#ifndef IO_INTERCEPTOR_H
#define IO_INTERCEPTOR_H

#include <stdbool.h>
#include <stdio.h>

#define MAX_PATHS 1024

// Operation types
typedef enum {
    OP_READ,
    OP_WRITE,
    OP_DELETE,
    OP_MODIFY
} operation_type_t;

// Path types
typedef enum {
    PATH_WHITELIST,
    PATH_SYSTEM,
    PATH_TMPFS,
    PATH_BLOCKED
} path_type_t;

// Function declarations
bool register_whitelist_path(const char* path);
bool register_system_path(const char* path);
bool register_tmpfs_path(const char* path);

// Internal functions (implemented in interceptor.c)
bool is_path_allowed(const char* path, int operation);
bool handle_system_path(const char* path, int operation);
bool handle_tmpfs_path(const char* path, int operation);
bool is_encrypted_path(const char* path);
bool is_encrypted_fd(int fd);
FILE* handle_encrypted_open(const char* path, const char* mode);
int handle_encrypted_open_flags(const char* path, int flags, mode_t mode);
ssize_t handle_encrypted_write(int fd, const void* buf, size_t count);
ssize_t handle_encrypted_read(int fd, void* buf, size_t count);
int get_operation_type(const char* mode);
int get_operation_type_flags(int flags);

#endif /* IO_INTERCEPTOR_H */ 