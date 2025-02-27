#!/bin/bash

# Install dependencies
install_deps() {
    if ! command -v bats >/dev/null 2>&1; then
        echo "Installing bats..."
        git clone https://github.com/bats-core/bats-core.git
        cd bats-core
        ./install.sh /usr/local
        cd ..
        rm -rf bats-core
    fi

    if ! command -v kcov >/dev/null 2>&1; then
        echo "Installing kcov..."
        apt-get update
        apt-get install -y kcov
    fi
}

# Run tests with coverage
run_tests_with_coverage() {
    local coverage_dir="coverage"
    mkdir -p "$coverage_dir"

    # Enable mock CVM mode for tests
    export MOCK_CVM=1

    echo "Running tests with coverage..."
    for test_file in tests/*.bats; do
        kcov --bash-method=DEBUG --include-pattern=.sh,.bash \
            "$coverage_dir/$(basename "$test_file")" \
            bats "$test_file"
    done

    # Generate coverage report
    echo "Generating coverage report..."
    kcov --merge "$coverage_dir/merged" "$coverage_dir"/*

    echo "Coverage report available at: $coverage_dir/merged/index.html"
}

# Main
install_deps
run_tests_with_coverage 