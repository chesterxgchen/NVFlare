#include "../core/interceptor.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main() {
    // Initialize IO interceptor with configuration
    io_config_t config = {
        .whitelist_paths = {
            "/workspace/checkpoints",
            "/workspace/models",
            NULL  // NULL terminate the list
        },
        .protection_mode = PROTECTION_MODE_ENCRYPT,
        .enable_random_padding = true,
        .min_padding_size = 4096
    };

    if (init_io_interceptor(&config) != 0) {
        fprintf(stderr, "Failed to initialize IO interceptor\n");
        return 1;
    }

    // Example 1: Write to whitelisted path (allowed & encrypted)
    const char *data = "Sensitive model data";
    FILE *f = fopen("/workspace/models/model.pt", "w");
    if (f) {
        fwrite(data, strlen(data), 1, f);
        fclose(f);
    }

    // Example 2: Read from whitelisted path (decrypted automatically)
    char buf[1024];
    f = fopen("/workspace/models/model.pt", "r");
    if (f) {
        fread(buf, sizeof(buf), 1, f);
        fclose(f);
    }

    // Example 3: Try writing to non-whitelisted path (blocked or encrypted based on mode)
    f = fopen("/tmp/model.pt", "w");
    if (f) {
        fwrite(data, strlen(data), 1, f);
        fclose(f);
    }

    // Example 4: Memory protection
    void *secure_mem = allocate_secure_memory(1024, MEM_TEE);
    if (secure_mem) {
        // Use secure memory
        memcpy(secure_mem, data, strlen(data));
        
        // Securely wipe and free
        free_secure_memory(secure_mem);
    }

    // Cleanup
    cleanup_io_interceptor();
    return 0;
} 