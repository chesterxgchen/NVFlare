#ifndef SECURE_IO_INTERCEPTOR_H
#define SECURE_IO_INTERCEPTOR_H

#include <stddef.h>

// Protection modes
typedef enum {
    PROTECT_MODE_IGNORE,    // Ignore writes to protected paths
    PROTECT_MODE_ENCRYPT    // Encrypt writes to protected paths
} protect_mode_t;

// Configuration options
typedef struct {
    size_t num_encryption_layers;  // Number of encryption passes
    size_t min_padding_size;       // Minimum random padding
    size_t max_padding_size;       // Maximum random padding
    int add_random_noise;          // Add noise between layers
} protect_config_t;

// Error codes
#define MAX_FILES 1024
#define SECURE_IO_SUCCESS          0
#define SECURE_IO_ERROR_PARAM     -1
#define SECURE_IO_ERROR_KEY       -2
#define SECURE_IO_ERROR_FILE      -3
#define SECURE_IO_ERROR_MEMORY    -4
#define SECURE_IO_ERROR_ENCRYPT   -5
#define SECURE_IO_ERROR_DECRYPT   -6
#define SECURE_IO_ERROR_BUFFER    -7
#define SECURE_IO_ERROR_LOCK      -8
#define SECURE_IO_ERROR_INIT      -9
#define SECURE_IO_ERROR_BACKUP    -10
#define SECURE_IO_ERROR_RESTORE   -11
#define SECURE_IO_ERROR_INTERRUPT  -12

// Whitelist path structure
#define MAX_WHITELIST_PATHS 64
#define MAX_PATH_LENGTH 4096

typedef enum {
    PATH_TYPE_EXACT,     // Exact path match
    PATH_TYPE_PREFIX,    // Path prefix match
    PATH_TYPE_PATTERN    // Pattern match (glob)
} path_match_type_t;

typedef struct {
    char path[MAX_PATH_LENGTH];
    path_match_type_t type;
} whitelist_path_t;

// Default configuration
#define DEFAULT_ENCRYPTION_LAYERS 3
#define DEFAULT_MIN_PADDING 1024
#define DEFAULT_MAX_PADDING (1024 * 1024)
#define DEFAULT_RANDOM_NOISE 1
#define DEFAULT_PROTECT_MODE PROTECT_MODE_ENCRYPT

// Configuration structure with defaults
typedef struct {
    protect_mode_t mode;          // Default: PROTECT_MODE_ENCRYPT
    char* safe_path;             // Must be set by user
    protect_config_t encrypt_config;  // Uses defaults if not set
    char* log_path;              // Optional
    int is_active;              // Default: 1
} secure_io_config_t;

// Public API
void set_safe_path(const char* path);
void set_protect_mode(protect_mode_t mode);
void set_protect_config(const protect_config_t* config);
void set_log_file(const char* log_path);  // For warnings/logs
int restore_from_backup(const char* filepath);
void cleanup_backups(void);
void add_whitelist_path(const char* path, path_match_type_t type);
void clear_whitelist_paths(void);
void restore_original_io(void);  // Restore original system calls

// Modified API
int init_secure_io(secure_io_config_t* config);
ssize_t secure_write(int fd, const void* buf, size_t count, secure_io_config_t* config);
int secure_open(const char* pathname, int flags, mode_t mode, secure_io_config_t* config);
int secure_close(int fd, secure_io_config_t* config);

// Initialize with defaults
void init_secure_io_with_defaults(const char* safe_path);

// Standard whitelist paths
typedef struct {
    const char* path;
    path_match_type_t type;
} whitelist_entry_t;

// Common whitelist patterns
static const whitelist_entry_t STANDARD_WHITELIST[] = {
    {"/tmp/nvflare/checkpoints", PATH_TYPE_EXACT},      // Exact checkpoint dir
    {"/tmp/nvflare/models/", PATH_TYPE_PREFIX},         // All model files
    {"/tmp/nvflare/data/*.pt", PATH_TYPE_PATTERN},      // PyTorch files
    {"/tmp/nvflare/data/*.pth", PATH_TYPE_PATTERN},     // PyTorch files
    {"/tmp/nvflare/data/*.ckpt", PATH_TYPE_PATTERN},    // Checkpoint files
    {NULL, 0}  // End marker
};

// Add standard whitelist paths
void add_standard_whitelist(void);

#endif // SECURE_IO_INTERCEPTOR_H 