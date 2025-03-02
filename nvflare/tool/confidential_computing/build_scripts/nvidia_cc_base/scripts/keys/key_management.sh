#!/bin/bash

# Source configurations
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/internal/key_settings.conf"  # Internal key settings
source "${SCRIPT_DIR}/../../config/tee.conf"    # User config

# Key Management Functions
# - Hardware-bound key derivation
# - Partition key management
# - TEE memory protection

# Derive hardware-bound key from CPU features
derive_hw_key() {
    local cpu_vendor="$1"
    local hw_key=""
    
    case "$cpu_vendor" in
        "amd")
            # Get AMD SEV-SNP measurements
            hw_key=$(get_amd_binding)
            ;;
        "intel")
            # Get Intel TDX measurements
            hw_key=$(get_intel_binding)
            ;;
    esac
    
    echo "$hw_key"
}

# Combine with TPM measurements
derive_tpm_key() {
    local pcrs="${TEE_KEY_SETTINGS[SEAL_PCR]}"
    local tpm_key=""
    local cpu_vendor=$(detect_cpu_vendor)
    
    case "$cpu_vendor" in
        "amd")
            # Use AMD SEV-SNP Guest API for measurements
            local report_data=$(dd if=/dev/urandom bs=64 count=1 2>/dev/null | base64)
            local report=$("${AMD_SEV_GUEST_REPORT}" \
                --report-data "$report_data")
            
            # Extract measurements directly from JSON report
            local measurement=$(echo "$report" | jq -r '.measurement')
            local platform_info=$(echo "$report" | jq -r '.platform_info')
            pcr_values="${measurement}${platform_info}"
            tpm_key=$(echo -n "$pcr_values" | sha512sum | cut -d' ' -f1)
            ;;
        "intel")
            # Use Intel TDX Guest API
            local quote_data=$(dd if=/dev/urandom bs=64 count=1 2>/dev/null | base64)
            local report=$("${INTEL_TDX_GUEST_QUOTE}" \
                --data "$quote_data" \
                --type tdreport)
            
            # Extract TDX measurements directly from JSON report
            local rtmr=$(echo "$report" | jq -r '.rtmr[]' | tr -d '\n')
            local attributes=$(echo "$report" | jq -r '.attributes')
            rtmr_values="${rtmr}${attributes}"
            tpm_key=$(echo -n "$rtmr_values" | sha512sum | cut -d' ' -f1)
            ;;
    esac
    
    echo "$tpm_key"
}

# Generate partition encryption key
generate_partition_key() {
    local hw_key="$1"
    local tpm_key="$2"
    local partition="$3"
    
    # Combine hardware and TPM keys
    local combined_key=$(echo -n "${hw_key}${tpm_key}" | sha512sum | cut -d' ' -f1)
    
    # Derive partition-specific key
    local part_key=$(echo -n "${combined_key}${partition}" | sha512sum | cut -d' ' -f1)
    echo "$part_key"
}

# Store key in TEE memory
store_tee_key() {
    local key="$1"
    local name="$2"
    local tee_path="${TEE_MEMORY_PATH}/keys/${name}"
    
    # Ensure TEE memory is mounted
    mkdir -p "${TEE_MEMORY_PATH}/keys"
    chmod 0700 "${TEE_MEMORY_PATH}/keys"
    
    # Store key with secure permissions
    echo -n "$key" > "$tee_path"
    chmod 0400 "$tee_path"
}

# Retrieve key from TEE memory
get_tee_key() {
    local name="$1"
    local tee_path="${TEE_MEMORY_PATH}/keys/${name}"
    
    if [ -f "$tee_path" ]; then
        cat "$tee_path"
    else
        return 1
    fi
}

# Setup partition encryption
setup_partition_encryption() {
    local device="$1"
    local partition="$2"
    local hw_key="$3"
    local tpm_key="$4"
    
    # Generate partition key
    local part_key=$(generate_partition_key "$hw_key" "$tpm_key" "$partition")
    
    # Store in TEE memory
    store_tee_key "$part_key" "${partition}_key"
    
    # Setup LUKS encryption
    cryptsetup luksFormat \
        --type luks2 \
        --cipher "${LUKS_CIPHER}" \
        --key-size "${LUKS_KEY_SIZE}" \
        --key-file <(echo -n "$part_key") \
        "$device"
}

# Get AMD SEV-SNP measurements
get_amd_binding() {
    # Use AMD SEV-SNP Guest API
    local report_data=$(dd if=/dev/urandom bs=64 count=1 2>/dev/null | base64)
    
    # Get attestation report using SEV-SNP guest library
    local report=$("${AMD_SEV_GUEST_REPORT}" \
        --report-data "$report_data")
    
    # Extract measurements from report
    local measurement=$(echo "$report" | \
        "${AMD_SEV_GUEST_PARSE}" \
        --field measurement)
    
    local chip_id=$(echo "$report" | \
        "${AMD_SEV_GUEST_PARSE}" \
        --field chip-id)
    
    echo -n "${measurement}${chip_id}" | sha512sum | cut -d' ' -f1
}

# Get Intel TDX measurements
get_intel_binding() {
    # Use Intel Trust Authority Guest API
    local report_data=$(dd if=/dev/urandom bs=64 count=1 2>/dev/null | base64)
    
    # Get attestation report using ITA guest library
    local report=$("${INTEL_TDX_GUEST_QUOTE}" \
        --report-data "$report_data" \
        --quote-type tdx)
    
    # Extract measurements from report
    local measurement=$(echo "$report" | \
        "${INTEL_TDX_GUEST_PARSE}" \
        --field mr_td)
    
    local chip_id=$(echo "$report" | \
        "${INTEL_TDX_GUEST_PARSE}" \
        --field cpu_svn)
    
    echo -n "${measurement}${chip_id}" | sha512sum | cut -d' ' -f1
} 