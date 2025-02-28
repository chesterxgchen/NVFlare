FROM ubuntu:20.04

# Install dependencies
RUN apt-get update && apt-get install -y \
    cryptsetup \
    lvm2 \
    parted \
    acl \
    attr \
    jq \
    net-tools \
    iptables \
    systemd \
    kmod \
    util-linux \
    coreutils \
    e2fsprogs \
    netcat \
    iproute2 \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /nvflare

# Copy test files
COPY . .

# Make scripts executable
RUN chmod +x test_all.sh \
    && chmod +x system_hardening/tests/test_local.sh \
    && chmod +x partition/tests/test_local.sh 