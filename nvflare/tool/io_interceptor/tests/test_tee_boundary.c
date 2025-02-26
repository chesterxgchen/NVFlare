#include "../core/interceptor.h"
#include <assert.h>

void test_tee_memory_boundaries() {
    // Test memory alignment
    void* mem = allocate_secure_memory(1023, MEM_TEE);
    assert(((uintptr_t)mem & 0xFFF) == 0); // Should be page aligned
    
    // Test crossing page boundaries
    char* data = (char*)mem;
    for (int i = 0; i < 4096; i++) {
        data[i] = 'A'; // Should not fault
    }
    
    free_secure_memory(mem);
}

void test_tee_encryption_boundaries() {
    // Test large data encryption crossing pages
    size_t large_size = 1024 * 1024; // 1MB
    char* large_data = allocate_secure_memory(large_size, MEM_TEE);
    
    encryption_ctx_t ctx = {0};
    init_encryption_context(&ctx, 256);
    
    // Should handle cross-page encryption
    assert(encrypt_data(&ctx, large_data, large_size) == 0);
    
    free_secure_memory(large_data);
} 