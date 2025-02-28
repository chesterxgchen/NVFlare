# System Hardening User Guide

This guide explains how to use the system hardening scripts to secure your NVFLARE deployment.

## Overview

The system hardening tools provide:
- Security configuration validation
- Network port hardening
- System service lockdown
- Logging and monitoring setup

## Prerequisites

- Ubuntu 20.04 or later
- Root/sudo access
- Basic understanding of Linux security concepts

## Quick Start

1. First, review and customize security configuration:
```bash
# Review default settings
cat security.conf

# Make any needed adjustments
sudo vim security.conf
```

2. Run the security validation:
```bash
# Check current security status
sudo ./validate_security.sh
```

3. Apply security hardening:
```bash
# Apply all security configurations
sudo ./secure_build.sh
```

## Configuration Files

### security.conf

Main configuration file that controls:

- Allowed network ports:
```bash
ALLOWED_PORTS=(
    "nvflare_fl:8002:tcp:FL training communication"
    "nvflare_fed:8003:tcp:Federation communication"
    "nvflare_admin:8004:tcp:Admin API"
    "nvflare_metrics:8005:tcp:Metrics endpoint"
    "nvflare_proxy:8006:tcp:Proxy service"
)
```

- Port ranges for dynamic allocation:
```bash
ALLOWED_PORT_RANGES=(
    "nvflare_dynamic:9000:9100:tcp:Dynamic port range for FL training"
)
```

- Network security settings:
```bash
DISABLE_SSH=true      # Disable SSH access
SSH_BACKUP=true      # Backup SSH keys before removal
```

- System paths and encryption:
```bash
SYSTEM_PATHS="/etc/nvflare,/etc/ssl/nvflare"
ENCRYPT_RW_PATHS="/workspace/models/*.pt,/workspace/checkpoints/*.ckpt"
```

## Scripts

### validate_security.sh

Validates security configuration:
```bash
sudo ./validate_security.sh
```

Checks:
- Port configurations
- Network isolation
- Security logging
- System service status
- File permissions
- Encryption settings

### secure_build.sh

Applies security hardening:
```bash
sudo ./secure_build.sh
```

Actions:
- Configures firewall rules
- Sets up port restrictions
- Disables unnecessary services
- Configures system logging
- Sets up encryption
- Applies file permissions

## Common Tasks

### Adding New Allowed Ports

1. Edit security.conf:
```bash
ALLOWED_PORTS=(
    # Existing ports...
    "new_service:8007:tcp:New service description"
)
```

2. Validate changes:
```bash
sudo ./validate_security.sh
```

3. Apply changes:
```bash
sudo ./secure_build.sh
```

### Modifying Port Ranges

1. Edit security.conf:
```bash
ALLOWED_PORT_RANGES=(
    "custom_range:10000:10100:tcp:Custom port range"
)
```

2. Apply and validate changes as above

### Troubleshooting

1. Check validation errors:
```bash
sudo ./validate_security.sh
```

2. Review logs:
```bash
sudo tail -f /var/log/iptables.log
```

3. Check service status:
```bash
sudo systemctl status nvflare-*
```

#### Common Issues and Solutions

1. Port Access Issues:
```bash
# Problem: Service can't connect
# Check if port is actually open
sudo netstat -tulpn | grep <port>

# Check firewall rules
sudo iptables -L -n | grep <port>

# Test port connectivity
nc -zv localhost <port>

# Check service logs
sudo journalctl -u nvflare-* | grep <port>
```

2. Firewall Issues:
```bash
# Problem: Firewall blocking legitimate traffic
# Check current rules
sudo iptables-save

# Check connection tracking
sudo conntrack -L

# Monitor dropped packets
sudo tcpdump -i any 'tcp[tcpflags] & (tcp-rst|tcp-syn) != 0'
```

3. Encryption Issues:
```bash
# Problem: Can't access encrypted paths
# Check mount status
sudo mount | grep workspace

# Check dm-crypt status
sudo dmsetup status

# Verify kernel modules
lsmod | grep -E 'dm_crypt|aes|xts'
```

5. Partition Issues:
```bash
# Problem: Can't mount encrypted partitions
# Check partition status
sudo fdisk -l
sudo cryptsetup status

# Verify partition integrity
sudo fsck /dev/mapper/nvflare_*

# Check partition mounts
sudo lsblk -f
sudo findmnt | grep nvflare
```

6. Permission Issues:
```bash
# Problem: Access denied to workspace
# Check ACLs
sudo getfacl /mnt/nvflare/workspace

# Check SELinux/AppArmor
sudo aa-status
sudo sestatus

# Fix permissions
sudo chmod -R 750 /mnt/nvflare/workspace
sudo chown -R nvflare:nvflare /mnt/nvflare/workspace
```

7. System Service Issues:
```bash
# Problem: NVFLARE services not starting
# Check systemd status
sudo systemctl status nvflare-partitions

# Check service dependencies
sudo systemctl list-dependencies nvflare-partitions

# View service logs
sudo journalctl -xeu nvflare-partitions
```

8. Memory/Swap Issues:
```bash
# Problem: Out of memory with disabled swap
# Check memory usage
free -h
sudo slabtop

# Monitor memory
sudo vmstat 1
sudo dmesg | grep -i "out of memory"
```

## Best Practices

1. Always review security.conf before deployment
2. Run validation before and after changes
3. Regularly monitor security logs
4. Maintain minimal set of open ports
5. Use port ranges judiciously

## Security Notes

- Default configuration assumes CVM (Confidential VM) environment
- All ports are closed by default (deny-all policy)
- SSH access is disabled by default
- All sensitive paths are encrypted
- System logging is enabled for auditing
