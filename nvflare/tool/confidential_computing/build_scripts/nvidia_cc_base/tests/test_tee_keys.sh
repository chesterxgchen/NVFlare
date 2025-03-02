#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"
source "${SCRIPT_DIR}/keys/key_management.sh"
source "${SCRIPT_DIR}/test_utils/keys/tee_mock.sh"

# Test AMD SEV-SNP key derivation
test_sev_snp_keys() {
    log "Testing SEV-SNP key derivation..."
    
    # Test vTPM measurements
    local vtpm_report=$(mock_snp_guest_vtpm_quote)
    if [ -z "$vtpm_report" ]; then
        error "Failed to get vTPM quote"
        return 1
    fi
    
    # Test PCR values parsing
    local pcr_values=$(mock_snp_guest_parse_vtpm --field pcr_values)
    if [ -z "$pcr_values" ]; then
        error "Failed to parse PCR values"
        return 1
    fi
    
    # Test key derivation
    local tpm_key=$(derive_tpm_key)
    if [ -z "$tpm_key" ]; then
        error "Failed to derive TPM key"
        return 1
    fi
    
    success "SEV-SNP key tests passed"
}

# Test Intel TDX key derivation
test_tdx_keys() {
    log "Testing TDX key derivation..."
    
    # Test RTMR measurements
    local rtmr_report=$(mock_tdx_rtmr_report)
    if [ -z "$rtmr_report" ]; then
        error "Failed to get RTMR report"
        return 1
    fi
    
    # Test RTMR values parsing
    local rtmr_values=$(mock_tdx_parse_rtmr --field rtmr_values)
    if [ -z "$rtmr_values" ]; then
        error "Failed to parse RTMR values"
        return 1
    }
    
    # Test key derivation
    local tpm_key=$(derive_tpm_key)
    if [ -z "$tpm_key" ]; then
        error "Failed to derive TPM key"
        return 1
    fi
    
    success "TDX key tests passed"
}

# Test TEE memory protection
test_tee_memory() {
    log "Testing TEE memory protection..."
    
    # Setup TEE memory
    setup_tee_environment
    
    # Test key storage in TEE memory
    local test_key="test_key_value"
    store_tee_key "$test_key" "test_key"
    
    # Verify permissions
    local key_path="${TEE_MEMORY_PATH}/keys/test_key"
    if [ "$(stat -c %a $key_path)" != "400" ]; then
        error "TEE key file has wrong permissions"
        return 1
    fi
    
    # Test key retrieval
    local retrieved_key=$(get_tee_key "test_key")
    if [ "$test_key" != "$retrieved_key" ]; then
        error "TEE key retrieval failed"
        return 1
    fi
    
    success "TEE memory tests passed"
}

# Run tests
test_sev_snp_keys
test_tdx_keys
test_tee_memory 