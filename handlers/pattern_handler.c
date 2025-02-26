#include <time.h>
#include "io_interceptor.h"

static io_handler_t pattern_handler = {
    .init = pattern_init,
    .cleanup = pattern_cleanup,
    .handle_write = pattern_write,
    .handle_read = pattern_read
};

static void add_random_delay(void) {
    struct timespec delay;
    RAND_bytes((uint8_t*)&delay.tv_nsec, sizeof(delay.tv_nsec));
    delay.tv_nsec = delay.tv_nsec % 1000000; // Max 1ms
    delay.tv_sec = 0;
    nanosleep(&delay, NULL);
}

static ssize_t pattern_write(int fd, const void* buf, size_t count) {
    add_random_delay();
    return -1; // Pass to next handler
}

static ssize_t pattern_read(int fd, void* buf, size_t count) {
    add_random_delay();
    return -1; // Pass to next handler
}

static void pattern_init(void) {
    // Initialize random number generator
    struct timespec ts;
    clock_gettime(CLOCK_REALTIME, &ts);
    srand(ts.tv_nsec);
}

static void pattern_cleanup(void) {
    // Nothing to cleanup
} 