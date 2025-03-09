#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../config/hardening.conf"

# Create systemd service for mount encryption
cat > /etc/systemd/system/nvflare-mount.service <<EOF
[Unit]
Description=NVFLARE Mount Encryption
Before=nvflare.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/opt/nvflare/scripts/mount_encrypt.sh
ExecStop=/opt/nvflare/scripts/mount_cleanup.sh

[Install]
WantedBy=multi-user.target
EOF

systemctl enable nvflare-mount 