# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Required packages
REQUIRED_PACKAGES=(
    "cryptsetup:2.2"
    "cryptsetup-bin:2.2"
    "cryptsetup-initramfs:2.2"
    "cryptsetup-run:2.2"
    "dmsetup:1.02"
    "lvm2:2.03"
    "parted:3.3"
    "acl:2.2"
    "attr:2.4"
    "jq:1.6"
    "net-tools:1.60"
    "iptables:1.8"
    "systemd:245"
    "kmod:27"
    "util-linux:2.34"
    "coreutils:8.30"
    "e2fsprogs:1.45"
    "netcat:1.10"
    "iproute2:5.5"
    "procps:3.3"
)

# Version comparison function
version_compare() {
    local v1="$1"
    local v2="$2"
    
    if [[ "$v1" == "$v2" ]]; then
        return 0
    fi
    
    local IFS=.
    local i ver1=($v1) ver2=($v2)
    
    # Fill empty positions with zeros
    for ((i=${#ver1[@]}; i<${#ver2[@]}; i++)); do
        ver1[i]=0
    done
    for ((i=${#ver2[@]}; i<${#ver1[@]}; i++)); do
        ver2[i]=0
    done
    
    # Compare version numbers
    for ((i=0; i<${#ver1[@]}; i++)); do
        if [[ -z ${ver2[i]} ]]; then
            ver2[i]=0
        fi
        if ((10#${ver1[i]} > 10#${ver2[i]})); then
            return 1
        fi
        if ((10#${ver1[i]} < 10#${ver2[i]})); then
            return 2
        fi
    done
    return 0
}

# Check package version
check_package_version() {
    local pkg="$1"
    local min_version="$2"
    local current_version
    
    # Get installed version
    current_version=$(dpkg-query -W -f='${Version}' "$pkg" 2>/dev/null | sed 's/[^0-9.]*\([0-9.]*\).*/\1/')
    if [ -z "$current_version" ]; then
        return 1
    fi
    
    # Compare versions
    version_compare "$current_version" "$min_version"
    local result=$?
    
    if [ "$result" -eq 2 ]; then
        return 1
    fi
    return 0
}

# Install dependencies
install_dependencies() {
    log "Installing required packages..."
    
    # Check if apt is available
    if ! command -v apt-get >/dev/null 2>&1; then
        error "This script requires apt package manager"
    fi
    
    # Update package list
    apt-get update || error "Failed to update package list"
    
    # Map packages to their commands
    declare -A PKG_COMMANDS=(
        ["lvm2"]="lvm"
        ["cryptsetup"]="cryptsetup"
        ["parted"]="parted"
        ["systemd"]="systemctl"
        ["iptables"]="iptables"
        ["dmsetup"]="dmsetup"
    )
    
    # Install packages
    for pkg_spec in "${REQUIRED_PACKAGES[@]}"; do
        # Split package spec into name and version
        IFS=':' read -r pkg min_version <<< "$pkg_spec"
        
        if ! dpkg -l | grep -q "^ii.*$pkg"; then
            log "Installing $pkg..."
            apt-get install -y "$pkg" || error "Failed to install $pkg"
        fi

        # Check version after installation
        if ! check_package_version "$pkg" "$min_version"; then
            error "Package $pkg version $(dpkg-query -W -f='${Version}' "$pkg") is lower than required $min_version"
        fi

        # Verify command is available after package installation
        if [[ -n "${PKG_COMMANDS[$pkg]}" ]]; then
            if ! command -v "${PKG_COMMANDS[$pkg]}" >/dev/null 2>&1; then
                error "Command ${PKG_COMMANDS[$pkg]} not found after installing $pkg"
            fi
        fi
    done
    
    log "All required packages installed"
}

# Test environment
TEST_ROOT="/tmp/nvflare_test"

# Cleanup function
cleanup() {
    log "Cleaning up test environment..."
    
    # Stop any running services
    systemctl stop nvflare-* 2>/dev/null || true
    
    # Remove test directories
    rm -rf "$TEST_ROOT"
    
    # Reset firewall rules
    iptables -F
    iptables -X
    
    # Unmount any test partitions
    for mp in $(mount | grep nvflare_test | cut -d' ' -f3); do
        umount "$mp" 2>/dev/null || true
    done
    
    # Remove device mappings
    dmsetup remove_all 2>/dev/null || true
    
    log "Cleanup completed"
}

# Set trap for cleanup
trap cleanup EXIT

# Create test environment
setup_env() {
    log "Setting up test environment..."
    mkdir -p "$TEST_ROOT"
    
    # Save original configurations
    if [ -f "/etc/iptables/rules.v4" ]; then
        cp "/etc/iptables/rules.v4" "$TEST_ROOT/iptables.backup"
    fi
}

# Run pre-test checks
pre_test_checks() {
    log "Running pre-test checks..."
    
    # Install dependencies first
    install_dependencies

    # Check required commands
    local required_cmds=(
        "cryptsetup"
        "lvm"
        "parted"
        "systemctl"
        "iptables"
        "dmsetup"
    )
    
    for cmd in "${required_cmds[@]}"; do
        if ! command -v "$cmd" >/dev/null 2>&1; then
            error "Required command not found: $cmd"
        fi
    done
    
    # Check kernel modules
    local required_modules=(
        "dm_crypt"
        "dm_verity"
    )
    
    for module in "${required_modules[@]}"; do
        if ! lsmod | grep -q "^${module}"; then
            if ! modprobe "$module" 2>/dev/null; then
                error "Required kernel module not available: $module"
            fi
        fi
    done
} 