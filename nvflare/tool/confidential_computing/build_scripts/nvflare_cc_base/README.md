# Stage 2: Confidential Computing Base Image Builder

This guide explains how to build the NVFLARE Confidential Computing image with Python environment.

## Prerequisites

- Stage 1 base image (nvcc_image.qcow2)
- Python 3.9-3.12
- Required packages:
  - virt-customize
  - python3-venv
  - guestmount
  - qemu-utils

## Configuration

Edit `config/nvflare.conf`:
```bash
# Adjust Python version
PYTHON_VERSION="3.9"   # Supports 3.9 to 3.12

# Update paths
VENV_PATH="/opt/nvflare/venv"
NVFLARE_HOME="/opt/nvflare"

# NVFLARE settings
NVFLARE_VERSION="2.6.0"
NVFLARE_USER="nvflare"
NVFLARE_GROUP="nvflare"

### Project Configuration

Add NVFLARE project configuration in `config/project.yml`:
```yaml
# Example project.yml
name: example_project
description: Example FL project

participants:
  - name: server1
    type: server
    org: nvidia
  - name: client1
    type: client
    org: org1
  - name: client2
    type: client
    org: org2
```

### Application Requirements

Add application-specific Python packages to `