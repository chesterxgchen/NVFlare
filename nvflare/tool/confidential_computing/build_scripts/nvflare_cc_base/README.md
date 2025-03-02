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
```

## Usage

```bash
# Basic usage
./build_nvflare.sh [OPTIONS]

Options:
  -h, --help            Show this help message
  -s, --size SIZE       Output image size (default: 10G)
  -r, --role ROLE       Build role: ALL, CLIENT, or SERVER (default: ALL)
  -v, --verbose         Show detailed output
  -t, --skip-tests      Skip running tests

Examples:
  # Build default image (ALL components, 10GB)
  ./build_nvflare.sh

  # Build 20GB client-only image
  ./build_nvflare.sh -s 20G -r CLIENT

  # Build server image with verbose output
  ./build_nvflare.sh -r SERVER -v

  # Build without running tests
  ./build_nvflare.sh -t
```

## Image Structure

The built image contains multiple partitions:

1. Root Partition (LUKS encrypted):
   ```
   /opt/nvflare/
   └── venv/           # Python virtual environment
   ```

2. Config Partition (dm-verity):
   ```
   /opt/nvflare/config/
   ├── startup/        # Read-only startup files
   ├── site_conf/      # Site configuration
   └── job_store_key/  # Job store keys (server only)
   ```

3. Dynamic Partition (LUKS encrypted):
   ```
   /opt/nvflare/dynamic/
   ├── workspace/      # Runtime workspace
   ├── logs/          # Log files
   └── job_store/     # Job storage (server only)
   ```

4. Data Partition (unencrypted, client only):
   ```
   /opt/nvflare/data/  # Client data access
   ```

## Role-Specific Components

### Server (Aggregator)
- Job store for FL training jobs
- Job store keys for encryption
- Workspace for aggregation

### Client (Trainer)
- Data directory for model training
- Workspace for local training

### Common Components
- Python environment
- NVFLARE installation
- Logs directory
- Configuration files

## Testing

The build process includes several tests:

1. Partition Tests:
   - Verifies partition labels
   - Checks partition structure
   - Validates role-specific partitions

2. NVFLARE Tests:
   - Validates installation
   - Checks Python environment
   - Tests import functionality

3. Permission Tests:
   - Verifies file ownership
   - Checks directory permissions
   - Validates security settings

Run specific tests:
```bash
# Run all tests
./tests/test_*.sh

# Run specific test
./tests/test_01_partitions.sh
```

## Security Features

- LUKS encryption for sensitive partitions
- dm-verity for read-only integrity
- Role-based access control
- Secure mount options
- Encrypted workspace

## Known Issues

- Python 3.12 may have compatibility issues with some dependencies
- Certain NVFLARE versions may require specific dependency versions
- See version compatibility matrix in script documentation 