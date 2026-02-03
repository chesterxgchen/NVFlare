# Checkpoint and Dict Config Test

This example tests the new recipe interface features:
1. **initial_ckpt parameter**: Load pre-trained model weights from a checkpoint file
2. **Dict model config**: Specify model using `{"path": "module.Class", "args": {...}}`
3. **Job submission and monitoring via FLARE API**: Proper session lifecycle management

## Quick Start

**Step 1: Test locally first (recommended)**
```bash
cd examples/advanced/model_checkpoint
python test_local_poc.py --use_dict_config --checkpoint /tmp/test_checkpoint.pt
```
This runs a simple local POC without Docker to verify dict config and checkpoint work correctly.

**Step 2: Test with Docker (after Step 1 passes)**
```bash
./test.sh
```
This runs the full Docker-based test with server in container and real-time log streaming.

---

## Testing Strategy

This directory contains multiple test approaches. **Start simple and add complexity incrementally.**

### Test 1: Local POC (Recommended First)

**Purpose**: Verify dict config and checkpoint work in basic POC without Docker complexity.

**Run:**
```bash
# Test with dict config + checkpoint
python test_local_poc.py --use_dict_config --checkpoint /tmp/test_checkpoint.pt

# Test with dict config only (no checkpoint)
python test_local_poc.py --use_dict_config

# Test with model instance + checkpoint (baseline)
python test_local_poc.py --checkpoint /tmp/test_checkpoint.pt
```

**What it tests:**
- ✓ Dict model config: `{"path": "model.SimpleNetwork"}`
- ✓ Checkpoint loading: `initial_ckpt` parameter
- ✓ All processes run locally (no containers)
- ✓ Quick feedback (< 1 minute)

**Expected outcome:**
- Job completes with `FINISHED:COMPLETED` status
- No `EXECUTION_EXCEPTION`
- Results directory created in `/tmp/nvflare/poc`

### Test 2: Docker POC (After Test 1 passes)

**Purpose**: Test with server in Docker container (production-like setup).

**Run:**
```bash
./test.sh
```

**What it tests:**
- ✓ Everything from Test 1
- ✓ Server runs in Docker with dev code
- ✓ Clients run locally
- ✓ Checkpoint accessible only in server container
- ✓ Volume mounts and networking
- ✓ FLARE API job submission and monitoring
- ✓ Real-time Docker log streaming

**Expected outcome:**
- Docker container starts successfully
- Job completes with `FINISHED:COMPLETED` status
- Automatic log display on error
- Server logs streamed in real-time with `[SERVER]` prefix

---

## Key Features Verified

✓ **Dict Model Config**: Job config correctly captures `{"path": "model.SimpleNetwork"}` in persistor  
✓ **Checkpoint Path**: Server-side checkpoint `/workspace/pretrained_model.pt` properly configured  
✓ **FLARE API Monitoring**: Using `submit_and_monitor.py` with proper session lifecycle to avoid "cannot schedule new futures after shutdown" errors

---

## How Docker Integration Works (for reference)

1. **POC generates `docker.sh`** at `server/startup/docker.sh`:
   ```bash
   DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
   # $DIR = /tmp/nvflare/poc/example_project/prod_00/server/startup
   
   NETARG="--net=host"  # Uses host network for localhost communication
   docker run -d --rm --name=$svr_name \
       -v $DIR/..:/workspace/ \    # Mounts server/ to /workspace/
       -w /workspace \
       --net=host \
       $DOCKER_IMAGE /bin/bash -c "..."
   ```

2. **Volume mount:**
   - Host: `/tmp/nvflare/poc/example_project/prod_00/server/`
   - Container: `/workspace/`
   - Result: `server/pretrained_model.pt` → `/workspace/pretrained_model.pt`

3. **Network configuration:**
   - `--net=host`: Container shares host's network namespace
   - Server binds to localhost:8002 (fed learn) and localhost:8003 (admin)
   - Clients on host connect to localhost:8002
   - No port mapping needed

4. **Starting the server:**
   ```bash
   nvflare poc start
   ```
   This runs `docker.sh` which starts the container with your dev code

5. **Checkpoint access:**
   - Only in server workspace (not accessible to clients)
   - Server: `/workspace/pretrained_model.pt`
   - Clients: Cannot access this file

## Files

```
examples/advanced/model_checkpoint/
├── Dockerfile               # Dockerfile for local dev image
├── build_docker.sh          # Build local Docker image with dev code
├── client.py                # Client training script (wrapper for hello-pt)
├── job.py                   # Recipe configuration with dict config + initial_ckpt
├── model.py                 # SimpleNetwork model definition
├── prepare_data.py          # Generate pre-trained checkpoint
├── submit_and_monitor.py    # Submit job and monitor via FLARE API
├── test_local_poc.py        # TEST 1: Simple local POC (no Docker) - START HERE
├── test.sh                  # TEST 2: Automated Docker test
├── test_interactive.sh      # TEST 2: Interactive Docker test
└── README.md                # This file
```

## Manual Steps (Docker Test)

### Step 0: Build Local Docker Image

Build a Docker image with the current development code:

```bash
./build_docker.sh
```

This creates `nvflare-dev-checkpoint-test:latest` with your local NVFlare code.

### Step 1: Prepare POC Environment with Local Docker Image

```bash
# Clean existing POC
nvflare poc clean

# Prepare POC with local Docker image
nvflare poc prepare -n 2 -d nvflare-dev-checkpoint-test:latest
```

This will:
- Create server that runs in Docker container **with your dev code**
- Create 2 client processes (run locally with dev code)
- Generate startup scripts including `docker.sh`

### Step 2: Generate and Place Checkpoint

```bash
# Generate checkpoint
python prepare_data.py

# Copy to SERVER workspace only
# docker.sh mounts server/ directory to /workspace/ in the container
# So server/pretrained_model.pt becomes /workspace/pretrained_model.pt
cp pretrained_model.pt /tmp/nvflare/poc/example_project/prod_00/server/
```

**Important:** 
- Checkpoint is placed in `/tmp/nvflare/poc/example_project/prod_00/server/`
- `docker.sh` script runs from `server/startup/` and mounts `server/` to `/workspace/`
- Inside Docker, the path becomes `/workspace/pretrained_model.pt`
- Do NOT copy to client workspaces (site-1, site-2, etc.)

### Step 3: Start POC Services (with Docker)

```bash
nvflare poc start
```

This starts:
- **Server in Docker container** (localhost:8002/8003)
- Clients as local processes
- Admin console

### Step 4: Create and Submit Job

```bash
# Create job with dict config
# Use /workspace/pretrained_model.pt (path inside Docker container)
python job.py --use_dict_config --checkpoint /workspace/pretrained_model.pt --n_clients 2 --num_rounds 2

# Submit and monitor job using FLARE API (recommended - handles session lifecycle properly)
python submit_and_monitor.py -j /tmp/nvflare_job/hello-pt-checkpoint-test \
    -s /tmp/nvflare/poc/example_project/prod_00/admin@nvidia.com \
    -t 300

# Alternative: Submit manually via CLI (not recommended - requires manual monitoring)
# nvflare job submit -j /tmp/nvflare_job/hello-pt-checkpoint-test
```

**Path Explanation:**
- On host: `/tmp/nvflare/poc/example_project/prod_00/server/pretrained_model.pt`
- `docker.sh` mounts: `server/` → `/workspace/`
- In Docker: `/workspace/pretrained_model.pt`

### Step 5: Monitor Job

```bash
# Check POC status
nvflare poc status

# View server logs
tail -f /tmp/nvflare/poc/example_project/prod_00/server/log.txt
```

## Test Variations

### Test 1: Dict Config + Checkpoint (Primary Test)

```bash
python job.py --use_dict_config --checkpoint pretrained_model.pt
```

Tests:
- ✓ Dict model config: `{"path": "model.SimpleNetwork"}`
- ✓ Checkpoint loading on server
- ✓ Dynamic model instantiation in PTFileModelPersistor

### Test 2: Model Instance + Checkpoint (Baseline)

```bash
python job.py --checkpoint pretrained_model.pt
```

Tests:
- ✓ Traditional model instance approach
- ✓ Checkpoint loading on server

### Test 3: Dict Config Only (No Checkpoint)

```bash
python job.py --use_dict_config --checkpoint ""
```

Tests:
- ✓ Dict config with random initialization
- ✓ No checkpoint file needed

## Expected Behavior

### Server Logs

```
Loading model from checkpoint: /workspace/pretrained_model.pt
Model config detected as dict, will dynamically instantiate model
Instantiating model from: model.SimpleNetwork
Successfully loaded checkpoint
```

### Client Logs

```
site = site-1, current_round=1
Received model from server (initialized from checkpoint)
```

### Checkpoint Location Verification

```bash
# Should exist (server workspace on host)
ls /tmp/nvflare/poc/example_project/prod_00/server/pretrained_model.pt

# Inside Docker container, accessible at:
# /workspace/pretrained_model.pt
# Because docker.sh mounts server/ directory to /workspace/

# Should NOT exist (client workspaces)
ls /tmp/nvflare/poc/example_project/prod_00/site-1/pretrained_model.pt  # Not found
ls /tmp/nvflare/poc/example_project/prod_00/site-2/pretrained_model.pt  # Not found
```

**Volume Mount by docker.sh:**
```bash
# docker.sh is at: server/startup/docker.sh
# It runs: docker run -v $DIR/..:/workspace/
# Where $DIR = server/startup/
# So $DIR/.. = server/
# Result: server/ → /workspace/
```

## Cleanup

```bash
# Stop POC (this stops the Docker container and all services)
nvflare poc stop

# Clean POC workspace
nvflare poc clean

# Remove generated files
rm -f pretrained_model.pt
rm -rf /tmp/nvflare_job/hello-pt-checkpoint-test

# Remove Docker image if you want to rebuild (optional)
# Only needed if NVFlare code or dependencies changed
docker rmi nvflare-dev-checkpoint-test:latest
```

**Important:** 
- Always use `nvflare poc stop` instead of `docker stop` directly
- The Docker image is cached and reused on subsequent runs
- Only remove/rebuild the image if your NVFlare code changes

## Troubleshooting

### Network Issues

**Problem:** Clients can't connect to server
- Cause: Server not using `--net=host`
- Solution: Verify NETARG in docker.sh:
  ```bash
  grep "NETARG" /tmp/nvflare/poc/example_project/prod_00/server/startup/docker.sh
  ```
  Should see: `NETARG="--net=host"`

**Problem:** Port already in use
- Cause: Previous POC instance still running
- Solution: `nvflare poc stop` (don't use `docker stop` directly)

**Problem:** Server starts but clients timeout
- Solution: Verify ports are listening:
  ```bash
  netstat -an | grep 8002  # Fed learn port
  netstat -an | grep 8003  # Admin port
  ```

### Volume Mount Issues

**Problem:** Checkpoint not found on server
- Verify: `ls /tmp/nvflare/poc/example_project/prod_00/server/pretrained_model.pt`
- Ensure you copied it AFTER `nvflare poc prepare`

**Problem:** Server can't find model.py for dict config
- The job.py script should automatically add model.py to job custom folder
- Verify: `ls /tmp/nvflare_job/hello-pt-checkpoint-test/app/custom/model.py`

### Verify Volume Mount

After `nvflare poc prepare`, check the generated docker.sh:
```bash
cat /tmp/nvflare/poc/example_project/prod_00/server/startup/docker.sh
```

Look for the volume mount line:
```bash
docker run -d --rm --name=$svr_name -v $DIR/..:/workspace/ -w /workspace
```

**File mapping:**
```
Host: /tmp/nvflare/poc/.../server/pretrained_model.pt  → Container: /workspace/pretrained_model.pt
Host: /tmp/nvflare/poc/.../server/startup/              → Container: /workspace/startup/
```

## Notes

- Tests the branch `2.7_recipe_interface_part2_stage`
- Uses POC mode (not production deployment)
- Checkpoint is server-only by design (tests realistic scenario)
- Docker image is cached and auto-rebuilds only when Dockerfile changes
- Always run Test 1 (local) before Test 2 (Docker) to isolate issues
