# Load configuration
CONFIG_FILE="/etc/nvflare/security.conf"

# Load required configuration
if [ ! -f "$CONFIG_FILE" ]; then
    echo "Error: Security configuration file $CONFIG_FILE not found"
    exit 1
fi

source "$CONFIG_FILE"

# Set encryption patterns
export NVFLARE_ENCRYPT_RW_PATHS="$ENCRYPT_RW_PATHS"
export NVFLARE_ENCRYPT_WO_PATHS="$ENCRYPT_WO_PATHS"

# System service configuration
configure_services() {
    echo "Configuring system services..."
    
    # Disable SSH if configured
    if [ "$DISABLE_SSH" = true ]; then
        log "Disabling SSH..."
        # Stop and disable SSH
        systemctl stop ssh sshd
        systemctl disable ssh sshd
        # Remove SSH completely
        apt-get remove -y openssh-server openssh-client
        rm -rf /etc/ssh
        # Block SSH port in firewall
        iptables -A INPUT -p tcp --dport 22 -j DROP
        iptables -A OUTPUT -p tcp --dport 22 -j DROP
    fi
}

setup_network_security() {
    # 1. Port Management
    configure_ports() {
        # Configure FL and monitoring ports from config
        IFS=',' read -ra FL_PORT_LIST <<< "$FL_PORTS"
        for port in "${FL_PORT_LIST[@]}"; do
            iptables -A INPUT -p tcp --dport "$port" -j ACCEPT
        done
        
        # Block SSH ports explicitly
        iptables -A INPUT -p tcp --dport 22 -j DROP   # SSH
        iptables -A INPUT -p tcp --dport 2222 -j DROP # Alternative SSH
        
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

    # Configure path permissions
    configure_paths() {
        # Set up system paths
        IFS=',' read -ra SYS_PATHS <<< "$SYSTEM_PATHS"
        for path in "${SYS_PATHS[@]}"; do
            chmod 644 "$path"
            register_system_path "$path"
        done

        # Set up tmpfs paths
        IFS=',' read -ra TMP_PATHS <<< "$TMPFS_PATHS"
        for path in "${TMP_PATHS[@]}"; do
            mkdir -p "$path"
            chmod 700 "$path"
            register_tmpfs_path "$path"
        done
    }
} 