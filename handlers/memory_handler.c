#include <sys/mman.h>
#include "io_interceptor.h"

static io_handler_t memory_handler = {
    .init = memory_init,
    .cleanup = memory_cleanup,
    .handle_write = memory_write,
    .handle_read = memory_read
};

static void memory_init(void) {
    // Lock memory pages
    mlockall(MCL_CURRENT | MCL_FUTURE);
}

static void memory_cleanup(void) {
    munlockall();
}

static ssize_t memory_write(int fd, const void* buf, size_t count) {
    // Add random padding
    size_t padding = 0;
    if (g_state.config.random_padding) {
        RAND_bytes((uint8_t*)&padding, sizeof(padding));
        padding = padding % (count / 4) + 1;
    }
    
    uint8_t *padded_buf = malloc(count + padding);
    memcpy(padded_buf, buf, count);
    RAND_bytes(padded_buf + count, padding);
    
    ssize_t ret = write(fd, padded_buf, count + padding);
    
    OPENSSL_cleanse(padded_buf, count + padding);
    free(padded_buf);
    
    return (ret >= count) ? count : ret;
}

static ssize_t memory_read(int fd, void* buf, size_t count) {
    // Read with padding
    size_t total_size = count + (count / 4);  // Max padding size
    uint8_t *padded_buf = malloc(total_size);
    
    ssize_t read_size = read(fd, padded_buf, total_size);
    if (read_size < count) {
        free(padded_buf);
        return -1;
    }
    
    // Copy actual data without padding
    memcpy(buf, padded_buf, count);
    
    OPENSSL_cleanse(padded_buf, total_size);
    free(padded_buf);
    
    return count;
} 