# Stage 3: NVFLARE CC Hardened Image Builder

This guide explains how to build the hardened NVFLARE Confidential Computing image.

## Prerequisites

- Stage 2 NVFLARE base image (nvflare_cc_image.qcow2)
- System requirements:
  - ufw (firewall)
  - auditd (audit daemon)
  - cryptsetup
  - systemd

## Configuration

1. System Hardening (`config/hardening.conf`):
```bash
# Configure disabled services
DISABLE_SERVICES=(
    "ssh"
    "telnet"
    "ftp"
)

# Configure allowed ports
ALLOWED_PORTS=(
    "8002:tcp:FL training"
    "8003:tcp:Federation"
)
```

2. Mount Configuration:
```bash
# Configure mount points
INPUT_MOUNT="/mnt/data/nvflare/input"
OUTPUT_MOUNT="/mnt/data/nvflare/output"

# Optional encryption
LUKS_KEYFILE="/etc/nvflare/keys/luks.key"
```

## Usage

1. Build hardened image:
```bash
sudo ./build_hardened.sh
```

2. Test hardening:
```bash
sudo ./tests/test_hardened.sh
```

## Security Features

1. System Hardening:
   - Disabled unnecessary services
   - Configured firewall
   - Enabled audit logging

2. Mount Security:
   - Optional LUKS encryption for input/output
   - Separate mount points for input/output
   - Mount point access control

3. Network Security:
   - Whitelisted ports only
   - UFW firewall rules
   - Service isolation

## Output

- Hardened image: `nvflare_cc_image_hardened.qcow2`
- Location: Current directory 