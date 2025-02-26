#include <stdio.h>
#include <string.h>
#include <assert.h>
#include <fcntl.h>
#include <unistd.h>
#include "../handlers/encryption_handler.h"
#include "../handlers/memory_handler.h"

void test_encryption() {
    // Create test file
    int fd = open("/tmp/test.enc", O_RDWR | O_CREAT, 0600);
    assert(fd != -1);

    // Create encryption context
    encryption_ctx_t* ctx = create_encryption_ctx(fd, "/tmp/test.enc");
    assert(ctx != NULL);

    // Test encryption
    const char* test_data = "Test data for encryption";
    ssize_t written = encrypt_data(ctx, test_data, strlen(test_data));
    assert(written > 0);

    // Test decryption
    char decrypted[100] = {0};
    ssize_t read_len = decrypt_data(ctx, decrypted, written);
    assert(read_len > 0);
    assert(strcmp(test_data, decrypted) == 0);

    // Cleanup
    destroy_encryption_ctx(ctx);
    close(fd);
    unlink("/tmp/test.enc");
}

void test_memory() {
    // Test secure memory allocation
    size_t test_size = 1024;
    memory_ctx_t* ctx = allocate_secure_memory(test_size, MEM_TEE);
    assert(ctx != NULL);
    assert(ctx->size == test_size);
    assert(ctx->type == MEM_TEE);
    assert(ctx->locked == true);

    // Test memory locking
    assert(lock_memory_region(ctx) == true);

    // Test memory wiping
    assert(wipe_memory_region(ctx) == true);

    // Cleanup
    free_secure_memory(ctx);
}

int main() {
    printf("Running encryption tests...\n");
    test_encryption();
    printf("Encryption tests passed\n");

    printf("Running memory tests...\n");
    test_memory();
    printf("Memory tests passed\n");

    return 0;
} 