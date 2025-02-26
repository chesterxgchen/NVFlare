#!/bin/bash

# Function to monitor connections
monitor_connections() {
    echo "Monitoring connections on ML ports..."
    netstat -ant | grep -E ':8002|:8003|:8443|:9443'
}

# Function to check for violations
check_violations() {
    # Check for unauthorized ports
    unauthorized=$(netstat -ant | grep "LISTEN" | grep -vE ':8002|:8003|:8443|:9443')
    if [ ! -z "$unauthorized" ]; then
        echo "WARNING: Unauthorized listening ports detected:"
        echo "$unauthorized"
    fi
}

# Function to monitor traffic patterns
monitor_traffic() {
    echo "Traffic statistics for ML ports:"
    iptables -nvL | grep -E '8002|8003|8443|9443'
}

# Main monitoring loop
while true; do
    clear
    echo "=== Network Security Monitor ==="
    echo "Time: $(date)"
    echo "------------------------"
    
    monitor_connections
    echo "------------------------"
    check_violations
    echo "------------------------"
    monitor_traffic
    
    sleep 10
done 