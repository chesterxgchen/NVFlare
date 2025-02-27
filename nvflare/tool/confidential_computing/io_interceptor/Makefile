CC=gcc
CFLAGS=-Wall -Wextra -fPIC -I./core -I./handlers
LDFLAGS=-shared -lcrypto

SRCS=core/interceptor.c handlers/encryption_handler.c handlers/memory_handler.c
OBJS=$(SRCS:.c=.o)
LIB=libiointerceptor.so

TEST_SRCS=tests/test_handlers.c
TEST_BIN=run_tests

TEST_DIR = tests
TEST_SRC = $(TEST_DIR)/example.c

# Get OpenSSL flags from pkg-config
OPENSSL_CFLAGS := $(shell pkg-config --cflags openssl)
OPENSSL_LIBS := $(shell pkg-config --libs openssl)

CFLAGS += -Wall -Werror $(OPENSSL_CFLAGS)
LDFLAGS += $(OPENSSL_LIBS)

ifeq ($(shell uname),Darwin)
    SRC = handlers/encryption_darwin.c
else
    SRC = handlers/encryption_linux.c
endif

all: $(LIB) $(TEST_BIN)

$(LIB): $(OBJS)
	$(CC) $(LDFLAGS) -o $@ $^

$(TEST_BIN): $(TEST_SRCS) $(LIB)
	$(CC) $(CFLAGS) -o $@ $^ -L. -liointerceptor -lcrypto

test: $(TEST_SRC)
	$(CC) $(CFLAGS) $^ -L. -liointerceptor -o $(TEST_DIR)/example
	LD_LIBRARY_PATH=. ./$(TEST_DIR)/example

clean:
	rm -f $(OBJS) $(LIB) $(TEST_BIN)
	rm -f $(TEST_DIR)/example

install:
	cp $(LIB) /usr/lib/
	ldconfig 