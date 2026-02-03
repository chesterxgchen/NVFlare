FROM python:3.10-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy the entire NVFlare development code to /nvflare_dev
COPY . /nvflare_dev

# Install NVFlare with PyTorch dependencies from local source (development code)
# The [pt] extra includes torch and torchvision dependencies
# Use --root-user-action=ignore to suppress pip root warning in Docker
RUN cd /nvflare_dev && pip install --no-cache-dir --root-user-action=ignore -e .[pt]

# Install tensorboard for experiment tracking (required by add_experiment_tracking)
RUN pip install --no-cache-dir --root-user-action=ignore tensorboard

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Note: The actual startup kit will be mounted at /workspace by docker.sh
# The startup directory structure will be:
# /workspace/
#   ├── server/           <- Server startup kit (mounted from POC)
#   ├── site-1/          <- Client 1 startup kit
#   ├── site-2/          <- Client 2 startup kit
#   └── admin@nvidia.com/

# Set working directory to /workspace (will contain mounted startup kit)
WORKDIR /workspace

# Default command - this is NOT how POC server starts!
# When docker.sh runs with -d flag, it overrides CMD with the actual server command:
# docker run ... /bin/bash -c "python -u -m nvflare.private.fed.app.server.server_train -m /workspace -s fed_server.json ..."
# The CMD below is just a fallback if you run the container manually without docker.sh
CMD ["/bin/bash"]
