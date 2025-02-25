#define _GNU_SOURCE
#include <sys/types.h>
#include <sys/stat.h>
#include <unistd.h>
#include <stdio.h>
#include <string.h>
#include <assert.h>
#include <fcntl.h>
#include "secure_io_interceptor.h"

// Test helper functions
static void setup_test_env() {
    // Create test directories
    system("mkdir -p /tmp/nvflare_test/safe");
    system("mkdir -p /tmp/nvflare_test/unsafe");
    
    // Set safe path
    set_safe_path("/tmp/nvflare_test/safe");
    
    // Set log file
    set_log_file("/tmp/nvflare_test/io_test.log");
}

static void teardown_test_env() {
    // Cleanup test directories
    system("rm -rf /tmp/nvflare_test");
}

// Test cases
void test_safe_path_write() {
    const char* test_data = "test data";
    const char* test_path = "/tmp/nvflare_test/safe/test.txt";
    
    // Write to safe path
    FILE* fp = fopen(test_path, "w");
    assert(fp != NULL && "Should open file in safe path");
    
    size_t written = fwrite(test_data, 1, strlen(test_data), fp);
    assert(written == strlen(test_data) && "Should write all data");
    
    fclose(fp);
    
    // Verify data was written normally
    char buffer[256];
    fp = fopen(test_path, "r");
    assert(fp != NULL && "Should read file");
    
    size_t read = fread(buffer, 1, sizeof(buffer), fp);
    buffer[read] = '\0';
    assert(strcmp(buffer, test_data) == 0 && "Data should match");
    
    fclose(fp);
}

void test_ignore_mode() {
    // Set up configuration
    secure_io_config_t config = {
        .mode = PROTECT_MODE_IGNORE,
        .safe_path = "/tmp/nvflare_test/safe",
        .log_path = "/tmp/nvflare_test/io_test.log",
        .is_active = 1,
        .encrypt_config = {
            .num_encryption_layers = 3,
            .min_padding_size = 1024,
            .max_padding_size = 1024 * 1024,
            .add_random_noise = 1
        }
    };

    // Initialize with config
    init_secure_io(&config);

    const char* test_data = "test data";
    const char* test_path = "/tmp/nvflare_test/unsafe/ignored.txt";
    
    // Use config in operations
    int fd = secure_open(test_path, O_WRONLY | O_CREAT, 0644, &config);
    assert(fd >= 0 && "Should open file");
    
    ssize_t written = secure_write(fd, test_data, strlen(test_data), &config);
    assert(written == strlen(test_data) && "Write should appear to succeed");
    
    secure_close(fd, &config);
    
    // Verify file is empty or doesn't exist
    struct stat st;
    int exists = stat(test_path, &st) == 0;
    assert((!exists || st.st_size == 0) && "File should be empty or non-existent");
}

void test_encrypt_mode() {
    const char* test_data = "sensitive data";
    const char* test_path = "/tmp/nvflare_test/unsafe/encrypted.txt";
    
    // Set encrypt mode
    set_protect_mode(PROTECT_MODE_ENCRYPT);
    
    // Write to unsafe path
    FILE* fp = fopen(test_path, "w");
    assert(fp != NULL && "Should open file");
    
    size_t written = fwrite(test_data, 1, strlen(test_data), fp);
    assert(written == strlen(test_data) && "Write should succeed");
    
    fclose(fp);
    
    // Verify file exists but content is encrypted
    fp = fopen(test_path, "r");
    assert(fp != NULL && "Should read file");
    
    char buffer[256];
    size_t read = fread(buffer, 1, strlen(test_data), fp);
    assert(read == strlen(test_data) && "Should read same number of bytes");
    assert(memcmp(buffer, test_data, strlen(test_data)) != 0 && "Data should be encrypted");
    
    fclose(fp);
}

void test_log_output() {
    const char* test_path = "/tmp/nvflare_test/unsafe/logged.txt";
    const char* test_data = "test data";
    
    // Set ignore mode and write
    set_protect_mode(PROTECT_MODE_IGNORE);
    FILE* fp = fopen(test_path, "w");
    fwrite(test_data, 1, strlen(test_data), fp);
    fclose(fp);
    
    // Check log file
    fp = fopen("/tmp/nvflare_test/io_test.log", "r");
    assert(fp != NULL && "Log file should exist");
    
    char buffer[1024];
    size_t read = fread(buffer, 1, sizeof(buffer), fp);
    buffer[read] = '\0';
    fclose(fp);
    
    assert(strstr(buffer, "WARNING") != NULL && "Log should contain warning");
    assert(strstr(buffer, test_path) != NULL && "Log should contain path");
}

void test_multiple_files() {
    // Test handling multiple files simultaneously
    FILE* safe_fp = fopen("/tmp/nvflare_test/safe/safe1.txt", "w");
    FILE* unsafe_fp1 = fopen("/tmp/nvflare_test/unsafe/unsafe1.txt", "w");
    FILE* unsafe_fp2 = fopen("/tmp/nvflare_test/unsafe/unsafe2.txt", "w");
    
    const char* test_data = "test data";
    
    fwrite(test_data, 1, strlen(test_data), safe_fp);
    fwrite(test_data, 1, strlen(test_data), unsafe_fp1);
    fwrite(test_data, 1, strlen(test_data), unsafe_fp2);
    
    fclose(safe_fp);
    fclose(unsafe_fp1);
    fclose(unsafe_fp2);
    
    // Verify safe file is readable
    char buffer[256];
    safe_fp = fopen("/tmp/nvflare_test/safe/safe1.txt", "r");
    size_t read = fread(buffer, 1, sizeof(buffer), safe_fp);
    buffer[read] = '\0';
    fclose(safe_fp);
    
    assert(strcmp(buffer, test_data) == 0 && "Safe file should be readable");
}

int main() {
    printf("Running secure IO interceptor tests...\n");
    
    // Initialize interception
    init_secure_io(&config);
    
    // Run tests with interception active
    test_safe_path_write();
    test_ignore_mode();
    test_encrypt_mode();
    
    // Restore original system calls
    restore_original_io();
    
    printf("All tests passed successfully!\n");
    return 0;
} 