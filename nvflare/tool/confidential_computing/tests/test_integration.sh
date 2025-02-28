#!/bin/bash

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

# Helper Functions
log() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')] $1${NC}"
}

error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}" >&2
    exit 1
}

# Test hardening with partitions
test_hardening_with_partitions() {
    log "Testing system hardening with partitions..."
    
    # Apply system hardening
    cd ../system_hardening
    ./secure_build.sh
    
    # Setup partitions
    cd ../partition
    ./setup_partitions.sh
    
    # Verify integration
    if ! systemctl is-active nvflare-partitions; then
        error "NVFLARE partition service not running"
    fi
    
    # Test encrypted workspace
    echo "test data" > /mnt/nvflare/workspace/test.txt
    if strings /dev/nvme0n1 | grep -q "test data"; then
        error "Found unencrypted data on disk"
    fi
}

# Run integration tests
test_hardening_with_partitions 