#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common/common.sh"
source "${SCRIPT_DIR}/../config/qemu.conf"
source "${SCRIPT_DIR}/../config/tee.conf"

log "Setting up QEMU/virtualization..."

# Install QEMU packages
apt-get install -y \
    qemu-kvm \
    libvirt-daemon-system \
    libvirt-clients \
    bridge-utils \
    virt-manager

# Configure QEMU for confidential computing
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
source /etc/cc/qemu/tee.conf

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

# Create VM configuration
VM_XML=$(cat << END
<domain type='kvm'>
  <name>${VM_NAME}</name>
  <memory unit='KiB'>${VM_MEMORY_SIZE}</memory>
  <vcpu placement='static'>${VM_CPUS}</vcpu>
  <os>
    <type arch='x86_64' machine='q35'>hvm</type>
    <loader readonly='yes' type='pflash'>/usr/share/OVMF/OVMF_CODE.fd</loader>
  </os>
  <features>
    <acpi/>
    <apic/>
  </features>
  <cpu mode='host-passthrough'/>
  $(if [ "$TEE_TYPE" = "sev-snp" ]; then
    echo "<launchSecurity type='sev'>
      <policy>${TEE_POLICY}</policy>
      <cbitpos>47</cbitpos>
      <reducedPhysBits>1</reducedPhysBits>
      <dhCert>auto</dhCert>
      <session>auto</session>
    </launchSecurity>"
  elif [ "$TEE_TYPE" = "tdx" ]; then
    echo "<launchSecurity type='tdx'>
      <policy>${TEE_POLICY}</policy>
    </launchSecurity>"
  fi)
  <devices>
    <disk type='file' device='disk'>
      <driver name='qemu' type='qcow2'/>
      <source file='${VM_DISK_PATH}'/>
      <target dev='vda' bus='virtio'/>
    </disk>
  </devices>
</domain>
END
)

# Define VM
echo "$VM_XML" | virsh define /dev/stdin

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