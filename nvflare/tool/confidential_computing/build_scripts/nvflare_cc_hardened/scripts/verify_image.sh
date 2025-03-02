#!/bin/bash

verify_image_integrity() {
    local image="$1"
    local failed=0

    # Verify dm-verity hashes
    if ! verify_verity_hashes "$image"; then
        error "Image integrity verification failed"
        failed=1
    }

    # Verify TPM measurements
    if ! verify_tpm_measurements "$image"; then
        error "TPM measurement verification failed"
        failed=1
    }

    # Verify partition sealing
    if ! verify_partition_sealing "$image"; then
        error "Partition seal verification failed"
        failed=1
    }

    # Verify security configurations
    if ! verify_security_configs "$image"; then
        error "Security configuration verification failed"
        failed=1
    }

    return $failed
} 