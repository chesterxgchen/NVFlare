#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"
source "${SCRIPT_DIR}/../config/security.conf"
source "${SCRIPT_DIR}/scripts/common/security_hardening.sh"
source "${SCRIPT_DIR}/../scripts/keys/key_management.sh"

test_keys() {
    local test_dir=$(mktemp -d)
    guestmount -a "$OUTPUT_IMAGE" -i "$test_dir"

    # Test hardware key derivation
    test_hw_key_derivation() {
        local cpu_vendor=$(detect_cpu_vendor)
        local hw_key=$(derive_hw_key "$cpu_vendor")
        
        if [ -z "$hw_key" ]; then
            error "Failed to derive hardware key"
        fi
        
        # Test invalid vendor
        if derive_hw_key "invalid_vendor" 2>/dev/null; then
            error "Should fail with invalid CPU vendor"
        fi
        
        # Test vendor-specific measurements
        case "$cpu_vendor" in
            "amd")
                local amd_binding=$(get_amd_binding)
                if [ -z "$amd_binding" ]; then
                    error "Failed to get AMD SEV-SNP binding"
                fi
                # Test report data validation
                if ! "${AMD_SEV_GUEST_PARSE}" --validate "$amd_binding"; then
                    error "Invalid AMD SEV-SNP report data"
                fi
                ;;
            "intel")
                local intel_binding=$(get_intel_binding)
                if [ -z "$intel_binding" ]; then
                    error "Failed to get Intel TDX binding"
                fi
                # Test quote validation
                if ! "${INTEL_TDX_GUEST_PARSE}" --validate "$intel_binding"; then
                    error "Invalid Intel TDX quote"
                fi
                ;;
        esac
        
        # Test key uniqueness
        local second_key=$(derive_hw_key "$cpu_vendor")
        if [ "$hw_key" != "$second_key" ]; then
            error "Hardware key not deterministic"
        fi
    }

    # Test TPM key derivation
    test_tpm_key_derivation() {
        local tpm_key=$(derive_tpm_key)
        if [ -z "$tpm_key" ]; then
            error "Failed to derive TPM key"
        fi
        
        # Test PCR values
        local pcrs="${TEE_KEY_SETTINGS[SEAL_PCR]}"
        if [ -z "$pcrs" ]; then
            error "TPM PCR selection not configured"
        fi
        
        # Test PCR read permissions
        if ! tpm2_pcrread sha256:0,1,2,3,4,5,6,7 > /dev/null 2>&1; then
            error "Cannot read TPM PCRs"
        fi
        
        # Test TPM locality
        if [ "$(tpm2_getcap properties-fixed | grep -A1 TPM2_PT_LOCALITY_1 | tail -1)" != "1" ]; then
            error "TPM locality not properly set"
        fi
    }

    # Test partition key management
    test_partition_keys() {
        local hw_key=$(derive_hw_key "$(detect_cpu_vendor)")
        local tpm_key=$(derive_tpm_key)
        
        # Test key generation
        for partition in "root" "app" "dynamic"; do
            local part_key=$(generate_partition_key "$hw_key" "$tpm_key" "$partition")
            if [ -z "$part_key" ]; then
                error "Failed to generate key for partition $partition"
            fi
            
            # Test key strength
            local key_length=${#part_key}
            if [ "$key_length" -lt 64 ]; then
                error "Partition key too short: $key_length bytes"
            fi
            
            # Test key storage in TEE memory
            store_tee_key "$part_key" "${partition}_key"
            local retrieved_key=$(get_tee_key "${partition}_key")
            if [ "$part_key" != "$retrieved_key" ]; then
                error "Key mismatch for partition $partition"
            fi
            
            # Test key isolation
            if [ -r "${TEE_MEMORY_PATH}/keys/${partition}_key" ]; then
                error "TEE key file readable by non-root user"
            fi
            
            # Test key persistence
            sync  # Ensure filesystem sync
            if [ -f "/var/log/cc/keys/${partition}_key" ]; then
                error "Key persisted to disk"
            fi
        done
        
        # Test concurrent access
        (
            store_tee_key "test_key" "concurrent_test" &
            store_tee_key "test_key2" "concurrent_test" &
            wait
        ) || error "Concurrent key storage failed"
    }

    # Test driver keys
    test_driver_keys() {
        # Test key generation
        if [ ! -d "${test_dir}/etc/cc/keys/drivers" ]; then
            error "Driver keys directory not found"
        fi

        # Test key signing
        for module in nvidia nvidia_uvm nvidia_drm; do
            if [ ! -f "${test_dir}/lib/modules/$(uname -r)/updates/dkms/${module}.ko.signed" ]; then
                error "Driver module '$module' not signed"
            fi
        done
    }

    # Test key lifecycle management
    test_key_lifecycle() {
        # Test key rotation
        if [ ! -f "${test_dir}/etc/cc/keys/rotation.conf" ]; then
            error "Key rotation config not found"
        fi

        # Test key backup
        if [ ! -d "${test_dir}/etc/cc/keys/backup" ]; then
            error "Key backup directory not found"
        fi

        # Test key revocation
        if [ ! -f "${test_dir}/etc/cc/keys/revocation.list" ]; then
            error "Key revocation list not found"
        fi
        
        # Test key service
        if ! chroot "$test_dir" systemctl is-enabled cc-key-service | grep -q "enabled"; then
            error "Key service not enabled"
        fi

        # Test key permissions
        if [ "$(stat -c %a ${test_dir}/etc/cc/keys)" != "700" ]; then
            error "Key directory has wrong permissions"
        fi

        # Test key storage
        if [ ! -f "${test_dir}/etc/cc/keys/master.key" ]; then
            error "Master key not found"
        fi
        
        # Test key rotation schedule
        local rotation_interval=$(grep "^ROTATION_INTERVAL=" "${test_dir}/etc/cc/keys/rotation.conf" | cut -d= -f2)
        if [ "$rotation_interval" -gt 90 ]; then
            error "Key rotation interval too long: $rotation_interval days"
        fi
        
        # Test backup encryption
        if ! grep -q "^BACKUP_ENCRYPTION=yes" "${test_dir}/etc/cc/keys/backup/config"; then
            error "Key backups not encrypted"
        fi
        
        # Test revocation propagation
        local revoked_key="test_revoke_key"
        echo "$revoked_key" >> "${test_dir}/etc/cc/keys/revocation.list"
        if ! grep -q "^$revoked_key" "${test_dir}/etc/cc/keys/revocation.list.sig"; then
            error "Revocation list not signed"
        fi
    }

    # Test TEE keys
    test_tee_keys() {
        # Test TEE memory setup
        setup_tee_environment
        
        # Test key storage in TEE memory
        local test_key="test_key_value"
        store_tee_key "$test_key" "test_key"
        
        # Verify permissions
        local key_path="${TEE_MEMORY_PATH}/keys/test_key"
        if [ "$(stat -c %a $key_path)" != "400" ]; then
            error "TEE key file has wrong permissions"
        fi
        
        # Test key retrieval
        local retrieved_key=$(get_tee_key "test_key")
        if [ "$test_key" != "$retrieved_key" ]; then
            error "TEE key retrieval failed"
        fi

        # Test vendor-specific key derivation
        if grep -q "AMD" /proc/cpuinfo; then
            # Test vTPM measurements
            local vtpm_report=$(mock_snp_guest_vtpm_quote)
            if [ -z "$vtpm_report" ]; then
                error "Failed to get vTPM quote"
            fi
            
            # Test PCR values parsing
            local pcr_values=$(mock_snp_guest_parse_vtpm --field pcr_values)
            if [ -z "$pcr_values" ]; then
                error "Failed to parse PCR values"
            fi
        elif grep -q "Intel" /proc/cpuinfo; then
            # Test RTMR measurements
            local rtmr_report=$(mock_tdx_rtmr_report)
            if [ -z "$rtmr_report" ]; then
                error "Failed to get RTMR report"
            fi
            
            # Test RTMR values parsing
            local rtmr_values=$(mock_tdx_parse_rtmr --field rtmr_values)
            if [ -z "$rtmr_values" ]; then
                error "Failed to parse RTMR values"
            fi
        fi

        # Test TEE key generation
        if [ ! -f "${test_dir}/etc/cc/keys/tee/measurement.key" ]; then
            error "TEE measurement key not found"
        fi

        # Test TEE key binding
        if ! verify_tee_key_binding; then
            error "TEE key binding verification failed"
        fi

        # Test TEE key attestation
        if [ ! -f "${test_dir}/etc/cc/keys/tee/attestation.key" ]; then
            error "TEE attestation key not found"
        fi
    }

    # Run all tests
    test_hw_key_derivation
    test_tpm_key_derivation
    test_partition_keys
    test_driver_keys
    test_key_lifecycle
    test_tee_keys

    # Cleanup
    guestunmount "$test_dir"
    rm -rf "$test_dir"
}

# Run tests
test_keys

