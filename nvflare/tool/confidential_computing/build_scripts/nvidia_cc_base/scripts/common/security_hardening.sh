#!/bin/bash

# Security constants
readonly REQUIRED_TEE_FEATURES=(
    "memory_encryption=on"    # Memory encryption enabled
    "sev_snp"                # AMD SEV-SNP
    "tdx_guest"              # Intel TDX
)

# Security verification functions
verify_installation() {
    local checks=(
        "verify_tpm"
        "verify_tee_environment"
        "verify_tee_features"
        "verify_tee_measurements"
    )
    
    for check in "${checks[@]}"; do
        $check || error "Security check failed: $check"
    done
}

# Cleanup with security checks
cleanup_install() {
    local work_dir="$1"
    
    # Secure cleanup of sensitive files
    find "$work_dir" -type f -exec shred -u {} \;
    rm -rf "$work_dir"
    
    # Verify cleanup
    if [ -d "$work_dir" ]; then
        error "Failed to cleanup work directory"
    fi
}

# Security verification helpers
verify_tpm() {
    # Get TPM manufacturer info
    local manufacturer=$(tpm2_getcap properties-fixed | grep -A1 TPM2_PT_MANUFACTURER | tail -1)
    if [[ ! "$manufacturer" =~ ^(AMD|Intel|IBM)$ ]]; then
        error "Unsupported TPM manufacturer: $manufacturer"
        return 1
    fi

    # Check TPM version
    local version=$(tpm2_getcap properties-fixed | grep -A1 TPM2_PT_FIRMWARE_VERSION | tail -1)
    if [ "$version" -lt "$MIN_TPM_VERSION" ]; then
        error "TPM version too old: $version"
        return 1
    fi

    # Verify PCR values
    local pcr_values=$(tpm2_pcrread sha256:0,1,2,3,4,5,6,7)
    if ! verify_pcr_values "$pcr_values"; then
        error "TPM PCR values verification failed"
        return 1
    fi

    # Check TPM capabilities
    if ! tpm2_getcap properties-fixed | grep -q "TPM2_PT_NV_BUFFER_MAX"; then
        error "TPM missing required capabilities"
        return 1
    fi

    return 0
}

verify_pcr_values() {
    local pcr_values="$1"
    local expected_values="${TPM_EXPECTED_PCR_VALUES}"
    
    # Compare with expected values
    if [ "$pcr_values" != "$expected_values" ]; then
        return 1
    fi
    return 0
}

verify_tee_environment() {
    # Check CPU features
    if ! grep -q "sev" /proc/cpuinfo && ! grep -q "tdx" /proc/cpuinfo; then
        error "No SEV or TDX support found"
        return 1
    fi
    
    # Check TEE memory
    if [ ! -d "${TEE_MEMORY_PATH}" ] || \
       [ "$(stat -c %a ${TEE_MEMORY_PATH})" != "700" ]; then
        error "TEE memory path not properly configured"
        return 1
    fi
    
    # Check TEE driver status
    if ! lsmod | grep -q "^sev" && ! lsmod | grep -q "^tdx"; then
        error "Required TEE drivers not loaded"
        return 1
    }
    
    # Verify memory encryption
    if ! grep -q "memory_encryption=on" /proc/cmdline; then
        error "Memory encryption not enabled"
        return 1
    }

    return 0
}

# TEE feature verification
verify_tee_features() {
    for feature in "${REQUIRED_TEE_FEATURES[@]}"; do
        if ! grep -q "$feature" /proc/cpuinfo && ! dmesg | grep -q "$feature"; then
            error "Required TEE feature not found: $feature"
            return 1
        fi
    done
    return 0
}

# TEE measurements verification
verify_tee_measurements() {
    # Verify TEE measurements match expected values
    local measurements
    local report
    if grep -q "sev" /proc/cpuinfo; then
        # Get detailed SEV-SNP report
        report=$(sev-guest-get-report)
        measurements=$(echo "$report" | jq -r '.measurement')
        
        # Verify platform version
        local platform_version=$(echo "$report" | jq -r '.platform_version')
        if [ "$platform_version" -lt "$MIN_SEV_PLATFORM_VERSION" ]; then
            error "SEV platform version too old: $platform_version"
            return 1
        }
        
        # Verify TCB version
        local tcb_version=$(echo "$report" | jq -r '.tcb_version')
        if [ "$tcb_version" -lt "$MIN_SEV_TCB_VERSION" ]; then
            error "SEV TCB version too old: $tcb_version"
            return 1
        }
    elif grep -q "tdx" /proc/cpuinfo; then
        # Get detailed TDX quote
        report=$(tdx-guest-quote)
        measurements=$(echo "$report" | jq -r '.mr_seam + .mr_td + .rtmr')
        
        # Verify SGX TCB status
        local tcb_status=$(echo "$report" | jq -r '.tcb_status')
        if [ "$tcb_status" != "OK" ]; then
            error "TDX TCB status not OK: $tcb_status"
            return 1
        }
        
        # Verify SEAM version
        local seam_version=$(echo "$report" | jq -r '.seam_version')
        if [ "$seam_version" -lt "$MIN_TDX_SEAM_VERSION" ]; then
            error "TDX SEAM version too old: $seam_version"
            return 1
        }
    else
        error "No supported TEE found"
        return 1
    fi
    
    # Verify measurement values
    if ! verify_measurement_values "$measurements"; then
        error "TEE measurements verification failed"
        return 1
    fi
    
    # Verify measurement freshness
    if ! verify_measurement_freshness "$measurements"; then
        error "TEE measurements not fresh"
        return 1
    }
    return 0
}

# Verify measurement values against expected values
verify_measurement_values() {
    local measurements="$1"
    local expected_values
    
    # Load expected values based on TEE type
    if grep -q "sev" /proc/cpuinfo; then
        expected_values="${SEV_EXPECTED_MEASUREMENTS}"
    else
        expected_values="${TDX_EXPECTED_MEASUREMENTS}"
    fi
    
    # Compare with expected values
    if [ "$measurements" != "$expected_values" ]; then
        return 1
    fi
    return 0
}

# Verify measurement freshness
verify_measurement_freshness() {
    local measurements="$1"
    local timestamp
    
    # Get measurement timestamp
    if grep -q "sev" /proc/cpuinfo; then
        timestamp=$(sev-guest-get-report | jq -r '.timestamp')
    else
        timestamp=$(tdx-guest-quote | jq -r '.timestamp')
    fi
    
    # Check if measurement is recent (within last 5 minutes)
    local now=$(date +%s)
    local age=$((now - timestamp))
    if [ $age -gt 300 ]; then
        return 1
    fi
    return 0
} 