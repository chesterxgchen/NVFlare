#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"
source "${SCRIPT_DIR}/lib/key_management.sh"

# Test hardware key derivation
test_hw_key_derivation() {
    local test_dir=$(mktemp -d)
    
    # Test AMD key derivation
    local amd_key=$(derive_hw_key "amd")
    if [ -z "$amd_key" ]; then
        error "Failed to derive AMD hardware key"
    fi
    
    # Test Intel key derivation
    local intel_key=$(derive_hw_key "intel")
    if [ -z "$intel_key" ]; then
        error "Failed to derive Intel hardware key"
    fi
    
    # Verify keys are different
    if [ "$amd_key" = "$intel_key" ]; then
        error "AMD and Intel keys should be different"
    fi
    
    cleanup_test "$test_dir"
}

# Test TPM key derivation
test_tpm_key_derivation() {
    local tpm_key=$(derive_tpm_key)
    if [ -z "$tpm_key" ]; then
        error "Failed to derive TPM key"
    fi
}

# Test partition key generation
test_partition_key_generation() {
    local hw_key="test_hw_key"
    local tpm_key="test_tpm_key"
    
    # Generate keys for different partitions
    local root_key=$(generate_partition_key "$hw_key" "$tpm_key" "root")
    local apps_key=$(generate_partition_key "$hw_key" "$tpm_key" "cc_apps")
    
    # Verify keys are different
    if [ "$root_key" = "$apps_key" ]; then
        error "Partition keys should be different"
    fi
}

# Test TEE key storage
test_tee_key_storage() {
    local test_key="test_key_value"
    local test_name="test_key"
    
    # Store key
    store_tee_key "$test_key" "$test_name"
    
    # Retrieve key
    local retrieved_key=$(get_tee_key "$test_name")
    if [ "$test_key" != "$retrieved_key" ]; then
        error "Retrieved key does not match stored key"
    fi
    
    # Check permissions
    local key_path="${TEE_MEMORY_PATH}/keys/${test_name}"
    if [ "$(stat -c %a $key_path)" != "400" ]; then
        error "Key file has wrong permissions"
    fi
}

# Run tests
test_hw_key_derivation
test_tpm_key_derivation
test_partition_key_generation
test_tee_key_storage 