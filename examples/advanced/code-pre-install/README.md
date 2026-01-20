# Code Pre-Installation Example

This example demonstrates how to use NVFLARE's code pre-installer for production deployments.

## Overview

In production environments, application code often needs to be pre-installed due to:
- Security policies restricting dynamic code loading (no BYOC - Bring Your Own Code)
- Network isolation requirements
- Need for consistent, reproducible deployments
- Docker-based infrastructure

The pre-installer provides two commands:
- `nvflare pre-install docker` - Build Docker images with pre-installed code
- `nvflare pre-install local` - Install code locally (for POC)

## Prerequisites

- Docker installed and running (for Docker deployment)
- NVFLARE installed (`pip install nvflare`)
- Example job directory: [jobs/fedavg](./jobs/fedavg)

## Option 1: POC with Docker

### Step 1: Prepare POC Environment

```bash
# Create a POC workspace with 2 clients
nvflare poc prepare -n 2

# This creates startup kits at:
# /tmp/nvflare/poc/example_project/prod_00/
# ├── admin@nvidia.com/
# ├── server/
# ├── site-1/
# └── site-2/
```

### Step 2: Build Docker Images

```bash
cd examples/advanced/code-pre-install

# Build Docker image for server
nvflare pre-install docker -j jobs/fedavg -s server \
    -t nvflare-server:latest

# Build Docker image for site-1
nvflare pre-install docker -j jobs/fedavg -s site-1 \
    -t nvflare-site1:latest

# Build Docker image for site-2
nvflare pre-install docker -j jobs/fedavg -s site-2 \
    -t nvflare-site2:latest
```

### Step 3: Start POC with Docker

```bash
nvflare poc start -ex admin@nvidia.com --docker
```

### Step 4: Submit Job

```bash
# Start admin console
nvflare poc start -p admin@nvidia.com

# Or use CLI
nvflare job submit -j jobs/fedavg --no-byoc
```

### Step 5: Stop POC

```bash
nvflare poc stop
```

## Option 2: POC with Local Installation

### Step 1: Prepare POC Environment

```bash
nvflare poc prepare -n 2
```

### Step 2: Install Code Locally

```bash
cd examples/advanced/code-pre-install

POC_DIR="/tmp/nvflare/poc/example_project/prod_00"

# Install to server
nvflare pre-install local -j jobs/fedavg -s server \
    -p $POC_DIR/server/local/custom

# Install to site-1
nvflare pre-install local -j jobs/fedavg -s site-1 \
    -p $POC_DIR/site-1/local/custom

# Install to site-2
nvflare pre-install local -j jobs/fedavg -s site-2 \
    -p $POC_DIR/site-2/local/custom
```

### Step 3: Start POC

```bash
nvflare poc start -ex admin@nvidia.com
```

### Step 4: Submit Job

```bash
nvflare job submit -j jobs/fedavg --no-byoc
```

### Step 5: Stop POC

```bash
nvflare poc stop
```

## Complete Script (Docker)

```bash
#!/bin/bash
set -e

EXAMPLE_DIR="examples/advanced/code-pre-install"
JOB_DIR="$EXAMPLE_DIR/jobs/fedavg"

echo "=== Step 1: Prepare POC ==="
nvflare poc prepare -n 2

echo "=== Step 2: Build Docker Images ==="
nvflare pre-install docker -j $JOB_DIR -s server -t nvflare-server:latest
nvflare pre-install docker -j $JOB_DIR -s site-1 -t nvflare-site1:latest
nvflare pre-install docker -j $JOB_DIR -s site-2 -t nvflare-site2:latest

echo "=== Step 3: Start POC with Docker ==="
nvflare poc start -ex admin@nvidia.com --docker

echo "=== Step 4: Submit Job ==="
sleep 10
nvflare job submit -j $JOB_DIR --no-byoc

echo "=== Job submitted! ==="
echo "Monitor with: nvflare poc start -p admin@nvidia.com"
```

## Complete Script (Local)

```bash
#!/bin/bash
set -e

EXAMPLE_DIR="examples/advanced/code-pre-install"
JOB_DIR="$EXAMPLE_DIR/jobs/fedavg"
POC_DIR="/tmp/nvflare/poc/example_project/prod_00"

echo "=== Step 1: Prepare POC ==="
nvflare poc prepare -n 2

echo "=== Step 2: Install Code Locally ==="
nvflare pre-install local -j $JOB_DIR -s server -p $POC_DIR/server/local/custom
nvflare pre-install local -j $JOB_DIR -s site-1 -p $POC_DIR/site-1/local/custom
nvflare pre-install local -j $JOB_DIR -s site-2 -p $POC_DIR/site-2/local/custom

echo "=== Step 3: Start POC ==="
nvflare poc start -ex admin@nvidia.com

echo "=== Step 4: Submit Job ==="
sleep 10
nvflare job submit -j $JOB_DIR --no-byoc

echo "=== Job submitted! ==="
echo "Monitor with: nvflare poc start -p admin@nvidia.com"
```

## Directory Structure

### Docker Container

```
/workspace/                              ← Startup kit mounted here
├── local/
│   ├── custom/                          ← Pre-installed (baked in image)
│   │   └── fedavg/
│   │       └── src/client.py
│   ├── libs/                            ← Pre-installed shared libs
│   ├── authorization.json.default
│   └── resources.json.default
├── startup/                             ← From startup kit (mounted)
│   ├── fed_client.json
│   └── start.sh
└── transfer/
```

### Local Installation

```
/tmp/nvflare/poc/example_project/prod_00/site-1/
├── local/
│   ├── custom/                          ← Installed via pre-install local
│   │   └── fedavg/
│   │       └── src/client.py
│   ├── libs/                            ← Installed shared libs
│   ├── authorization.json.default
│   └── resources.json.default
├── startup/
│   ├── fed_client.json
│   └── start.sh
└── transfer/
```

## Job Configuration

When using pre-installed code, update job configs to use absolute paths:

**Before (development with custom/ folder):**
```json
{
    "executor": {
        "args": {
            "task_script_path": "src/client.py"
        }
    }
}
```

**After (with pre-installed code):**
```json
{
    "executor": {
        "args": {
            "task_script_path": "/workspace/local/custom/fedavg/src/client.py"
        }
    }
}
```

See [jobs/fedavg_preinstall](./jobs/fedavg_preinstall) for a complete example.

## Command Reference

### Docker Build

```bash
nvflare pre-install docker -j <job_folder> -s <site_name> [options]
```

| Option | Description |
|--------|-------------|
| `-j, --job` | Job folder path (required) |
| `-s, --site-name` | Target site name (required) |
| `-t, --tag` | Docker image tag |
| `--base-image` | Base Docker image |

### Local Install

```bash
nvflare pre-install local -j <job_folder> -s <site_name> -p <install_path>
```

| Option | Description |
|--------|-------------|
| `-j, --job` | Job folder path (required) |
| `-s, --site-name` | Target site name (required) |
| `-p, --install-path` | Installation path (required) |

### Job Submit

```bash
nvflare job submit -j <job_folder> --no-byoc
```

The `--no-byoc` flag skips uploading local custom code, using pre-installed code instead.
