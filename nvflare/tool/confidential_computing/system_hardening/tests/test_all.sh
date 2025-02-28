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

# Check if running as root
if [[ $EUID -ne 0 ]]; then
    error "Please run as root (sudo)"
fi

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Test environment
TEST_ROOT="/tmp/nvflare_test"

# Cleanup function
cleanup() {
    log "Cleaning up test environment..."
    
    # Stop any running services
    systemctl stop nvflare-* 2>/dev/null || true
    
    # Remove test directories
    rm -rf "$TEST_ROOT"
    
    # Reset firewall rules
    iptables -F
    iptables -X
    
    # Unmount any test partitions
    for mp in $(mount | grep nvflare_test | cut -d' ' -f3); do
        umount "$mp" 2>/dev/null || true
    done
    
    # Remove device mappings
    dmsetup remove_all 2>/dev/null || true
    
    log "Cleanup completed"
}

# Set trap for cleanup
trap cleanup EXIT

# Create test environment
setup_env() {
    log "Setting up test environment..."
    mkdir -p "$TEST_ROOT"
    
    # Save original configurations
    if [ -f "/etc/iptables/rules.v4" ]; then
        cp "/etc/iptables/rules.v4" "$TEST_ROOT/iptables.backup"
    fi
}

# Run pre-test checks
pre_test_checks() {
    log "Running pre-test checks..."
    
    # Check required commands
    local required_cmds=(
        "cryptsetup"
        "lvm2"
        "parted"
        "systemctl"
        "iptables"
        "dmsetup"
    )
    
    for cmd in "${required_cmds[@]}"; do
        if ! command -v "$cmd" >/dev/null 2>&1; then
            error "Required command not found: $cmd"
        fi
    done
    
    # Check kernel modules
    local required_modules=(
        "dm_crypt"
        "dm_verity"
    )
    
    for module in "${required_modules[@]}"; do
        if ! lsmod | grep -q "^${module}"; then
            error "Required kernel module not loaded: $module"
        fi
    done
}

# Setup test environment
setup_env

# Run pre-test checks
pre_test_checks

# Test system hardening
log "Testing system hardening..."
cd "${SCRIPT_DIR}/system_hardening"
./tests/test_local.sh || error "System hardening tests failed"

# Test partition management
log "Testing partition management..."
cd "${SCRIPT_DIR}/partition"
./tests/test_local.sh || error "Partition tests failed"

# Run integration tests
log "Running integration tests..."
cd "${SCRIPT_DIR}"
./tests/test_integration.sh || error "Integration tests failed"

log "All tests completed successfully!" 