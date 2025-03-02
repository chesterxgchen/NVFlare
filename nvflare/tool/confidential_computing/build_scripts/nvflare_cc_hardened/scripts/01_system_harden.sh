#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../config/hardening.conf"

# Disable unnecessary services
for service in "${DISABLE_SERVICES[@]}"; do
    systemctl disable "$service"
    systemctl mask "$service"
done

# Configure firewall
for port_config in "${ALLOWED_PORTS[@]}"; do
    IFS=':' read -r port proto desc <<< "$port_config"
    ufw allow "$port/$proto" comment "$desc"
done
ufw enable

# Configure audit
auditctl -R "$AUDIT_RULES" 