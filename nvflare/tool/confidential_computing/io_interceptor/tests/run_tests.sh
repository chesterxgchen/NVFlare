#!/bin/bash

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

# Check for required tools
command -v valgrind >/dev/null 2>&1 || { echo "valgrind is required but not installed. Aborting." >&2; exit 1; }
command -v gcov >/dev/null 2>&1 || { echo "gcov is required but not installed. Aborting." >&2; exit 1; }

# Test files
TEST_FILES=(
    "test_error_handling"
    "test_tee_boundary"
    "benchmark"
)

# Compile all tests
echo "Compiling tests..."
for test in "${TEST_FILES[@]}"; do
    gcc -o ${test} ${test}.c -L.. -liointerceptor -lcrypto -fprofile-arcs -ftest-coverage -g
    if [ $? -ne 0 ]; then
        echo -e "${RED}Failed to compile ${test}${NC}"
        exit 1
    fi
done

# Function to run test with memory check
run_test_with_memcheck() {
    local test_name=$1
    echo -e "\n${GREEN}Running memory check for ${test_name}...${NC}"
    valgrind --leak-check=full \
             --show-leak-kinds=all \
             --track-origins=yes \
             --verbose \
             --log-file=${test_name}_valgrind.log \
             ./${test_name}
    
    if grep -q "ERROR SUMMARY: 0 errors" ${test_name}_valgrind.log; then
        echo -e "${GREEN}✓ No memory leaks detected${NC}"
    else
        echo -e "${RED}✗ Memory leaks detected! Check ${test_name}_valgrind.log${NC}"
        exit 1
    fi
}

# Run error handling tests
echo -e "\n${GREEN}Running error handling tests...${NC}"
run_test_with_memcheck test_error_handling
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Error handling tests passed${NC}"
else
    echo -e "${RED}✗ Error handling tests failed${NC}"
    exit 1
fi

# Run TEE boundary tests
echo -e "\n${GREEN}Running TEE boundary tests...${NC}"
run_test_with_memcheck test_tee_boundary
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ TEE boundary tests passed${NC}"
else
    echo -e "${RED}✗ TEE boundary tests failed${NC}"
    exit 1
fi

# Run benchmarks
echo -e "\n${GREEN}Running performance benchmarks...${NC}"
./benchmark

# Generate coverage report
echo -e "\n${GREEN}Generating coverage report...${NC}"
gcov *.gcda

# Print coverage summary
echo -e "\n${GREEN}Coverage Summary:${NC}"
for file in *.gcov; do
    echo "Coverage for ${file%.*}:"
    grep -A2 "File '.*'" $file | tail -n2
done

# Cleanup
echo -e "\n${GREEN}Cleaning up...${NC}"
rm -f test_error_handling test_tee_boundary benchmark \
      *.gcno *.gcda *.gcov *_valgrind.log

echo -e "\n${GREEN}All tests completed successfully${NC}" 