#!/bin/bash

# Mock device data
mock_device_data() {
    cat > "$1" <<EOF
NAME   SIZE MODEL       MOUNTPOINT
nvme0n1 512G Samsung_PM9A1
├─nvme0n1p1 512M       /boot/efi
├─nvme0n1p2 511.5G     /
nvme1n1 1T Samsung_PM9A1
sda    256G Samsung_SSD
sdb    128G Kingston_SSD /mnt/data
sdc    32G  USB_Drive
EOF
}

# Mock lsblk command
mock_lsblk() {
    local device="$1"
    local option="$2"
    
    case "$device" in
        "/dev/nvme0n1")
            echo "512G Samsung_PM9A1 /"
            ;;
        "/dev/nvme1n1")
            echo "1T Samsung_PM9A1"
            ;;
        "/dev/sda")
            echo "256G Samsung_SSD"
            ;;
        "/dev/sdb")
            echo "128G Kingston_SSD /mnt/data"
            ;;
        "/dev/sdc")
            echo "32G USB_Drive"
            ;;
    esac
} 