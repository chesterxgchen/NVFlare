#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"
source "${SCRIPT_DIR}/keys/key_service.sh"

# Test key lifecycle
test_key_lifecycle() {
    log "Testing key lifecycle..."
    
    # Test initialization
    init_key_service
    if [ ! -d "${KEY_SERVICE_STATE}" ]; then
        error "Key service initialization failed"
        return 1
    fi
    
    # Test hardware binding
    if ! verify_binding; then
        error "Hardware binding verification failed"
        return 1
    fi
    
    # Test key generation and retrieval
    local test_key_name="test_key"
    generate_key "$test_key_name" "test"
    local retrieved_key=$(get_key "$test_key_name")
    if [ -z "$retrieved_key" ]; then
        error "Key generation/retrieval failed"
        return 1
    fi
    
    success "Key lifecycle tests passed"
}

# Test partition key management
test_partition_keys() {
    log "Testing partition key management..."
    
    # Test root partition key
    local root_key=$(get_key "root_key")
    if [ -z "$root_key" ]; then
        error "Root partition key not found"
        return 1
    fi
    
    # Test CC apps partition key
    local apps_key=$(get_key "cc_apps_key")
    if [ -z "$apps_key" ]; then
        error "CC apps partition key not found"
        return 1
    fi
    
    success "Partition key tests passed"
}

# Run tests
test_key_lifecycle
test_partition_keys 