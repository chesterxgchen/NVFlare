# Load configuration
CONFIG_FILE="/etc/nvflare/security.conf"

# Default values
FL_PORTS="8002,8003"
ALLOWED_NETWORKS=""
MAX_CONNECTIONS_FL=20
MAX_CONNECTIONS_ADMIN=5
RATE_LIMIT="100/minute"

# Load custom config if exists
if [ -f "$CONFIG_FILE" ]; then
    source "$CONFIG_FILE"
fi

setup_network_security() {
    # 1. Port Management
    configure_ports() {
        # Configure FL ports from config
        IFS=',' read -ra PORTS <<< "$FL_PORTS"
        for port in "${PORTS[@]}"; do
            iptables -A INPUT -p tcp --dport "$port" -j ACCEPT
        done
    }

    # 2. Network Isolation
    setup_network_isolation() {
        # Allow loopback
        iptables -A INPUT -i lo -j ACCEPT
        
        # Configure allowed networks from config
        if [ ! -z "$ALLOWED_NETWORKS" ]; then
            IFS=',' read -ra NETWORKS <<< "$ALLOWED_NETWORKS"
            for network in "${NETWORKS[@]}"; do
                iptables -A INPUT -s "$network" -j ACCEPT
            done
        fi
    }

    # 3. Traffic Control
    setup_traffic_control() {
        # Allow established connections only for FL ports
        for port in "${PORTS[@]}"; do
            iptables -A INPUT -p tcp --dport "$port" -m state --state ESTABLISHED,RELATED -j ACCEPT
        done
    }
} 