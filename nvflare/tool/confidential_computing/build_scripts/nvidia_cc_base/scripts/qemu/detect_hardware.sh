#!/bin/bash

set -e

# Detect NVIDIA GPU
detect_gpu() {
    # Find first NVIDIA GPU
    local gpu_pci=$(lspci | grep -i nvidia | head -n1 | cut -d' ' -f1)
    if [ -z "$gpu_pci" ]; then
        echo "No NVIDIA GPU found"
        return 1
    }

    # Find device path
    local gpu_path=""
    for dev in /dev/nvidia*; do
        if [ -c "$dev" ]; then
            gpu_path="$dev"
            break
        fi
    done

    if [ -z "$gpu_path" ]; then
        echo "No NVIDIA device found"
        return 1
    }

    # Save GPU settings
    cat > "$GPU_SETTINGS_FILE" << EOF
NVIDIA_GPU_PATH="$gpu_path"
NVIDIA_GPU_PCI="$gpu_pci"
EOF
}

# Detect Network
detect_network() {
    # Find available bridge interface or create one
    local bridge=""
    if ip link show type bridge | grep -q "virbr"; then
        bridge=$(ip link show type bridge | grep "virbr" | head -n1 | cut -d: -f2 | tr -d ' ')
    else
        bridge="virbr0"
    fi

    # Find available IP range
    local subnet="192.168.122"
    while ip route | grep -q "$subnet"; do
        subnet="192.168.$((RANDOM % 255))"
    done

    # Save network settings
    cat > "$NETWORK_SETTINGS_FILE" << EOF
BRIDGE_NAME="$bridge"
NETWORK_MODE="nat"
IP_RANGE_START="$subnet.2"
IP_RANGE_END="$subnet.254"
NETWORK_ADDRESS="$subnet.1"
EOF
}

# Main
main() {
    mkdir -p "$(dirname "$GPU_SETTINGS_FILE")"
    mkdir -p "$(dirname "$NETWORK_SETTINGS_FILE")"

    detect_gpu
    detect_network
}

main "$@" 