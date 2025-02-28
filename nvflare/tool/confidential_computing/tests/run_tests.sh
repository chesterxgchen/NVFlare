#!/bin/bash

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

# Helper Functions
log() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')] $1${NC}"
}

error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}" >&2
    exit 1
}

# Build test container
log "Building test container..."
docker build -t nvflare-security-test -f tests/Dockerfile .

# Run tests in container
log "Running tests in container..."
docker run --privileged \
    -v "$(pwd):/nvflare" \
    --name nvflare-test \
    nvflare-security-test \
    ./test_all.sh

# Cleanup
log "Cleaning up..."
docker rm -f nvflare-test || true 