#include <stdio.h>
#include "secure_io_interceptor.h"

int main() {
    // Initialize the interceptor
    init_secure_io();

    // Configure whitelist paths
    add_whitelist_path("/tmp/nvflare_test/safe", PATH_TYPE_EXACT);       // Single directory
    add_whitelist_path("/tmp/nvflare_test/models/", PATH_TYPE_PREFIX);   // Directory and subdirs
    add_whitelist_path("/tmp/nvflare_test/checkpoints/*.pt", PATH_TYPE_PATTERN); // Pattern matching

    // Set up logging
    set_log_file("/tmp/nvflare_test/io.log");

    // Configure protection
    protect_config_t config = {
        .num_encryption_layers = 3,
        .min_padding_size = 1024,
        .max_padding_size = 1024 * 1024,
        .add_random_noise = 1
    };
    set_protect_config(&config);

    // Set protection mode
    set_protect_mode(PROTECT_MODE_ENCRYPT);  // or PROTECT_MODE_IGNORE

    // Test writing to safe and unsafe paths
    FILE* safe_fp = fopen("/tmp/nvflare_test/safe/model.pt", "w");
    if (safe_fp) {
        fprintf(safe_fp, "Safe data");  // This will write normally
        fclose(safe_fp);
    }

    FILE* unsafe_fp = fopen("/tmp/nvflare_test/unsafe/model.pt", "w");
    if (unsafe_fp) {
        fprintf(unsafe_fp, "Sensitive data");  // This will be encrypted or ignored
        fclose(unsafe_fp);
    }

    cleanup_secure_io();
    return 0;
} 