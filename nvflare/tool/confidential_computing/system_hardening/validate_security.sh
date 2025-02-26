#!/bin/bash

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

check_ports() {
    echo "Checking port configuration..."
    
    # Check FL ports
    nc -zv localhost 8002 &>/dev/null && echo -e "${GREEN}✓ Port 8002 (FL) open${NC}" || echo -e "${RED}✗ Port 8002 closed${NC}"
    nc -zv localhost 8003 &>/dev/null && echo -e "${GREEN}✓ Port 8003 (Admin) open${NC}" || echo -e "${RED}✗ Port 8003 closed${NC}"
    
    # Check blocked ports
    nc -zv localhost 22 &>/dev/null && echo -e "${RED}✗ SSH port open${NC}" || echo -e "${GREEN}✓ SSH blocked${NC}"
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

main() {
    echo "Starting security validation..."
    check_ports
    check_network_isolation
    check_logging
}

main 