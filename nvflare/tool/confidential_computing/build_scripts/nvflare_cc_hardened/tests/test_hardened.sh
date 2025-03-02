#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../config/hardening.conf"

# Test system hardening
test_system() {
    # Test disabled services
    for service in "${DISABLE_SERVICES[@]}"; do
        if systemctl is-enabled "$service" &>/dev/null; then
            error "Service $service should be disabled"
        fi
    done

    # Test firewall
    for port_config in "${ALLOWED_PORTS[@]}"; do
        IFS=':' read -r port proto _ <<< "$port_config"
        if ! ufw status | grep -q "$port/$proto"; then
            error "Port $port/$proto not configured in firewall"
        fi
    done

    # Test mount points
    if [ -f "$LUKS_KEYFILE" ]; then
        if ! cryptsetup status "nvflare_input" &>/dev/null; then
            error "Input encryption not active"
        fi
        if ! cryptsetup status "nvflare_output" &>/dev/null; then
            error "Output encryption not active"
        fi
    fi

    # Test audit
    if ! auditctl -l | grep -q "nvflare"; then
        error "Audit rules not configured"
    fi
}

test_system 