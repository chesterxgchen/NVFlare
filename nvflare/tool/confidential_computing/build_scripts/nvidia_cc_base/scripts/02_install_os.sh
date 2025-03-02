#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../config/partition.conf"
source "${SCRIPT_DIR}/../config/security.conf"

# Create working directory
WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

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
    --include="linux-image-amd64,grub2,sudo,curl,wget,gnupg,cryptsetup,cryptsetup-bin,cryptsetup-initramfs,dmsetup,veritysetup" \
    --no-check-gpg \
    "$OS_CODENAME" \
    "$ROOT_MOUNT" \
    "$WORK_DIR/ubuntu"

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
kernel.modules_disabled = 1
kernel.randomize_va_space = 2
kernel.kptr_restrict = 2
kernel.dmesg_restrict = 1
EOF
"

# Unmount ISO
umount "$WORK_DIR" 