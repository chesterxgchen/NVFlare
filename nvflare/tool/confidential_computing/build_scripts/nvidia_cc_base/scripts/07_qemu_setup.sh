#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common/common.sh"
source "${SCRIPT_DIR}/../config/qemu.conf"

log "Setting up QEMU/virtualization..."

# Install QEMU packages
apt-get install -y \
    qemu-kvm \
    libvirt-daemon-system \
    libvirt-clients \
    bridge-utils \
    virt-manager

# Configure QEMU for confidential computing
mkdir -p "${VM_TEMPLATE_DIR}"
cp "${SCRIPT_DIR}/qemu/templates/"*.xml "${VM_TEMPLATE_DIR}/"

# Detect hardware settings
"${SCRIPT_DIR}/qemu/detect_hardware.sh"

# Source detected settings
source "$GPU_SETTINGS_FILE"
source "$NETWORK_SETTINGS_FILE"

cat > "/etc/libvirt/qemu.conf" << EOF
# QEMU configuration
security_driver = "selinux"
user = "root"
group = "root"
dynamic_ownership = 1
remember_owner = 1
cgroup_device_acl = [
    "/dev/kvm",
    "/dev/vfio/vfio",
    "${NVIDIA_GPU_PATH}",
]
EOF

# Configure VM creation script
cat > "/usr/local/sbin/setup-cc-vm" << 'EOF'
#!/bin/bash

set -e

# Source configuration
source /etc/cc/qemu/qemu.conf

# Detect TEE type if auto
if [ "$TEE_TYPE" = "auto" ]; then
    if grep -q "sev" /proc/cpuinfo; then
        TEE_TYPE="sev-snp"
    elif grep -q "tdx" /proc/cpuinfo; then
        TEE_TYPE="tdx"
    else
        echo "No TEE support detected"
        exit 1
    fi
fi

# Select template
template="${VM_TEMPLATE_DIR}/${TEE_TYPE}.xml"
if [ ! -f "$template" ]; then
    echo "Template not found: $template"
    exit 1
fi

# Create VM
envsubst < "$template" > "/tmp/vm.xml"
virsh define "/tmp/vm.xml"
rm "/tmp/vm.xml"

echo "VM configured successfully"
EOF

chmod +x "/usr/local/sbin/setup-cc-vm"

# Configure default network
cat > "/etc/libvirt/qemu/networks/default.xml" << EOF
<network>
  <name>default</name>
  <bridge name="${BRIDGE_NAME}"/>
  <forward mode="${NETWORK_MODE}"/>
  <ip address="${NETWORK_ADDRESS}" netmask="255.255.255.0">
    <dhcp>
      <range start="${IP_RANGE_START}" end="${IP_RANGE_END}"/>
    </dhcp>
  </ip>
</network>
EOF

# Enable and start services
systemctl enable --now libvirtd
systemctl enable --now virtlogd

success "QEMU/virtualization setup completed" 