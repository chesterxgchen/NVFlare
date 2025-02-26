#ifndef IO_INTERCEPTOR_H
#define IO_INTERCEPTOR_H

#include <stddef.h>
#include <stdbool.h>

// Protection modes
typedef enum {
    PROTECTION_MODE_ENCRYPT,  // Encrypt non-whitelisted writes
    PROTECTION_MODE_IGNORE    // Ignore non-whitelisted writes
} protection_mode_t;

// Handler interface
typedef struct {
    void (*init)(void);
    void (*cleanup)(void);
    ssize_t (*handle_write)(int fd, const void* buf, size_t count);
    ssize_t (*handle_read)(int fd, void* buf, size_t count);
} io_handler_t;

// Main interceptor config
typedef struct {
    char** whitelist_paths;
    size_t num_paths;
    protection_mode_t mode;
    bool random_padding;
} io_config_t;

// Public API
void init_io_interceptor(const io_config_t* config);
void cleanup_io_interceptor(void);

// Context manager API
void* begin_protection(protection_mode_t mode);
void end_protection(void* ctx);

#endif 