#!/bin/bash
# Build local Docker image with dev code

set -e

IMAGE_NAME="nvflare-dev-checkpoint-test"
IMAGE_TAG="latest"

echo "=========================================="
echo "Building NVFlare Dev Docker Image"
echo "=========================================="
echo

# Check if we're in the right directory
if [ ! -f "../../../nvflare/__init__.py" ]; then
    echo "ERROR: Must run from examples/model_checkpoint directory"
    echo "Current directory: $(pwd)"
    echo "Expected to find: ../../../nvflare/__init__.py"
    exit 1
fi

echo "Building Docker image: ${IMAGE_NAME}:${IMAGE_TAG}"
echo "This will include the current development code..."
echo

# Build from the NVFlare root directory (go up 2 levels from examples/model_checkpoint/)
cd ../../..
docker build -f examples/advanced/model_checkpoint/Dockerfile -t ${IMAGE_NAME}:${IMAGE_TAG} .

echo
echo "✓ Docker image built successfully: ${IMAGE_NAME}:${IMAGE_TAG}"
echo
echo "To use this image with POC:"
echo "  nvflare poc prepare -n 2 -d ${IMAGE_NAME}:${IMAGE_TAG}"
echo
