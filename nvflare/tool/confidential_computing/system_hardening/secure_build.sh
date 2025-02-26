# Load configuration
CONFIG_FILE="/etc/nvflare/security.conf"

# Load required configuration
if [ ! -f "$CONFIG_FILE" ]; then
    echo "Error: Security configuration file $CONFIG_FILE not found"
    exit 1
fi

source "$CONFIG_FILE"

setup_network_security() {
    # 1. Port Management
    configure_ports() {
        # Configure FL and monitoring ports from config
        IFS=',' read -ra FL_PORT_LIST <<< "$FL_PORTS"
        for port in "${FL_PORT_LIST[@]}"; do
            iptables -A INPUT -p tcp --dport "$port" -j ACCEPT
        done
        
        # Configure monitoring ports if monitoring network is set
        if [ ! -z "$MONITOR_NETWORK" ]; then
            IFS=',' read -ra MONITOR_PORT_LIST <<< "$MONITOR_PORTS"
            for port_spec in "${MONITOR_PORT_LIST[@]}"; do
                port="${port_spec%:*}"
                proto="${port_spec#*:}"
                iptables -A INPUT -p "$proto" -s "$MONITOR_NETWORK" --dport "$port" -j ACCEPT
            done
        fi
        
        # Configure attestation service ports
        if [ ! -z "$ATTESTATION_NETWORKS" ]; then
            IFS=',' read -ra ATTESTATION_PORT_LIST <<< "$ATTESTATION_PORTS"
            for port_spec in "${ATTESTATION_PORT_LIST[@]}"; do
                # Parse port:protocol:vendor format
                port="${port_spec%%:*}"
                proto="${port_spec#*:}"; proto="${proto%%:*}"
                vendor="${port_spec##*:}"
                
                # Apply rules for each attestation network
                IFS=',' read -ra ATT_NETWORKS <<< "$ATTESTATION_NETWORKS"
                for network in "${ATT_NETWORKS[@]}"; do
                    iptables -A INPUT -p "$proto" -s "$network" --dport "$port" \
                            -m comment --comment "Attestation-${vendor}" -j ACCEPT
                done
            done
        fi
        
        # Block all other incoming
        iptables -P INPUT DROP
    }

    # 2. Network Isolation
    setup_network_isolation() {
        # Allow monitoring from specific networks only
        iptables -A INPUT -p tcp -s "$MONITOR_NETWORK" --dport 9090 -j ACCEPT
        iptables -A INPUT -p tcp -s "$MONITOR_NETWORK" --dport 9102 -j ACCEPT
        
        # Allow loopback
        iptables -A INPUT -i lo -j ACCEPT
    }

    # 3. Traffic Control
    setup_traffic_control() {
        # Allow established connections only for FL ports
        for port in "${PORTS[@]}"; do
            iptables -A INPUT -p tcp --dport "$port" -m state --state ESTABLISHED,RELATED -j ACCEPT
        done
    }
} 