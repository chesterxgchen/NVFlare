#include <sys/mman.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include "memory_handler.h"

memory_ctx_t* allocate_secure_memory(size_t size, mem_type_t type) {
    memory_ctx_t* ctx = calloc(1, sizeof(memory_ctx_t));
    if (!ctx) return NULL;

    // Allocate memory with proper protection
    void* addr = mmap(NULL, size, PROT_READ | PROT_WRITE,
                     MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (addr == MAP_FAILED) {
        free(ctx);
        return NULL;
    }

    ctx->addr = addr;
    ctx->size = size;
    ctx->type = type;
    ctx->locked = false;

    // Lock memory if TEE or encrypted
    if (type != MEM_TMPFS) {
        if (!lock_memory_region(ctx)) {
            free_secure_memory(ctx);
            return NULL;
        }
    }

    return ctx;
}

void free_secure_memory(memory_ctx_t* ctx) {
    if (!ctx) return;

    // Wipe memory before freeing
    wipe_memory_region(ctx);

    // Unlock if locked
    if (ctx->locked) {
        munlock(ctx->addr, ctx->size);
    }

    // Unmap memory
    munmap(ctx->addr, ctx->size);
    free(ctx);
}

bool lock_memory_region(memory_ctx_t* ctx) {
    if (!ctx || ctx->locked) return false;

    // Lock memory to prevent swapping
    if (mlock(ctx->addr, ctx->size) != 0) {
        return false;
    }

    ctx->locked = true;
    return true;
}

bool wipe_memory_region(memory_ctx_t* ctx) {
    if (!ctx || !ctx->addr) return false;

    // Secure memory wiping
    memset(ctx->addr, 0, ctx->size);
    __asm__ volatile("" : : "r"(ctx->addr) : "memory");
    
    return true;
} 