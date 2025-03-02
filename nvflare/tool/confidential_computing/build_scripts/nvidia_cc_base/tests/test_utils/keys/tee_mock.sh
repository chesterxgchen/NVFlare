#!/bin/bash

# Mock SEV-SNP guest report
mock_sev_guest_get_report() {
    cat <<EOF
{
    "version": 1,
    "guest_svn": 1,
    "policy": 0,
    "measurement": "1111111111111111111111111111111111111111111111111111111111111111",
    "platform_info": "2222222222222222222222222222222222222222222222222222222222222222",
    "signature": "3333333333333333333333333333333333333333333333333333333333333333"
}
EOF
}

# Mock RTMR for TDX
mock_tdx_guest_quote() {
    cat <<EOF
{
    "version": 1,
    "type": "tdreport",
    "rtmr": [
        "1111111111111111111111111111111111111111111111111111111111111111",
        "2222222222222222222222222222222222222222222222222222222222222222",
        "3333333333333333333333333333333333333333333333333333333333333333",
        "4444444444444444444444444444444444444444444444444444444444444444"
    ],
    "attributes": "5555555555555555555555555555555555555555555555555555555555555555",
    "signature": "6666666666666666666666666666666666666666666666666666666666666666"
}
EOF
}

# Mock TDX RTMR parser
mock_tdx_parse_rtmr() {
    local field="$2"
    local report=$(mock_tdx_guest_quote)
    
    case "$field" in
        "rtmr_values")
            echo "$report" | jq -r '.rtmr[]' | tr -d '\n'
            ;;
        *)
            echo "unknown"
            ;;
    esac
} 