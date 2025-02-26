CC = gcc
CFLAGS = -Wall -Werror -I./include
LDFLAGS = -ldl -lcrypto

SRCS = core/interceptor.c \
       handlers/encryption_handler.c \
       handlers/memory_handler.c \
       handlers/pattern_handler.c

OBJS = $(SRCS:.c=.o)

all: libio_interceptor.so test_io_interceptor

libio_interceptor.so: $(OBJS)
	$(CC) -shared -o $@ $^ $(LDFLAGS)

test_io_interceptor: tests/test_io_interceptor.c libio_interceptor.so
	$(CC) $(CFLAGS) -o $@ $< -L. -lio_interceptor $(LDFLAGS)

clean:
	rm -f $(OBJS) libio_interceptor.so test_io_interceptor

.PHONY: all clean 