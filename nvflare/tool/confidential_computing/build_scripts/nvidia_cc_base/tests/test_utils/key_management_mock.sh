#!/bin/bash

# Mock CPU feature reports
mock_snp_guest_report() {
    cat <<EOF
{
    "measurement": "0123456789abcdef0123456789abcdef",
    "chip_id": "AMD0123456789",
    "signature": "valid_signature"
}
EOF
}

mock_tdx_guest_report() {
    cat <<EOF
{
    "mr_td": "fedcba9876543210fedcba9876543210",
    "cpu_svn": "INTEL0123456789",
    "signature": "valid_signature"
}
EOF
}

# Mock TPM operations
mock_tpm2_pcrread() {
    echo "0000111122223333444455556666777788889999"
}

# Mock cryptsetup operations
mock_cryptsetup() {
    case "$1" in
        "luksFormat")
            return 0
            ;;
        "open")
            return 0
            ;;
        *)
            return 1
            ;;
    esac
} 