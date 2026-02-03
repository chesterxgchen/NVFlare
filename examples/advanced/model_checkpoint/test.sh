#!/bin/bash
# Test checkpoint and dict config using NVFlare POC CLI with local dev Docker image

set -e  # Exit on error

PROJECT_NAME="model_checkpoint_test"
POC_WORKSPACE="/tmp/nvflare/poc"
NUM_CLIENTS=2
DOCKER_IMAGE="nvflare-dev-checkpoint-test:latest"

# Cleanup function called on error or exit
cleanup_services() {
    echo
    echo "Cleaning up services..."
    
    # Stop POC services
    echo "  Stopping POC services..."
    nvflare poc stop 2>/dev/null || true
    
    # Force remove any lingering containers
    echo "  Removing Docker containers..."
    docker rm -f flserver site-1 site-2 2>/dev/null || true
    
    echo "Cleanup completed"
}

# Register cleanup function to run on error AND normal exit
trap cleanup_services EXIT

echo "=========================================="
echo "Checkpoint + Dict Config Test (POC CLI)"
echo "=========================================="
echo

# Check prerequisites
echo "Checking prerequisites..."
if ! command -v nvflare &> /dev/null; then
    echo "ERROR: nvflare CLI not found. Please install NVFlare."
    exit 1
fi

if ! command -v docker &> /dev/null; then
    echo "ERROR: Docker not found. Please install Docker."
    exit 1
fi

if ! docker ps &> /dev/null; then
    echo "ERROR: Docker daemon not running. Please start Docker."
    exit 1
fi

echo "✓ Prerequisites OK"
echo

# Step 0a: Prepare data (CIFAR10 + checkpoint)
echo "Step 0a: Preparing data..."
python prepare_data.py
echo "✓ Data ready"
echo

# Step 0b: Build Docker image with dev code (check if rebuild needed)
echo "Step 0b: Checking Docker image..."
REBUILD_NEEDED=false

if docker images ${DOCKER_IMAGE} | grep -q nvflare-dev-checkpoint-test; then
    # Image exists, check if Dockerfile changed
    IMAGE_ID=$(docker images ${DOCKER_IMAGE} --format "{{.ID}}")
    IMAGE_CREATED=$(docker inspect --format='{{.Created}}' ${IMAGE_ID} 2>/dev/null)
    DOCKERFILE_MODIFIED=$(stat -c %Y Dockerfile 2>/dev/null || stat -f %m Dockerfile 2>/dev/null)
    IMAGE_CREATED_TS=$(date -d "$IMAGE_CREATED" +%s 2>/dev/null || date -j -f "%Y-%m-%dT%H:%M:%S" "${IMAGE_CREATED%.*}" +%s 2>/dev/null)
    
    if [ ! -z "$DOCKERFILE_MODIFIED" ] && [ ! -z "$IMAGE_CREATED_TS" ]; then
        if [ $DOCKERFILE_MODIFIED -gt $IMAGE_CREATED_TS ]; then
            echo "⚠ Dockerfile modified after image was built"
            REBUILD_NEEDED=true
        else
            echo "✓ Docker image ${DOCKER_IMAGE} exists and is up to date"
        fi
    else
        echo "✓ Docker image ${DOCKER_IMAGE} exists (could not verify if up to date)"
    fi
else
    echo "Docker image not found"
    REBUILD_NEEDED=true
fi

if [ "$REBUILD_NEEDED" = true ]; then
    echo "Building Docker image with development code..."
    ./build_docker.sh
    echo "✓ Docker image built"
fi
echo

# Step 1: Clean any existing POC
echo "Step 1: Cleaning existing POC..."
if [ -d "${POC_WORKSPACE}" ]; then
    if nvflare poc clean; then
        echo "✓ POC cleaned"
    else
        echo "Note: POC clean had issues (continuing anyway)"
    fi
else
    echo "No existing POC found (nothing to clean)"
fi
echo

# Step 2: Prepare POC environment with local Docker image
echo "Step 2: Preparing POC environment with local Docker image (${NUM_CLIENTS} clients)..."
nvflare poc prepare -n ${NUM_CLIENTS} -d ${DOCKER_IMAGE}
echo "✓ POC environment prepared with Docker"
echo "  docker.sh will mount server/ directory to /workspace/ in container"
echo

# Step 3: Generate checkpoint
echo "Step 3: Generating pre-trained checkpoint..."
python prepare_data.py
if [ ! -f "pretrained_model.pt" ]; then
    echo "ERROR: Failed to generate checkpoint"
    exit 1
fi
echo "✓ Checkpoint generated"
echo

# Step 4: Copy checkpoint to SERVER workspace (will be mounted into Docker)
echo "Step 4: Copying checkpoint to server workspace..."
SERVER_WORKSPACE="${POC_WORKSPACE}/example_project/prod_00/server"
if [ ! -d "${SERVER_WORKSPACE}" ]; then
    echo "ERROR: Server workspace not found at ${SERVER_WORKSPACE}"
    exit 1
fi

# The checkpoint needs to be in the server directory
# When docker.sh runs, it mounts server/ to /workspace/
# So server/pretrained_model.pt becomes /workspace/pretrained_model.pt
cp pretrained_model.pt "${SERVER_WORKSPACE}/"
echo "✓ Checkpoint copied to: ${SERVER_WORKSPACE}/pretrained_model.pt"
echo "  Will be accessible in Docker at: /workspace/pretrained_model.pt"
echo

# Verify checkpoint is NOT in client workspaces
for i in $(seq 1 ${NUM_CLIENTS}); do
    CLIENT_WORKSPACE="${POC_WORKSPACE}/example_project/prod_00/site-${i}"
    if [ -f "${CLIENT_WORKSPACE}/pretrained_model.pt" ]; then
        echo "WARNING: Checkpoint found in client workspace ${i} (should not be there)"
    fi
done
echo

# Step 5: Start POC services (server in Docker, clients locally)
echo "Step 5: Starting server in Docker..."
cd ${POC_WORKSPACE}/example_project/prod_00/server/startup
./docker.sh -d  # Start server in Docker daemon mode
cd - > /dev/null
echo "✓ Server Docker container started"
sleep 3  # Give server time to initialize

echo "Starting clients..."
nvflare poc start -p site-1
nvflare poc start -p site-2
echo "✓ All POC services started"
echo

# Wait for services to be ready
echo "Waiting for services to initialize..."
sleep 5
echo

# Step 6: Export the job
echo "Step 6: Exporting job with dict config + checkpoint path..."
CHECKPOINT_PATH="/workspace/pretrained_model.pt"
python job.py --use_dict_config --checkpoint "${CHECKPOINT_PATH}" --n_clients ${NUM_CLIENTS} --num_rounds 2
JOB_DIR="/tmp/nvflare_job/hello-pt-checkpoint-test"
echo "✓ Job exported to ${JOB_DIR}"
echo

# Step 7: Submit and monitor job with live logs
echo "Step 7: Submitting job and streaming logs..."
ADMIN_WORKSPACE="${POC_WORKSPACE}/example_project/prod_00/admin@nvidia.com"

# Start streaming Docker logs in background
echo "Starting Docker log stream..."
docker logs -f flserver 2>&1 | sed 's/^/[SERVER] /' &
DOCKER_LOGS_PID=$!

# Wait a moment for log streaming to start
sleep 2

# Monitor job progress
echo "Monitoring job progress (streaming server logs above)..."
echo
# Increase timeout to 10 minutes for Docker (slower than local)
python submit_and_monitor.py -j "${JOB_DIR}" -s "${ADMIN_WORKSPACE}" -t 600
JOB_RESULT=$?

# Stop Docker log streaming
kill $DOCKER_LOGS_PID 2>/dev/null || true
wait $DOCKER_LOGS_PID 2>/dev/null || true

echo
if [ $JOB_RESULT -eq 0 ]; then
    echo "✓ Job completed successfully"
else
    echo "⚠ Job failed or timed out (exit code: $JOB_RESULT)"
fi
echo
echo "=========================================="
echo "Test completed!"
echo "=========================================="
echo
echo "Results location:"
echo "  ${POC_WORKSPACE}/example_project/prod_00/server/run_*/workspace"
echo
echo "Log files:"
echo "  Server: ${POC_WORKSPACE}/example_project/prod_00/server/log.txt"
echo "  Site-1: ${POC_WORKSPACE}/example_project/prod_00/site-1/log.txt"
echo "  Site-2: ${POC_WORKSPACE}/example_project/prod_00/site-2/log.txt"
echo
echo "Note: Services will be cleaned up automatically on exit"
echo "To manually clean POC workspace:"
echo "  nvflare poc clean"
echo "  rm -f pretrained_model.pt"
echo
