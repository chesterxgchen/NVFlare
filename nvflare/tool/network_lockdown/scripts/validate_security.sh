#!/bin/bash

# Function to validate IPTables rules
validate_rules() {
    echo "Validating IPTables rules..."
    
    # Check default policies
    if ! iptables -L | grep -q "Chain INPUT (policy DROP)"; then
        echo "ERROR: INPUT chain policy not set to DROP"
        return 1
    fi
    
    # Check ML ports
    for port in 8002 8003 8443 9443; do
        if ! iptables -L | grep -q "tcp dpt:$port"; then
            echo "ERROR: Rule missing for port $port"
            return 1
        fi
    done
    
    # Check rate limiting
    if ! iptables -L | grep -q "limit"; then
        echo "ERROR: Rate limiting rules not found"
        return 1
    fi
    
    echo "IPTables validation passed"
    return 0
}

# Function to test network security
test_security() {
    echo "Testing network security..."
    
    # Test blocked ports
    for port in 22 80 443; do
        if nc -zv localhost $port 2>/dev/null; then
            echo "ERROR: Port $port should be blocked"
            return 1
        fi
    done
    
    # Test allowed ports
    for port in 8002 8003 8443 9443; do
        if ! nc -zv localhost $port 2>/dev/null; then
            echo "ERROR: Port $port should be accessible"
            return 1
        fi
    done
    
    echo "Security tests passed"
    return 0
}

# Main validation
validate_rules && test_security 