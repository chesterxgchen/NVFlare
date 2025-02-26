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

# Main execution
main() {
    echo "Starting system security configuration..."
    
    configure_remote_access
    configure_login_security
    harden_system
    configure_tee
    
    echo "Security configuration completed."
}

main 