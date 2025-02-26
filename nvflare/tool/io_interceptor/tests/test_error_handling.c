#include "../core/interceptor.h"
#include <assert.h>
#include <errno.h>

void test_path_validation_errors() {
    // Test NULL path
    assert(validate_path(NULL) == false);
    assert(errno == EINVAL);

    // Test empty path
    assert(validate_path("") == false);
    assert(errno == EINVAL);

    // Test path too long
    char long_path[4096] = {0};
    memset(long_path, 'a', 4095);
    assert(validate_path(long_path) == false);
    assert(errno == ENAMETOOLONG);
}

void test_memory_allocation_errors() {
    // Test zero size allocation
    assert(allocate_secure_memory(0, MEM_TEE) == NULL);
    assert(errno == EINVAL);

    // Test excessive size
    assert(allocate_secure_memory(SIZE_MAX, MEM_TEE) == NULL);
    assert(errno == ENOMEM);
}

void test_encryption_errors() {
    // Test invalid key size
    encryption_ctx_t ctx = {0};
    assert(init_encryption_context(&ctx, 123) == -1);
    assert(errno == EINVAL);

    // Test invalid IV
    ctx.iv_len = 0;
    assert(encrypt_data(&ctx, "test", 4) == -1);
    assert(errno == EINVAL);
} 