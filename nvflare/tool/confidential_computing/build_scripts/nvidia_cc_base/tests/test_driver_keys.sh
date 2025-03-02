#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"
source "${SCRIPT_DIR}/lib/key_service.sh"

# Test driver key management
test_driver_keys() {
    log "Testing driver key management..."
    
    # Initialize key service
    init_key_service
    
    # Generate driver keys
    generate_key "nvidia_driver" "driver"
    local driver_key=$(get_key "nvidia_driver")
    if [ -z "$driver_key" ]; then
        error "Driver key generation failed"
        return 1
    fi
    
    # Test key permissions
    local key_path="${KEY_SERVICE_STORE}/nvidia_driver"
    if [ "$(stat -c %a $key_path)" != "400" ]; then
        error "Driver key has incorrect permissions"
        return 1
    fi
    
    success "Driver key tests passed"
}

# Run tests
test_driver_keys 