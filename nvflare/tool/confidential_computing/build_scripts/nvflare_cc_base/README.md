# Stage 2: Confidential Computing Base Image Builder

This guide explains how to build the Confidential Computing base image with Python environment.

## Prerequisites

- Stage 1 base image (nvcc_image.qcow2)
- Python 3.8+
- Required packages:
  - qemu-img
  - virt-customize
  - python3-venv

## Configuration

Edit `config/cc_image.conf`:
```bash
# Adjust Python version
PYTHON_VERSION="3.8"

# Update paths
VENV_PATH="/opt/venv"
APP_HOME="/opt/app"

# Modify Python dependencies
PYTHON_DEPS=(
    "numpy>=1.21.0"
    "cryptography>=3.3.2"
)
```

## Usage

1. Basic build:
```bash
sudo ./build_base.sh
```

2. Build with custom size:
```bash
sudo ./build_base.sh -s 20G
```

## Image Resizing

The image can be resized using the -s option:
```bash
# Resize to 20GB
sudo ./build_base.sh -s 20G

# Use default size (10GB)
sudo ./build_base.sh
```

## Testing

1. Test installation:
```bash
sudo ./tests/test_image.sh
```

2. Test resizing:
```bash
sudo ./tests/test_resize.sh
```

## Output

- Base image: `cc_base_image.qcow2`
- Default size: 10GB (configurable) 