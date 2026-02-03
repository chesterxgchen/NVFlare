#!/bin/bash
# Interactive test runner - runs one step at a time with verification

set -e  # Exit on error

PROJECT_NAME="model_checkpoint_test"
POC_WORKSPACE="/tmp/nvflare/poc"
NUM_CLIENTS=2
DOCKER_IMAGE="nvflare-dev-checkpoint-test:latest"

# Color output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Cleanup function called on error or exit
cleanup_services() {
    echo
    echo -e "${BLUE}Cleaning up services...${NC}"
    
    # Stop POC services
    echo "  Stopping POC services..."
    nvflare poc stop 2>/dev/null || true
    
    # Force remove any lingering containers
    echo "  Removing Docker containers..."
    docker rm -f flserver site-1 site-2 2>/dev/null || true
    
    echo -e "${GREEN}Cleanup completed${NC}"
}

# Register cleanup function to run on error AND normal exit
trap cleanup_services EXIT

function pause_step() {
    echo
    echo -e "${BLUE}Press Enter to continue to next step (or Ctrl+C to exit)...${NC}"
    read
}

echo "=========================================="
echo "Checkpoint + Dict Config Test (Interactive)"
echo "=========================================="
echo

# Step 0: Build Docker image
echo -e "${GREEN}=== Step 0: Build Docker image ===${NC}"
REBUILD_NEEDED=false

if docker images ${DOCKER_IMAGE} | grep -q nvflare-dev-checkpoint-test; then
    echo "Docker image ${DOCKER_IMAGE} exists"
    
    # Check if Dockerfile changed
    IMAGE_ID=$(docker images ${DOCKER_IMAGE} --format "{{.ID}}")
    IMAGE_CREATED=$(docker inspect --format='{{.Created}}' ${IMAGE_ID} 2>/dev/null)
    DOCKERFILE_MODIFIED=$(stat -c %Y Dockerfile 2>/dev/null || stat -f %m Dockerfile 2>/dev/null)
    IMAGE_CREATED_TS=$(date -d "$IMAGE_CREATED" +%s 2>/dev/null || date -j -f "%Y-%m-%dT%H:%M:%S" "${IMAGE_CREATED%.*}" +%s 2>/dev/null)
    
    if [ ! -z "$DOCKERFILE_MODIFIED" ] && [ ! -z "$IMAGE_CREATED_TS" ]; then
        if [ $DOCKERFILE_MODIFIED -gt $IMAGE_CREATED_TS ]; then
            echo -e "${BLUE}⚠ Dockerfile modified after image was built${NC}"
            echo "Rebuild recommended. Rebuild? (y/n) [y]: "
            read -n 1 -r DO_REBUILD
            echo
            if [[ ! $DO_REBUILD =~ ^[Nn]$ ]]; then
                REBUILD_NEEDED=true
            fi
        else
            echo "Image is up to date with Dockerfile"
            echo "Force rebuild anyway? (y/n) [n]: "
            read -n 1 -r FORCE_REBUILD
            echo
            if [[ $FORCE_REBUILD =~ ^[Yy]$ ]]; then
                REBUILD_NEEDED=true
            fi
        fi
    fi
else
    echo "Docker image not found, will build"
    REBUILD_NEEDED=true
fi

if [ "$REBUILD_NEEDED" = true ]; then
    echo "Building Docker image with your development code..."
    pause_step
    ./build_docker.sh
    echo -e "${GREEN}✓ Docker image built${NC}"
else
    echo -e "${GREEN}✓ Using existing Docker image${NC}"
fi
pause_step

# Step 1: Clean existing POC
echo -e "${GREEN}=== Step 1: Clean existing POC ===${NC}"
if [ -d "${POC_WORKSPACE}" ]; then
    echo "Found existing POC at ${POC_WORKSPACE}"
    echo "Cleaning..."
    pause_step
    if nvflare poc clean; then
        echo -e "${GREEN}✓ POC cleaned${NC}"
    else
        echo "Note: POC clean had issues (continuing anyway)"
    fi
else
    echo "No existing POC found (nothing to clean)"
    pause_step
fi
pause_step

# Step 2: Prepare POC
echo -e "${GREEN}=== Step 2: Prepare POC environment ===${NC}"
echo "Running: nvflare poc prepare -n ${NUM_CLIENTS} -d ${DOCKER_IMAGE}"
pause_step
nvflare poc prepare -n ${NUM_CLIENTS} -d ${DOCKER_IMAGE}
echo -e "${GREEN}✓ POC environment prepared${NC}"
echo "Verify: ls ${POC_WORKSPACE}/example_project/prod_00/"
ls ${POC_WORKSPACE}/example_project/prod_00/
pause_step

# Step 3: Generate checkpoint
echo -e "${GREEN}=== Step 3: Generate checkpoint ===${NC}"
echo "Running: python prepare_data.py"
pause_step
python prepare_data.py
if [ ! -f "pretrained_model.pt" ]; then
    echo -e "${RED}ERROR: Failed to generate checkpoint${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Checkpoint generated${NC}"
echo "Verify: ls -lh pretrained_model.pt"
ls -lh pretrained_model.pt
pause_step

# Step 4: Copy checkpoint to server
echo -e "${GREEN}=== Step 4: Copy checkpoint to server workspace ===${NC}"
SERVER_WORKSPACE="${POC_WORKSPACE}/example_project/prod_00/server"
echo "Copying to: ${SERVER_WORKSPACE}/"
pause_step
if [ ! -d "${SERVER_WORKSPACE}" ]; then
    echo -e "${RED}ERROR: Server workspace not found${NC}"
    exit 1
fi
cp pretrained_model.pt "${SERVER_WORKSPACE}/"
echo -e "${GREEN}✓ Checkpoint copied${NC}"
echo "Verify: ls -lh ${SERVER_WORKSPACE}/pretrained_model.pt"
ls -lh ${SERVER_WORKSPACE}/pretrained_model.pt
echo "Checkpoint will be accessible at /workspace/pretrained_model.pt in Docker"
pause_step

# Step 5: Verify docker.sh
echo -e "${GREEN}=== Step 5: Verify docker.sh configuration ===${NC}"
DOCKER_SH="${POC_WORKSPACE}/example_project/prod_00/server/startup/docker.sh"
echo "Checking volume mount in docker.sh..."
echo "Looking for: -v \$DIR/..:/workspace/"
grep "docker run" "${DOCKER_SH}" | grep "\-v"
echo
echo "Checking network mode..."
grep "NETARG=" "${DOCKER_SH}"
pause_step

# Step 6: Start server in Docker
echo -e "${GREEN}=== Step 6: Start server in Docker ===${NC}"
echo "Running: ./docker.sh -d (from server/startup/)"
pause_step
cd ${POC_WORKSPACE}/example_project/prod_00/server/startup
./docker.sh -d
cd - > /dev/null
sleep 3
echo -e "${GREEN}✓ Server Docker container started${NC}"
echo "Verify container is running:"
docker ps | grep flserver
pause_step

# Step 7: Check server logs
echo -e "${GREEN}=== Step 7: Check server logs ===${NC}"
echo "Checking if server started successfully..."
pause_step
docker logs flserver 2>&1 | tail -20
echo
echo "Check for any errors above"
pause_step

# Step 8: Start clients
echo -e "${GREEN}=== Step 8: Start clients ===${NC}"
echo "Starting site-1..."
pause_step
nvflare poc start -p site-1 &
sleep 2
echo "Starting site-2..."
nvflare poc start -p site-2 &
sleep 2
echo -e "${GREEN}✓ All clients started${NC}"
echo "Verify client processes:"
ps aux | grep "site-[12]" | grep -v grep
pause_step

# Step 9: Wait for services
echo -e "${GREEN}=== Step 9: Wait for services to initialize ===${NC}"
echo "Waiting 5 seconds..."
sleep 5
echo -e "${GREEN}✓ Services initialized${NC}"
pause_step

# Step 10: Export and submit the job
echo -e "${GREEN}=== Step 10: Export the job ===${NC}"
CHECKPOINT_PATH="/workspace/pretrained_model.pt"
echo "Running: python job.py --use_dict_config --checkpoint ${CHECKPOINT_PATH}"
echo "This will export a job with:"
echo "  - Dict model config: {'path': 'model.SimpleNetwork'}"
echo "  - Checkpoint: ${CHECKPOINT_PATH}"
pause_step
python job.py --use_dict_config --checkpoint "${CHECKPOINT_PATH}" --n_clients ${NUM_CLIENTS} --num_rounds 2
JOB_DIR="/tmp/nvflare_job/hello-pt-checkpoint-test"
echo -e "${GREEN}✓ Job exported to ${JOB_DIR}${NC}"
pause_step

# Step 11: Submit and monitor job with live logs
echo -e "${GREEN}=== Step 11: Submit and monitor job ===${NC}"
ADMIN_WORKSPACE="${POC_WORKSPACE}/example_project/prod_00/admin@nvidia.com"
echo "This will:"
echo "  - Start streaming Docker server logs in real-time"
echo "  - Submit the job via FLARE API"
echo "  - Monitor progress until completion"
echo "  - Timeout: 10 minutes (Docker is slower than local)"
pause_step

# Start streaming Docker logs in background
echo -e "${BLUE}Starting Docker log stream...${NC}"
docker logs -f flserver 2>&1 | sed "s/^/[SERVER] /" &
DOCKER_LOGS_PID=$!

# Wait a moment for log streaming to start
sleep 2

echo -e "${BLUE}Monitoring job progress (logs streaming above)...${NC}"
echo
python submit_and_monitor.py -j "${JOB_DIR}" -s "${ADMIN_WORKSPACE}" -t 600
JOB_RESULT=$?

# Stop Docker log streaming
kill $DOCKER_LOGS_PID 2>/dev/null || true
wait $DOCKER_LOGS_PID 2>/dev/null || true

echo
if [ $JOB_RESULT -eq 0 ]; then
    echo -e "${GREEN}✓ Job completed successfully${NC}"
else
    echo -e "${RED}⚠ Job failed or timed out (exit code: $JOB_RESULT)${NC}"
fi
pause_step

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
