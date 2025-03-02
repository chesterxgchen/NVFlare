#!/bin/bash

# Mock SEV-SNP guest tools for testing
mock_snp_guest_attestation() {
    cat <<EOF
{
    "version": 1,
    "guest_svn": 1,
    "policy": 0,
    "family_id": "0000000000000000000000000000000000000000000000000000000000000000",
    "image_id": "0000000000000000000000000000000000000000000000000000000000000000",
    "measurement": "1111111111111111111111111111111111111111111111111111111111111111",
    "host_data": "0000000000000000000000000000000000000000000000000000000000000000",
    "id_key_digest": "2222222222222222222222222222222222222222222222222222222222222222",
    "author_key_digest": "3333333333333333333333333333333333333333333333333333333333333333",
    "report_data": "4444444444444444444444444444444444444444444444444444444444444444",
    "chip_id": "0123456789ABCDEF",
    "signature": "5555555555555555555555555555555555555555555555555555555555555555"
}
EOF
}

# Mock report parsing
mock_snp_guest_parse_report() {
    local field="$2"
    local report=$(mock_snp_guest_attestation)
    
    case "$field" in
        "measurement")
            echo "$report" | jq -r '.measurement'
            ;;
        "chip-id")
            echo "$report" | jq -r '.chip_id'
            ;;
        *)
            echo "unknown"
            ;;
    esac
} 