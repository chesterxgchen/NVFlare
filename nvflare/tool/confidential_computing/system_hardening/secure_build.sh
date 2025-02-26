#!/bin/bash

# System Hardening Script for NVFlare TEE Environment

# 1. Remote Access Control
configure_remote_access() {
    echo "Configuring remote access restrictions..."
    
    # Disable SSH service
    systemctl disable --now ssh
    
    # Block remote access ports
    iptables -A INPUT -p tcp --dport 22 -j DROP  # SSH
    iptables -A INPUT -p tcp --dport 23 -j DROP  # Telnet
    iptables -A INPUT -p tcp --dport 3389 -j DROP  # RDP
    
    # Block remote debugging
    iptables -A INPUT -p tcp --dport 1234 -j DROP  # GDB
    iptables -A INPUT -p tcp --dport 5005 -j DROP  # JDWP
    
    # Save iptables rules
    iptables-save > /etc/iptables/rules.v4
}

# 2. Login Security
configure_login_security() {
    echo "Configuring login security..."
    
    # Configure PAM with TEE requirements
    cat >> /etc/pam.d/common-auth << EOF
auth required pam_tee.so
EOF
    
    # Restrict privileged commands
    chmod 0700 /bin/su
    chmod 0700 /usr/bin/sudo
    
    # Create TEE-specific group
    groupadd tee_users
}

# 3. System Hardening
harden_system() {
    echo "Applying system hardening..."
    
    # Disable core dumps
    echo "* hard core 0" >> /etc/security/limits.conf
    
    # Secure sysctl settings
    cat >> /etc/sysctl.conf << EOF
kernel.core_pattern=|/bin/false
kernel.core_uses_pid=0
kernel.dmesg_restrict=1
kernel.kptr_restrict=2
kernel.sysrq=0
EOF
    
    # Apply sysctl changes
    sysctl -p
    
    # Disable unused services
    systemctl disable telnet
    systemctl disable rsh
    
    # Secure SSH
    sed -i 's/#PermitRootLogin yes/PermitRootLogin no/' /etc/ssh/sshd_config
    
    # File permissions
    chmod 700 /etc/iptables
    chmod 600 /etc/iptables/rules.v4
}

# 4. TEE Integration
configure_tee() {
    echo "Configuring TEE integration..."
    
    # Set up TEE environment
    mkdir -p /etc/tee
    chmod 700 /etc/tee
    
    # Configure TEE attestation
    cat > /etc/tee/attestation.conf << EOF
require_attestation=true
enforce_secure_boot=true
verify_tee_context=true
EOF
}

# Network Security Configuration
setup_network_security() {
    # 1. Port Management
    configure_ports() {
        # Allow only specific FL ports
        iptables -A INPUT -p tcp --dport 8002 -j ACCEPT  # FL communication
        iptables -A INPUT -p tcp --dport 8003 -j ACCEPT  # Admin API
        # Block all other incoming
        iptables -P INPUT DROP
    }

    # 2. Network Isolation
    setup_network_isolation() {
        # Restrict to specific interfaces
        iptables -A INPUT -i lo -j ACCEPT
        iptables -A INPUT -i eth0 -j ACCEPT
        # Drop from other interfaces
        iptables -A INPUT -j DROP
    }

    # 3. Traffic Control
    setup_traffic_control() {
        # Rate limiting
        iptables -A INPUT -p tcp --dport 8002 -m limit --limit 100/minute -j ACCEPT
        # Connection tracking
        iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
    }

    configure_ports
    setup_network_isolation
    setup_traffic_control
}

# Main execution
main() {
    echo "Starting system security configuration..."
    
    configure_remote_access
    configure_login_security
    harden_system
    configure_tee
    setup_network_security
    
    echo "Security configuration completed."
}

main 