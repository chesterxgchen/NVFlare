#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../config/partition.conf"
source "${SCRIPT_DIR}/../config/security.conf"
source "${SCRIPT_DIR}/common/security_hardening.sh"

# Security settings
readonly SECURE_MOUNT_OPTS="nodev,nosuid,noexec,ro"
readonly WORKSPACE_MOUNT_OPTS="nodev,nosuid"
readonly MEMORY_PROTECTION="noexec,nosuid,nodev,private"

# Create working directory
WORK_DIR=$(mktemp -d)
trap 'cleanup_install "$WORK_DIR"' EXIT

# Verify installation environment
verify_secure_environment() {
    # Check secure boot status
    if ! mokutil --sb-state | grep -q "SecureBoot enabled"; then
        error "Secure Boot must be enabled"
    }
    
    # Verify TPM is available and enabled
    if ! tpm2_getcap properties-fixed | grep -q "TPM2_PT_FIXED"; then
        error "TPM 2.0 is required"
    }
    
    # Check CPU security features
    if ! grep -q "sev" /proc/cpuinfo && ! grep -q "tdx" /proc/cpuinfo; then
        error "CPU must support SEV or TDX"
    }
}

# Pre-configure debconf to avoid prompts
cat > "$WORK_DIR/debconf.conf" <<EOF
grub-pc grub2/linux_cmdline string
grub-pc grub2/linux_cmdline_default string quiet
locales locales/locales_to_be_generated multiselect ${LANGUAGE} UTF-8
locales locales/default_environment_locale select ${LANGUAGE}
tzdata tzdata/Areas select $(echo $TIMEZONE | cut -d'/' -f1)
tzdata tzdata/Zones/$(echo $TIMEZONE | cut -d'/' -f1) select $(echo $TIMEZONE | cut -d'/' -f2)
EOF

# Apply debconf settings
debconf-set-selections "$WORK_DIR/debconf.conf"

# Mount ISO
mount -o loop "$ISO_FILE" "$WORK_DIR"

# Install base system with non-interactive mode
DEBIAN_FRONTEND=noninteractive debootstrap \
    --arch=amd64 \
    --include="linux-image-amd64,grub2,sudo,curl,wget,gnupg,cryptsetup,cryptsetup-bin,\
    cryptsetup-initramfs,dmsetup,veritysetup,tpm2-tools,sev-guest-utils,tdx-guest-tools" \
    --keyring=/usr/share/keyrings/ubuntu-archive-keyring.gpg \
    "$OS_CODENAME" \
    "$ROOT_MOUNT"

# Configure system non-interactively
chroot "$ROOT_MOUNT" /bin/bash -c "
    export DEBIAN_FRONTEND=noninteractive
    
    # Set timezone without prompts
    ln -sf /usr/share/zoneinfo/$TIMEZONE /etc/localtime
    echo '$TIMEZONE' > /etc/timezone
    dpkg-reconfigure -f noninteractive tzdata
    
    # Configure locale without prompts
    echo '$LANGUAGE UTF-8' > /etc/locale.gen
    locale-gen --no-purge
    update-locale LANG=$LANGUAGE LC_ALL=$LANGUAGE
    
    # Create CC user and group non-interactively
    groupadd -r $CC_GROUP
    useradd -r -g $CC_GROUP -d $CC_USER_HOME -m -s /bin/bash $CC_USER
    
    # Configure grub without prompts
    echo 'GRUB_TIMEOUT=0' >> /etc/default/grub
    echo 'GRUB_CMDLINE_LINUX_DEFAULT=\"quiet\"' >> /etc/default/grub
    update-grub
    
    # Disable unnecessary services without prompts
    for service in ${SYSTEM_SERVICES_DISABLE[@]}; do
        systemctl disable \$service
        systemctl mask \$service
    done
    
    # Disable swap without prompts
    swapoff -a
    sed -i '/swap/d' /etc/fstab

    # Disable unnecessary kernel modules
    for module in ${KERNEL_MODULES_DISABLE[@]}; do
        echo \"blacklist \$module\" >> /etc/modprobe.d/blacklist-cc.conf
    done

    # Configure secure directories
    for dir_config in ${SECURE_DIRS[@]}; do
        IFS=':' read -r dir owner group mode <<< \"\$dir_config\"
        mkdir -p \"\$dir\"
        chown \"\$owner\":\"\$group\" \"\$dir\"
        chmod \"\$mode\" \"\$dir\"
    done

    # Configure network security
    if [ \"$DISABLE_SSH\" = true ]; then
        systemctl disable ssh
        systemctl mask ssh
    fi

    # Configure kernel parameters for CC
    cat > /etc/sysctl.d/99-cc-secure.conf <<EOF
# TEE-specific settings
memory_encryption = on
cc.tee.enabled = 1
cc.tee.measurement_enforce = 1
EOF
"

# Unmount ISO
umount "$WORK_DIR"

# Setup secure boot keys
setup_secure_boot() {
    local efi_dir="${ROOT_MOUNT}/boot/efi/EFI/ubuntu"
    
    # Generate secure boot keys
    openssl req -new -x509 -newkey rsa:2048 -keyout PK.key -out PK.crt -days 3650 -subj "/CN=Platform Key"
    openssl req -new -x509 -newkey rsa:2048 -keyout KEK.key -out KEK.crt -days 3650 -subj "/CN=Key Exchange Key"
    openssl req -new -x509 -newkey rsa:2048 -keyout db.key -out db.crt -days 3650 -subj "/CN=Signature Database"
    
    # Sign GRUB and kernel
    sbsign --key db.key --cert db.crt "${efi_dir}/grubx64.efi"
    sbsign --key db.key --cert db.crt "${ROOT_MOUNT}/boot/vmlinuz-*"
}

# Integrate with partition security
integrate_security() {
    # Add mount options to fstab
    sed -i "s|^\(/dev/mapper/root_crypt.*\)|\1,${SECURE_MOUNT_OPTS}|" "${ROOT_MOUNT}/etc/fstab"
    sed -i "s|^\(/dev/mapper/workspace_crypt.*\)|\1,${WORKSPACE_MOUNT_OPTS}|" "${ROOT_MOUNT}/etc/fstab"
    
    # Configure tmpfs security
    echo "tmpfs ${TEE_MEMORY_PATH} tmpfs ${MEMORY_PROTECTION},size=${TEE_MEMORY_SIZE} 0 0" >> "${ROOT_MOUNT}/etc/fstab"
    
    # Setup SELinux contexts for partitions
    chroot "$ROOT_MOUNT" /bin/bash -c "
        semanage fcontext -a -t cc_exec_t '/opt/cc(/.*)?'
        semanage fcontext -a -t tee_memory_t '${TEE_MEMORY_PATH}(/.*)?'
        restorecon -R /opt/cc ${TEE_MEMORY_PATH}
    "
}

# Main installation flow
main() {
    verify_secure_environment
    setup_secure_boot
    integrate_security
    verify_installation
}

# Run installation
main 