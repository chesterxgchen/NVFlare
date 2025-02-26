#!/bin/bash

# Function to check root access
check_root() {
    if [ "$(id -u)" != "0" ]; then
        echo "Error: This script must be run as root"
        exit 1
    fi
}

# Function to clean existing rules
clean_rules() {
    iptables -F
    iptables -X
    iptables -t nat -F
    iptables -t nat -X
    iptables -t mangle -F
    iptables -t mangle -X
}

# Function to set default policies (block all)
set_default_policies() {
    iptables -P INPUT DROP
    iptables -P FORWARD DROP
    iptables -P OUTPUT DROP
}

# Function to allow only essential ML ports
allow_essential_ports() {
    # Define allowed ports
    ALLOWED_PORTS=(
        8002    # ML Training Communication
        8003    # ML Training Communication
        8443    # Secure ML Operations
        9443    # TEE Attestation
    )

    # Allow whitelisted ports
    for port in "${ALLOWED_PORTS[@]}"; do
        # Allow incoming connections to our services
        iptables -A INPUT -p tcp --dport $port -j ACCEPT
        # Allow outgoing responses from our services
        iptables -A OUTPUT -p tcp --sport $port -j ACCEPT
        # Allow outgoing connections for client operations
        iptables -A OUTPUT -p tcp --dport $port -j ACCEPT
        # Allow incoming responses to our client requests
        iptables -A INPUT -p tcp --sport $port -j ACCEPT
    done

    # Allow established connections
    iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
    iptables -A OUTPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
}

# Function to persist rules
persist_rules() {
    if command -v iptables-save >/dev/null 2>&1; then
        iptables-save > /etc/iptables/rules.v4
        echo "Rules persisted to /etc/iptables/rules.v4"
    else
        echo "Warning: iptables-save not found, rules not persisted"
    fi
}

# Main execution
main() {
    check_root
    echo "Setting up network lockdown..."
    
    clean_rules
    set_default_policies
    allow_essential_ports
    persist_rules
    
    echo "Network lockdown complete"
    echo "Allowed ports: ${ALLOWED_PORTS[*]}"
}

main 