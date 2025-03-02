#!/bin/bash

# Mock Intel TDX guest tools for testing
mock_ita_guest_get_report() {
    cat <<EOF
{
    "version": 1,
    "cpu_svn": "0000000000000000",
    "mr_seam": "1111111111111111111111111111111111111111111111111111111111111111",
    "mr_td": "2222222222222222222222222222222222222222222222222222222222222222",
    "mr_config_id": "3333333333333333333333333333333333333333333333333333333333333333",
    "mr_owner": "4444444444444444444444444444444444444444444444444444444444444444",
    "mr_owner_config": "5555555555555555555555555555555555555555555555555555555555555555",
    "rtmr_0": "6666666666666666666666666666666666666666666666666666666666666666",
    "rtmr_1": "7777777777777777777777777777777777777777777777777777777777777777",
    "rtmr_2": "8888888888888888888888888888888888888888888888888888888888888888",
    "rtmr_3": "9999999999999999999999999999999999999999999999999999999999999999",
    "report_data": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "signature": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
}
EOF
}

# Mock report parsing
mock_ita_guest_parse_report() {
    local field="$2"
    local report=$(mock_ita_guest_get_report)
    
    case "$field" in
        "mr_td")
            echo "$report" | jq -r '.mr_td'
            ;;
        "cpu_svn")
            echo "$report" | jq -r '.cpu_svn'
            ;;
        *)
            echo "unknown"
            ;;
    esac
} 