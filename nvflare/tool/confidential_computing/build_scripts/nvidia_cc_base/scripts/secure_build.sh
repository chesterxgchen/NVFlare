#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common/common.sh"
source "${SCRIPT_DIR}/../config/security.conf"

# Base security hardening
setup_base_security() {
    # Disable SSH
    systemctl disable ssh
    systemctl stop ssh

    # Lock down ports
    iptables -P INPUT DROP
    iptables -P OUTPUT DROP
    iptables -P FORWARD DROP

    # Allow only essential services
    iptables -A INPUT -i lo -j ACCEPT
    iptables -A OUTPUT -o lo -j ACCEPT
    iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
    iptables -A OUTPUT -m state --state ESTABLISHED,RELATED -j ACCEPT

    # Save iptables rules
    iptables-save > /etc/iptables/rules.v4

    # Secure kernel parameters
    cat > /etc/sysctl.d/99-security.conf << EOF
kernel.randomize_va_space = 2
kernel.kptr_restrict = 2
kernel.dmesg_restrict = 1
kernel.perf_event_paranoid = 3
kernel.yama.ptrace_scope = 2
fs.protected_hardlinks = 1
fs.protected_symlinks = 1
EOF
    sysctl -p /etc/sysctl.d/99-security.conf

    # Secure mount options
    sed -i 's/defaults/defaults,nodev,nosuid,noexec/' /etc/fstab
}

# TPM initialization
setup_tpm() {
    # Clear TPM
    tpm2_clear -c p

    # Setup PCRs for measurements
    for pcr_config in "${PCR_ALLOCATIONS[@]}"; do
        IFS=':' read -r pcr_num purpose <<< "$pcr_config"
        tpm2_pcrreset "$pcr_num"
    done

    # Initialize NVRAM indices
    for nvram_config in "${NVRAM_INDICES[@]}"; do
        IFS=':' read -r index purpose size <<< "$nvram_config"
        tpm2_nvdefine -C o -s "$size" -a "ownerread|ownerwrite" "$index"
    done
}

# Secure boot configuration
setup_secure_boot() {
    # Generate secure boot keys
    for key_config in "${BOOT_SIGNING_KEYS[@]}"; do
        IFS=':' read -r type key cert <<< "$key_config"
        openssl req -new -x509 -sha256 -newkey rsa:2048 -nodes \
            -keyout "/etc/secureboot/keys/$key" \
            -out "/etc/secureboot/certs/$cert" \
            -subj "/CN=$type Key for NVFLARE CC/"
    done

    # Enroll keys
    sbsiglist --owner 77fa9abd-0359-4d32-bd60-28f4e78f784b \
        --type x509 --output PK.esl /etc/secureboot/certs/platform.crt
    sbsiglist --owner 77fa9abd-0359-4d32-bd60-28f4e78f784b \
        --type x509 --output KEK.esl /etc/secureboot/certs/key-exchange.crt
    sbsiglist --owner 77fa9abd-0359-4d32-bd60-28f4e78f784b \
        --type x509 --output db.esl /etc/secureboot/certs/signature.crt

    # Sign and enroll
    sbvarsign --key /etc/secureboot/keys/platform.key \
        --cert /etc/secureboot/certs/platform.crt \
        --output PK.auth PK PK.esl
    sbvarsign --key /etc/secureboot/keys/platform.key \
        --cert /etc/secureboot/certs/platform.crt \
        --output KEK.auth KEK KEK.esl
    sbvarsign --key /etc/secureboot/keys/key-exchange.key \
        --cert /etc/secureboot/certs/key-exchange.crt \
        --output db.auth db db.esl

    # Install variables
    efi-updatevar -f PK.auth PK
    efi-updatevar -f KEK.auth KEK
    efi-updatevar -f db.auth db
}

# Main build function
main() {
    log "Starting base security hardening..."

    # Basic security setup
    setup_base_security

    # TPM setup
    setup_tpm

    # Secure boot setup
    setup_secure_boot

    log "Base security hardening completed"
}

main "$@" 