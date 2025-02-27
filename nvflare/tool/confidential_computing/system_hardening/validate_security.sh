#!/bin/bash

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

check_ports() {
    echo "Checking port configuration..."
    
    # Check configured ports
    for port_config in "${ALLOWED_PORTS[@]}"; do
        IFS=':' read -r name port protocol description <<< "$port_config"
        nc -zv localhost "$port" &>/dev/null && \
            echo -e "${GREEN}✓ Port $port ($name) open${NC}" || \
            echo -e "${RED}✗ Port $port ($name) closed${NC}"
    done
    
    # Check port ranges
    for range_config in "${ALLOWED_PORT_RANGES[@]}"; do
        IFS=':' read -r name start end protocol description <<< "$range_config"
        echo "Checking port range $name ($start-$end)..."
        for port in $(seq "$start" "$end"); do
            if nc -zv localhost "$port" &>/dev/null; then
                echo -e "${GREEN}✓ Port $port in range $name open${NC}"
            fi
        done
    done
    
    # Check blocked ports
    # Check commonly blocked ports
    BLOCKED_PORTS=(
        "22:SSH"
        "23:Telnet"
        "3389:RDP"
    )
    
    for blocked in "${BLOCKED_PORTS[@]}"; do
        IFS=':' read -r port service <<< "$blocked"
        nc -zv localhost "$port" &>/dev/null && \
            echo -e "${RED}✗ $service port $port open${NC}" || \
            echo -e "${GREEN}✓ $service port $port blocked${NC}"
    done
}

check_network_isolation() {
    echo "Checking network isolation..."
    
    # Check iptables rules
    iptables -L | grep -q "DROP" && echo -e "${GREEN}✓ Default DROP policy${NC}" || echo -e "${RED}✗ Missing DROP policy${NC}"
    iptables -L | grep -q "fl_conn" && echo -e "${GREEN}✓ Rate limiting active${NC}" || echo -e "${RED}✗ Missing rate limiting${NC}"
}

check_logging() {
    echo "Checking security logging..."
    
    # Check log files
    [ -f "/var/log/iptables.log" ] && echo -e "${GREEN}✓ IPTables logging enabled${NC}" || echo -e "${RED}✗ Missing IPTables logs${NC}"
}

# Validate port configurations
validate_ports() {
    log "Validating port configurations..."

    # Check individual ports
    for port_config in "${ALLOWED_PORTS[@]}"; do
        IFS=':' read -r name port protocol description <<< "$port_config"
        
        # Validate port number
        if ! [[ "$port" =~ ^[0-9]+$ ]] || [ "$port" -lt 1024 ] || [ "$port" -gt 65535 ]; then
            error "Invalid port number for $name: $port"
        fi
        
        # Validate protocol
        if [[ ! "$protocol" =~ ^(tcp|udp)$ ]]; then
            error "Invalid protocol for $name: $protocol"
        fi
        
        # Check if port is properly restricted in firewall
        if ! check_port_firewall "$port" "$protocol"; then
            error "Port $port ($protocol) is not properly restricted in firewall"
        fi
    done

    # Check port ranges
    for range_config in "${ALLOWED_PORT_RANGES[@]}"; do
        IFS=':' read -r name start end protocol description <<< "$range_config"
        
        # Validate range numbers
        if ! [[ "$start" =~ ^[0-9]+$ ]] || ! [[ "$end" =~ ^[0-9]+$ ]] || 
           [ "$start" -lt 1024 ] || [ "$end" -gt 65535 ] || [ "$start" -ge "$end" ]; then
            error "Invalid port range for $name: $start-$end"
        fi
        
        # Validate protocol
        if [[ ! "$protocol" =~ ^(tcp|udp)$ ]]; then
            error "Invalid protocol for $name: $protocol"
        fi
        
        # Check if port range is properly restricted in firewall
        if ! check_port_range_firewall "$start" "$end" "$protocol"; then
            error "Port range $start-$end ($protocol) is not properly restricted in firewall"
        fi
    done
}

# Check if port is properly configured in firewall
check_port_firewall() {
    local port="$1"
    local protocol="$2"
    
    # Check iptables rules
    if ! iptables -L INPUT -n | grep -q "^ACCEPT.*$protocol.*dpt:$port"; then
        return 1
    fi
    
    return 0
}

# Check if port range is properly configured in firewall
check_port_range_firewall() {
    local start="$1"
    local end="$2"
    local protocol="$3"
    
    # Check iptables rules for port range
    if ! iptables -L INPUT -n | grep -q "^ACCEPT.*$protocol.*dpts:$start:$end"; then
        return 1
    fi
    
    return 0
}

main() {
    echo "Starting security validation..."
    check_ports
    check_network_isolation
    check_logging
}

main 