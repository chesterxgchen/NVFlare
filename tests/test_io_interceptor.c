#include <stdio.h>
#include <string.h>
#include <assert.h>
#include "io_interceptor.h"

void test_whitelist_path(void) {
    io_config_t config = {
        .whitelist_paths = (char*[]){"/tmp/test"},
        .num_paths = 1,
        .mode = PROTECTION_MODE_ENCRYPT,
        .random_padding = true
    };
    
    init_io_interceptor(&config);
    
    // Test whitelisted path
    FILE* f = fopen("/tmp/test/data.txt", "w");
    assert(f != NULL);
    const char* data = "test data";
    size_t written = fwrite(data, 1, strlen(data), f);
    assert(written == strlen(data));
    fclose(f);
    
    // Test non-whitelisted path
    f = fopen("/tmp/other/data.txt", "w");
    assert(f != NULL);
    written = fwrite(data, 1, strlen(data), f);
    assert(written == 0);  // Should be ignored
    fclose(f);
    
    cleanup_io_interceptor();
}

void test_protection_modes(void) {
    io_config_t config = {
        .whitelist_paths = (char*[]){"/tmp/test"},
        .num_paths = 1,
        .mode = PROTECTION_MODE_ENCRYPT,
        .random_padding = true
    };
    
    init_io_interceptor(&config);
    
    // Test ENCRYPT mode
    FILE* f = fopen("/tmp/other/data.txt", "w");
    assert(f != NULL);
    const char* data = "test data";
    size_t written = fwrite(data, 1, strlen(data), f);
    assert(written == strlen(data));  // Should be encrypted
    fclose(f);
    
    // Test IGNORE mode
    void* ctx = begin_protection(PROTECTION_MODE_IGNORE);
    f = fopen("/tmp/other/data2.txt", "w");
    assert(f != NULL);
    written = fwrite(data, 1, strlen(data), f);
    assert(written == 0);  // Should be ignored
    fclose(f);
    end_protection(ctx);
    
    cleanup_io_interceptor();
}

int main(void) {
    test_whitelist_path();
    test_protection_modes();
    printf("All tests passed!\n");
    return 0;
} 