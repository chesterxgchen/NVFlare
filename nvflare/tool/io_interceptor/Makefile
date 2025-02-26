CC=gcc
CFLAGS=-Wall -Wextra -fPIC -I./core -I./handlers
LDFLAGS=-shared -lcrypto

SRCS=core/interceptor.c handlers/encryption_handler.c handlers/memory_handler.c
OBJS=$(SRCS:.c=.o)
LIB=libiointerceptor.so

TEST_SRCS=tests/test_handlers.c
TEST_BIN=run_tests

all: $(LIB) $(TEST_BIN)

$(LIB): $(OBJS)
	$(CC) $(LDFLAGS) -o $@ $^

$(TEST_BIN): $(TEST_SRCS) $(LIB)
	$(CC) $(CFLAGS) -o $@ $^ -L. -liointerceptor -lcrypto

%.o: %.c
	$(CC) $(CFLAGS) -c -o $@ $<

clean:
	rm -f $(OBJS) $(LIB) $(TEST_BIN)

test: $(TEST_BIN)
	LD_LIBRARY_PATH=. ./$(TEST_BIN) 