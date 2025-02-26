#ifndef MEMORY_HANDLER_H
#define MEMORY_HANDLER_H

#include <stdbool.h>
#include <sys/types.h>

// Memory region types
typedef enum {
    MEM_TEE,        // TEE protected memory
    MEM_TMPFS,      // Tmpfs in memory
    MEM_ENCRYPTED   // Encrypted memory
} mem_type_t;

// Memory region context
typedef struct memory_ctx {
    void* addr;         // Memory address
    size_t size;        // Region size
    mem_type_t type;    // Memory type
    bool locked;        // Whether memory is locked
} memory_ctx_t;

// Function declarations
memory_ctx_t* allocate_secure_memory(size_t size, mem_type_t type);
void free_secure_memory(memory_ctx_t* ctx);
bool lock_memory_region(memory_ctx_t* ctx);
bool wipe_memory_region(memory_ctx_t* ctx);

#endif /* MEMORY_HANDLER_H */ 