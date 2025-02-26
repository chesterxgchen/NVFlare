#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <pthread.h>
#include "io_interceptor.h"

// Global state
static struct {
    io_config_t config;
    io_handler_t* handlers[3];  // encryption, memory, pattern
    pthread_mutex_t mutex;
    bool initialized;
} g_state = {0};

// Original function pointers
static struct {
    ssize_t (*write)(int fd, const void *buf, size_t count);
    ssize_t (*read)(int fd, void *buf, size_t count);
    int (*open)(const char *pathname, int flags, mode_t mode);
    int (*close)(int fd);
} orig_funcs = {0};

// Path validation
static bool is_whitelisted(const char* path) {
    if (!path) return false;
    
    for (size_t i = 0; i < g_state.config.num_paths; i++) {
        if (strncmp(path, g_state.config.whitelist_paths[i], strlen(g_state.config.whitelist_paths[i])) == 0) {
            return true;
        }
    }
    return false;
}

// Initialize interceptor
void init_io_interceptor(const io_config_t* config) {
    pthread_mutex_lock(&g_state.mutex);
    if (g_state.initialized) {
        pthread_mutex_unlock(&g_state.mutex);
        return;
    }

    // Store config
    memcpy(&g_state.config, config, sizeof(io_config_t));

    // Load original functions
    orig_funcs.write = dlsym(RTLD_NEXT, "write");
    orig_funcs.read = dlsym(RTLD_NEXT, "read");
    orig_funcs.open = dlsym(RTLD_NEXT, "open");
    orig_funcs.close = dlsym(RTLD_NEXT, "close");

    // Initialize handlers
    for (int i = 0; i < 3; i++) {
        if (g_state.handlers[i] && g_state.handlers[i]->init) {
            g_state.handlers[i]->init();
        }
    }

    g_state.initialized = true;
    pthread_mutex_unlock(&g_state.mutex);
}

// Cleanup interceptor
void cleanup_io_interceptor(void) {
    pthread_mutex_lock(&g_state.mutex);
    if (!g_state.initialized) {
        pthread_mutex_unlock(&g_state.mutex);
        return;
    }

    // Cleanup handlers
    for (int i = 0; i < 3; i++) {
        if (g_state.handlers[i] && g_state.handlers[i]->cleanup) {
            g_state.handlers[i]->cleanup();
        }
    }

    g_state.initialized = false;
    pthread_mutex_unlock(&g_state.mutex);
}

// Context management
void* begin_protection(protection_mode_t mode) {
    protection_mode_t* ctx = malloc(sizeof(protection_mode_t));
    *ctx = g_state.config.mode;
    g_state.config.mode = mode;
    return ctx;
}

void end_protection(void* ctx) {
    if (ctx) {
        g_state.config.mode = *(protection_mode_t*)ctx;
        free(ctx);
    }
}

// Intercepted functions
ssize_t write(int fd, const void *buf, size_t count) {
    if (!g_state.initialized) {
        return orig_funcs.write(fd, buf, count);
    }

    // Get file path
    char path[PATH_MAX];
    snprintf(path, sizeof(path), "/proc/self/fd/%d", fd);
    char real_path[PATH_MAX];
    if (readlink(path, real_path, sizeof(real_path)) == -1) {
        return orig_funcs.write(fd, buf, count);
    }

    // Check whitelist
    if (is_whitelisted(real_path)) {
        // Handle whitelisted path
        for (int i = 0; i < 3; i++) {
            if (g_state.handlers[i] && g_state.handlers[i]->handle_write) {
                ssize_t ret = g_state.handlers[i]->handle_write(fd, buf, count);
                if (ret != -1) return ret;
            }
        }
    } else if (g_state.config.mode == PROTECTION_MODE_ENCRYPT) {
        // Encrypt with throwaway key
        // ... encryption implementation
    }

    return orig_funcs.write(fd, buf, count);
}

// Similar implementations for read, open, close
ssize_t read(int fd, void *buf, size_t count) {
    if (!g_state.initialized) {
        return orig_funcs.read(fd, buf, count);
    }

    // Get file path
    char path[PATH_MAX];
    snprintf(path, sizeof(path), "/proc/self/fd/%d", fd);
    char real_path[PATH_MAX];
    if (readlink(path, real_path, sizeof(real_path)) == -1) {
        return orig_funcs.read(fd, buf, count);
    }

    // Check whitelist
    if (is_whitelisted(real_path)) {
        // Handle whitelisted path
        for (int i = 0; i < 3; i++) {
            if (g_state.handlers[i] && g_state.handlers[i]->handle_read) {
                ssize_t ret = g_state.handlers[i]->handle_read(fd, buf, count);
                if (ret != -1) return ret;
            }
        }
    } else if (g_state.config.mode == PROTECTION_MODE_ENCRYPT) {
        // Encrypt with throwaway key
        // ... encryption implementation
    }

    return orig_funcs.read(fd, buf, count);
}

int open(const char *pathname, int flags, mode_t mode) {
    if (!g_state.initialized) {
        return orig_funcs.open(pathname, flags, mode);
    }

    // Get file path
    char real_path[PATH_MAX];
    if (is_whitelisted(pathname)) {
        // Handle whitelisted path
        for (int i = 0; i < 3; i++) {
            if (g_state.handlers[i] && g_state.handlers[i]->handle_open) {
                int ret = g_state.handlers[i]->handle_open(pathname, flags, mode);
                if (ret != -1) return ret;
            }
        }
    } else if (g_state.config.mode == PROTECTION_MODE_ENCRYPT) {
        // Encrypt with throwaway key
        // ... encryption implementation
    }

    return orig_funcs.open(pathname, flags, mode);
}

int close(int fd) {
    if (!g_state.initialized) {
        return orig_funcs.close(fd);
    }

    // Get file path
    char path[PATH_MAX];
    snprintf(path, sizeof(path), "/proc/self/fd/%d", fd);
    char real_path[PATH_MAX];
    if (readlink(path, real_path, sizeof(real_path)) == -1) {
        return orig_funcs.close(fd);
    }

    // Check whitelist
    if (is_whitelisted(real_path)) {
        // Handle whitelisted path
        for (int i = 0; i < 3; i++) {
            if (g_state.handlers[i] && g_state.handlers[i]->handle_close) {
                int ret = g_state.handlers[i]->handle_close(fd);
                if (ret != -1) return ret;
            }
        }
    } else if (g_state.config.mode == PROTECTION_MODE_ENCRYPT) {
        // Encrypt with throwaway key
        // ... encryption implementation
    }

    return orig_funcs.close(fd);
} 