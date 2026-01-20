# NVFLARE Code Pre-Installer

This tool packages NVFLARE application code for production deployment.

## Overview

The code pre-installer provides two commands:
- `docker` - Build Docker images with pre-installed code
- `local` - Install code locally (for POC or development)

## Quick Start

### Build Docker Image

```bash
# Build Docker image with pre-installed code for site-1
nvflare pre-install docker -j jobs/fedavg -s site-1

# Build with custom base image and tag
nvflare pre-install docker -j jobs/fedavg -s site-1 \
    --base-image nvcr.io/nvidia/nvflare:2.7.0 \
    -t myregistry/nvflare-site1:v1.0
```

### Install Locally

```bash
# Install to POC workspace
nvflare pre-install local -j jobs/fedavg -s site-1 \
    -p /tmp/nvflare/poc/example_project/prod_00/site-1/local/custom

# Install to custom path
nvflare pre-install local -j jobs/fedavg -s site-1 \
    -p /opt/nvflare/site-1/local/custom
```

## Command Reference

### Docker Command

Build Docker image with pre-installed application code.

```bash
nvflare pre-install docker -j <job_folder> -s <site_name> [options]
```

| Option | Description |
|--------|-------------|
| `-j, --job` | Job folder path (required) |
| `-s, --site-name` | Target site name (required) |
| `-t, --tag` | Docker image tag (default: `nvflare-<site>:latest`) |
| `--base-image` | Base Docker image (default: `nvcr.io/nvidia/nvflare:2.7.0`) |
| `--dockerfile` | Path to custom Dockerfile |
| `-p, --install-path` | App code path in container (default: `/workspace/local/custom`) |
| `-ts, --shared-path` | Shared libs path in container (default: `/workspace/local/libs`) |
| `--shared` | Shared library folder to include |
| `-r, --requirements` | Requirements.txt file |

### Local Command

Install application code locally (no Docker).

```bash
nvflare pre-install local -j <job_folder> -s <site_name> -p <install_path> [options]
```

| Option | Description |
|--------|-------------|
| `-j, --job` | Job folder path (required) |
| `-s, --site-name` | Target site name (required) |
| `-p, --install-path` | Installation path (required) |
| `-ts, --shared-path` | Shared libs path (default: `<install_path>/../libs`) |
| `--shared` | Shared library folder to include |
| `-r, --requirements` | Requirements.txt file |

## Examples

### Production Deployment with Docker

```bash
# Build images for all sites
nvflare pre-install docker -j jobs/fedavg -s server -t myregistry/nvflare-server:v1.0
nvflare pre-install docker -j jobs/fedavg -s site-1 -t myregistry/nvflare-site1:v1.0
nvflare pre-install docker -j jobs/fedavg -s site-2 -t myregistry/nvflare-site2:v1.0

# Push to registry
docker login myregistry
docker push myregistry/nvflare-server:v1.0
docker push myregistry/nvflare-site1:v1.0
docker push myregistry/nvflare-site2:v1.0
```

### POC with Local Installation

```bash
# Prepare POC
nvflare poc prepare -n 2
# Creates: /tmp/nvflare/poc/example_project/prod_00/

# Install to each site's local/custom directory
POC_DIR="/tmp/nvflare/poc/example_project/prod_00"

nvflare pre-install local -j jobs/fedavg -s server \
    -p $POC_DIR/server/local/custom

nvflare pre-install local -j jobs/fedavg -s site-1 \
    -p $POC_DIR/site-1/local/custom

nvflare pre-install local -j jobs/fedavg -s site-2 \
    -p $POC_DIR/site-2/local/custom

# Start POC
nvflare poc start -ex admin@nvidia.com

# Submit job without custom code
nvflare job submit -j jobs/fedavg --no-byoc
```

## End-to-End Example

For a complete end-to-end example with POC and Docker, see:
[examples/advanced/code-pre-install](../../../examples/advanced/code-pre-install/README.md)

## Installation Paths

### Docker Container

```
/workspace/                     ← Startup kit mounted here
├── local/
│   ├── custom/                 ← App code (pre-installed)
│   │   └── <job_name>/
│   ├── libs/                   ← Shared libs (pre-installed)
│   └── resources.json          ← From startup kit
├── startup/                    ← From startup kit
└── transfer/
```

### Local Installation

```
<poc_workspace>/<site>/
├── local/
│   ├── custom/                 ← App code (installed via -p)
│   │   └── <job_name>/
│   ├── libs/                   ← Shared libs (installed via -ts)
│   └── resources.json
├── startup/
└── transfer/
```

## Job Configuration

When using pre-installed code, update job configs to use absolute paths:

**Before (development):**
```json
{
    "executor": {
        "args": {
            "task_script_path": "src/client.py"
        }
    }
}
```

**After (pre-installed):**
```json
{
    "executor": {
        "args": {
            "task_script_path": "/workspace/local/custom/fedavg/src/client.py"
        }
    }
}
```

## Skip Custom Code on Submit

Use `--no-byoc` flag to skip uploading custom code:

```bash
nvflare job submit -j jobs/fedavg --no-byoc
```
