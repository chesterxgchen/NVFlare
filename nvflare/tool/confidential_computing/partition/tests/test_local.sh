#!/bin/bash

set -e  # Exit on error

# Helper Functions
log() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')] $1${NC}"
}

error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}" >&2
    exit 1
}

# Version comparison helper
verify_version() {
    local current="$1"
    local required="$2"
    
    # Convert versions to arrays
    IFS='.' read -ra current_arr <<< "$current"
    IFS='.' read -ra required_arr <<< "$required"
    
    # Compare each component
    for i in "${!required_arr[@]}"; do
        if [ "${current_arr[i]:-0}" -lt "${required_arr[i]}" ]; then
            return 1
        elif [ "${current_arr[i]:-0}" -gt "${required_arr[i]}" ]; then
            return 0
        fi
    done
    return 0
}

handle_error() {
    local error_type="$1"
    local component="$2"
    local message="$3"

    case "$error_type" in
        "disk_full")
            log "ERROR: Disk full in $component: $message"
            sudo df -h
            sudo du -sh "$ROOT_MOUNT/*"
            ;;
        "permission")
            log "ERROR: Permission denied in $component: $message"
            sudo ls -la "$ROOT_MOUNT/$component"
            sudo getfacl "$ROOT_MOUNT/$component"
            ;;
        "corruption")
            log "ERROR: Data corruption in $component: $message"
            sudo dmsetup status
            sudo cryptsetup status "${component}_crypt"
            ;;
        "encryption")
            log "ERROR: Encryption error in $component: $message"
            sudo cryptsetup status "${component}_crypt"
            ;;
        *)
            log "ERROR: Unknown error in $component: $message"
            ;;
    esac
    exit 1
}

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOL_DIR="$(dirname "$SCRIPT_DIR")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

# Required packages
REQUIRED_PACKAGES=(
    "cryptsetup"
    "cryptsetup-bin"
    "cryptsetup-initramfs"
    "cryptsetup-run"
    "dmsetup"
    "lvm2"
    "parted"
    "acl"
    "attr"  # for extended attributes
    "jq"
    "util-linux"
    "coreutils"
    "e2fsprogs"
    "kmod"
    "systemd"
)

# Required package versions
declare -A MIN_VERSIONS=(
    ["cryptsetup"]="2.3.0"
    ["systemd"]="245"
    ["e2fsprogs"]="1.45"
    ["lvm2"]="1.02.175"
    ["util-linux"]="2.34"
)

# Install required packages
install_dependencies() {
    log "Checking and installing required packages..."
    
    # Check if apt is available
    if ! command -v apt-get >/dev/null 2>&1; then
        error "This script requires apt package manager"
    fi
    
    # Update package list
    apt-get update || error "Failed to update package list"
    
    # Install packages
    for pkg in "${REQUIRED_PACKAGES[@]}"; do
        if ! dpkg -l | grep -q "^ii.*$pkg"; then
            log "Installing $pkg..."
            apt-get install -y "$pkg" || error "Failed to install $pkg"
        fi
    done
    
    # Verify package versions after installation
    verify_package_versions
    
    log "All required packages installed"
}

# Verify package versions
verify_package_versions() {
    log "Verifying package versions..."

    for pkg in "${!MIN_VERSIONS[@]}"; do
        local min_version="${MIN_VERSIONS[$pkg]}"
        local current_version

        case "$pkg" in
            "cryptsetup")
                current_version=$(cryptsetup --version | grep -oE '[0-9]+\.[0-9]+\.[0-9]+')
                ;;
            "systemd")
                current_version=$(systemctl --version | head -1 | grep -oE '[0-9]+')
                ;;
            "e2fsprogs")
                current_version=$(mkfs.ext4 -V 2>&1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+')
                ;;
            "lvm2")
                current_version=$(dmsetup --version | awk '{print $3}' | grep -oE '^[0-9]+\.[0-9]+\.[0-9]+')
                ;;
            "util-linux")
                current_version=$(mount --version | head -1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+')
                ;;
        esac

        log "Checking $pkg version: current=$current_version, required=$min_version"
        if ! verify_version "$current_version" "$min_version"; then
            error "Package $pkg version $current_version is lower than required $min_version"
        fi
    done
}

# Debug output
log "Script directory: $SCRIPT_DIR"
log "Tool directory: $TOOL_DIR"
log "Current user: $(id)"
log "Current directory: $(pwd)"

# Check if running as root
if [[ $EUID -ne 0 ]]; then
    echo "Please run as root (sudo)"
    exit 1
fi

# Install dependencies first
install_dependencies

# Check required tools
for cmd in losetup cryptsetup dmsetup dd jq; do
    if ! command -v $cmd >/dev/null 2>&1; then
        error "Required command not found: $cmd"
    fi
done

# Check required kernel modules
check_kernel_modules() {
    log "Checking required kernel modules..."
    
    local required_modules=(
        "dm_crypt"
        "dm_verity"
        "aes"
        "sha256"
        "xts"
        "ecb"
        "cbc"
        "hmac"
    )
    
    for module in "${required_modules[@]}"; do
        if ! lsmod | grep -q "^${module}" && ! modprobe -n "$module" 2>/dev/null; then
            error "Required kernel module not available: $module"
        fi
    done
    
    log "All required kernel modules available"
}

# Check hardware capabilities
check_hardware_capabilities() {
    log "Checking hardware capabilities..."

    # Check CPU AES support
    if ! grep -q '^flags.*aes' /proc/cpuinfo; then
        error "CPU does not support AES instructions"
    fi

    # Check available memory
    local mem_available=$(free -m | awk '/^Mem:/ {print $7}')
    if [ "$mem_available" -lt 1024 ]; then
        error "Insufficient memory available: ${mem_available}M (need at least 1024M)"
    fi

    # Check disk space
    local disk_space=$(df -m "$PWD" | awk 'NR==2 {print $4}')
    if [ "$disk_space" -lt 2048 ]; then
        error "Insufficient disk space: ${disk_space}M (need at least 2048M)"
    fi

    log "Hardware capabilities meet requirements"
}

# Make sure scripts are executable
setup_scripts() {
    log "Setting up script permissions..."
    
    local scripts=(
        "${TOOL_DIR}/setup_partitions.sh"
        "${TOOL_DIR}/cleanup_partitions.sh"
        "${TOOL_DIR}/verify_partitions.sh"
    )
    
    for script in "${scripts[@]}"; do
        if [ ! -f "$script" ]; then
            error "Required script not found: $script"
        fi
        chmod +x "$script" || error "Failed to make executable: $script"
    done
}

# Setup Functions
setup_test_env() {
    log "Setting up test environment..."
    
    # Setup script permissions first
    setup_scripts
    
    # Create test config directory
    TEST_CONFIG_DIR="/tmp/nvflare_test_config"
    mkdir -p $TEST_CONFIG_DIR
    chmod 755 $TEST_CONFIG_DIR
    
    # Create test config files
    create_test_configs
    
    # Create test disk image
    TEST_IMG="test_disk.img"
    dd if=/dev/zero of=$TEST_IMG bs=1M count=2048 2>/dev/null
    
    # Setup loop device
    LOOP_DEV=$(losetup -f)
    losetup $LOOP_DEV $TEST_IMG || error "Failed to setup loop device"
    
    # Export device for partition script
    export DEVICE=$LOOP_DEV
    export MOCK_CVM=1
    
    # Create test mount point
    export ROOT_MOUNT="/tmp/nvflare_test"
    mkdir -p $ROOT_MOUNT
    chmod 755 $ROOT_MOUNT
    
    log "Test environment ready:"
    log "- Device: $DEVICE"
    log "- Mount: $ROOT_MOUNT"
    log "- Config: $TEST_CONFIG_DIR"
}

create_test_configs() {
    # Create partition.conf with test values
    cat > "$TEST_CONFIG_DIR/partition.conf" <<EOF
# Base paths
ROOT_MOUNT=/tmp/nvflare_test
DEVICE=$LOOP_DEV

# Root filesystem partition
ROOT_FS_SIZE=512M
ROOT_FS_TYPE=verity
ROOT_FS_MOUNT=\${ROOT_MOUNT}/root
ROOT_FS_ENCRYPTION=none

# Workspace partition
WORKSPACE_SIZE=512M
WORKSPACE_TYPE=crypt
WORKSPACE_MOUNT=\${ROOT_MOUNT}/workspace
WORKSPACE_ENCRYPTION=required

# Job store partition
JOBSTORE_SIZE=512M
JOBSTORE_TYPE=crypt
JOBSTORE_MOUNT=\${ROOT_MOUNT}/jobs
JOBSTORE_ENCRYPTION=optional

# Temporary filesystem
TMPFS_SIZE=256M
TMPFS_TYPE=tmpfs
TMPFS_MOUNT=\${ROOT_MOUNT}/tmp
TMPFS_ENCRYPTION=none

# Encryption settings
CRYPT_CIPHER=aes-xts-plain64
CRYPT_KEYSIZE=512
CRYPT_HASH=sha256

# Verity settings
VERITY_HASH=sha256
VERITY_DATABLOCK=4096
VERITY_HASHBLOCK=4096

# Tmpfs settings
TMPFS_MODE=1777
TMPFS_UID=0
TMPFS_GID=0

# System settings
SWAP_ENABLED=false
EOF

    # Create partition_config.sh with test values
    cat > "$TEST_CONFIG_DIR/partition_config.sh" <<EOF
#!/bin/bash

# Source configuration
SCRIPT_DIR="\$(cd "\$(dirname "\${BASH_SOURCE[0]}")" && pwd)"
source "\${SCRIPT_DIR}/partition.conf"

# Allow environment overrides
ROOT_MOUNT="\${NVFLARE_ROOT:-\$ROOT_MOUNT}"
DEVICE="\${NVFLARE_DEVICE:-\$DEVICE}"

# Build partition array
declare -A PARTITIONS=(
    ["root-fs"]="\${ROOT_FS_SIZE}:\${ROOT_FS_TYPE}:\${ROOT_FS_MOUNT}:\${ROOT_FS_ENCRYPTION}"
    ["workspace"]="\${WORKSPACE_SIZE}:\${WORKSPACE_TYPE}:\${WORKSPACE_MOUNT}:\${WORKSPACE_ENCRYPTION}"
    ["job-store"]="\${JOBSTORE_SIZE}:\${JOBSTORE_TYPE}:\${JOBSTORE_MOUNT}:\${JOBSTORE_ENCRYPTION}"
    ["tmp-fs"]="\${TMPFS_SIZE}:\${TMPFS_TYPE}:\${TMPFS_MOUNT}:\${TMPFS_ENCRYPTION}"
)
EOF
}

# Test Functions
test_config_validation() {
    log "Testing configuration validation..."
    
    # Save original config
    cp "$TEST_CONFIG_DIR/partition.conf" "$TEST_CONFIG_DIR/partition.conf.bak"
    
    # Test valid configuration
    source "$TEST_CONFIG_DIR/partition_config.sh" || error "Failed to source valid config"
    
    # Test invalid configurations
    local INVALID_CONFIGS=(
        "ROOT_MOUNT=''"  # Empty value
        "ROOT_MOUNT='/invalid/path'"  # Invalid path
        "ROOT_FS_SIZE=invalid"
        "ROOT_FS_TYPE=invalid"
        "ROOT_FS_ENCRYPTION=invalid"
        "CRYPT_KEYSIZE=invalid"
        "TMPFS_MODE=99999"
    )
    
    for invalid in "${INVALID_CONFIGS[@]}"; do
        log "Testing invalid config: $invalid"
        
        # Restore original config
        cp "$TEST_CONFIG_DIR/partition.conf.bak" "$TEST_CONFIG_DIR/partition.conf"
        
        # Add invalid config
        echo "$invalid" >> "$TEST_CONFIG_DIR/partition.conf"
        
        # Source should fail
        if NVFLARE_ROOT="" source "$TEST_CONFIG_DIR/partition_config.sh" 2>/dev/null; then
            error "Configuration validation should fail for: $invalid"
        fi
    done
    
    # Restore original config
    cp "$TEST_CONFIG_DIR/partition.conf.bak" "$TEST_CONFIG_DIR/partition.conf"
    rm -f "$TEST_CONFIG_DIR/partition.conf.bak"
    
    log "Configuration validation tests passed"
}

test_partition_setup() {
    log "Testing partition setup..."
    
    # Use test config
    export NVFLARE_CONFIG_DIR=$TEST_CONFIG_DIR
    
    # Run setup script
    $TOOL_DIR/setup_partitions.sh || error "Partition setup failed"
    
    # Verify partitions
    $TOOL_DIR/verify_partitions.sh || error "Partition verification failed"
    
    log "Partition setup successful"
}

test_operations() {
    log "Testing basic operations..."
    
    test_readonly_partitions
    test_encrypted_partitions
    test_integrity_protection
    test_access_controls
    test_tampering
    test_tmpfs_operations
    test_error_conditions
    test_ml_patterns
    test_jobstore_encryption
    test_key_management
    test_system_state
    test_performance
    log "All operations tests passed"
}

test_readonly_partitions() {
    log "Testing read-only partitions..."
    
    # Create test file in root partition
    echo "test content" | sudo tee "$ROOT_MOUNT/root/test_file" > /dev/null || \
        handle_error "permission" "root" "Failed to create test file"
    
    # Verify read access
    sudo cat "$ROOT_MOUNT/root/test_file" || \
        handle_error "permission" "root" "Cannot read from root partition"
    
    # Verify write protection
    local write_tests=(
        "dd if=/dev/zero of=$ROOT_MOUNT/root/test bs=1M count=1"
        "touch $ROOT_MOUNT/root/newfile"
        "echo 'test' > $ROOT_MOUNT/root/test"
    )
    
    for cmd in "${write_tests[@]}"; do
        if sudo sh -c "$cmd" 2>/dev/null; then
            handle_error "permission" "root" "Write operation should fail: $cmd"
        fi
    done
}

test_encrypted_partitions() {
    log "Testing encrypted partitions..."
    local raw_device=$(sudo dmsetup deps -o devname $DEVICE | grep -o '[^[:space:]]*')

    # Test workspace (required encryption)
    local test_data=(
        "model weights: 1234567890"
        "training data: ABCDEFGHIJK"
        "gradients: [0.1, 0.2, 0.3]"
    )

    for data in "${test_data[@]}"; do
        local test_file="$ROOT_MOUNT/workspace/data_${RANDOM}.txt"
        
        # Write data
        echo "$data" | sudo tee "$test_file" > /dev/null || \
            handle_error "disk_full" "workspace" "Failed to write test data"
        
        # Verify data is accessible within CVM
        sudo grep -q "$data" "$test_file" || \
            handle_error "corruption" "workspace" "Data not readable in workspace"
        
        # Verify data is encrypted on disk
        if sudo strings "/dev/$raw_device" | grep -q "$data"; then
            handle_error "encryption" "workspace" "Found unencrypted data"
        fi
    done
}

test_integrity_protection() {
    log "Testing integrity protection..."
    
    # Get verity device info
    local root_device=$(sudo dmsetup deps -o devname | grep root-fs | grep -o '[^[:space:]]*')
    
    # Try to modify raw device
    if sudo dd if=/dev/zero of="/dev/$root_device" bs=1M count=1 conv=notrunc 2>/dev/null; then
        # Verify integrity check fails
        if sudo cat "$ROOT_MOUNT/root/test_file" 2>/dev/null; then
            handle_error "corruption" "root" "Integrity check should fail after modification"
        fi
    fi
}

test_access_controls() {
    log "Testing access controls..."

    # Test workspace access (encrypted, should be accessible in mock CVM)
    if ! sudo test -w $ROOT_MOUNT/workspace; then
        error "Workspace should be writable in CVM"
    fi

    # Test job store with different encryption modes
    case "$JOBSTORE_ENCRYPTION" in
        "required")
            if ! sudo test -w $ROOT_MOUNT/jobs; then
                error "Job store should be writable with required encryption"
            fi
            ;;
        "optional")
            # Test both encrypted and unencrypted access
            sudo touch $ROOT_MOUNT/jobs/test || \
                error "Job store should be writable with optional encryption"
            ;;
        "none")
            if sudo test -w $ROOT_MOUNT/jobs; then
                error "Job store should not be writable without encryption"
            fi
            ;;
    esac
}

test_tampering() {
    log "Testing tampering detection..."

    # Test verity-protected partitions
    local verity_parts=("root" "launcher" "config")
    for part in "${verity_parts[@]}"; do
        local device="/dev/mapper/${part}_verity"
        if [ -e "$device" ]; then
            # Try to modify through device mapper
            if sudo dd if=/dev/zero of="$device" bs=1M count=1 conv=notrunc 2>/dev/null; then
                error "Should not be able to modify verity device: $device"
            fi

            # Verify reads still work
            if ! sudo head -n1 "$ROOT_MOUNT/${part}/test_file" 2>/dev/null; then
                log "Verified: reads fail after tampering attempt on $part"
            fi
        fi
    done

    # Test encrypted partitions
    local crypt_parts=("workspace" "jobs")
    for part in "${crypt_parts[@]}"; do
        local device="/dev/mapper/${part}_crypt"
        if [ -e "$device" ]; then
            # Try to modify encrypted data directly
            if sudo dd if=/dev/zero of="$device" bs=1M count=1 conv=notrunc 2>/dev/null; then
                # Should fail or data should be corrupted
                if sudo cat "$ROOT_MOUNT/${part}/test_file" 2>/dev/null; then
                    error "Data should be corrupted after tampering: $part"
                fi
            fi
        fi
    done
}

test_tmpfs_operations() {
    log "Testing tmpfs operations..."
    
    # Test data isolation
    local test_data="sensitive_training_data_${RANDOM}"
    local test_file="$ROOT_MOUNT/tmp/test"
    
    # Write test
    echo "$test_data" | sudo tee "$test_file" > /dev/null || \
        handle_error "permission" "tmp" "Failed to write to tmpfs"

    # Read test
    sudo grep -q "$test_data" "$test_file" || \
        handle_error "corruption" "tmp" "Failed to read from tmpfs"

    # Verify data is not written to disk
    if grep -r "$test_data" /var/log/ /tmp/ /var/tmp/ 2>/dev/null; then
        handle_error "encryption" "tmp" "Found tmpfs data on disk"
    fi

    # Test data clearing on unmount
    sudo umount "$ROOT_MOUNT/tmp"
    sudo mount -t tmpfs -o size=256M tmpfs "$ROOT_MOUNT/tmp"
    if sudo grep -q "$test_data" "$ROOT_MOUNT/tmp/"* 2>/dev/null; then
        handle_error "encryption" "tmp" "Data persisted after tmpfs remount"
    fi
}

test_error_conditions() {
    log "Testing error conditions..."

    # Test disk full condition
    log "Testing disk full handling..."
    local large_file="$ROOT_MOUNT/workspace/large_file"
    if dd if=/dev/zero of="$large_file" bs=1M count=1024 2>/dev/null; then
        error "Should fail when disk is full"
    fi

    # Test permission errors
    log "Testing permission handling..."
    if sudo -u nobody touch "$ROOT_MOUNT/workspace/test" 2>/dev/null; then
        error "Non-root user should not have access"
    fi

    # Test concurrent access
    log "Testing concurrent access..."
    (
        sudo dd if=/dev/zero of="$ROOT_MOUNT/workspace/file1" bs=1M count=100 &
        sudo dd if=/dev/zero of="$ROOT_MOUNT/workspace/file2" bs=1M count=100 &
        wait
    ) || error "Concurrent access failed"
}

test_ml_patterns() {
    log "Testing ML specific patterns..."

    # Get raw device for encryption verification
    local raw_device=$(sudo dmsetup deps -o devname $DEVICE | grep -o '[^[:space:]]*')

    # Test model file patterns
    local ml_patterns=(
        '{"weights": [0.1234, -0.5678, 1.2345]}'
        '{"gradients": {"layer1": [0.01, -0.02], "layer2": [0.03, -0.04]}}'
        '{"metrics": {"accuracy": 0.9876, "loss": 0.1234}}'
        '{"hyperparameters": {"learning_rate": 0.001, "batch_size": 32}}'
    )

    for pattern in "${ml_patterns[@]}"; do
        # Write to workspace
        echo "$pattern" | sudo tee "$ROOT_MOUNT/workspace/ml_${RANDOM}.json" > /dev/null

        # Verify encryption
        if sudo strings "/dev/$raw_device" | grep -q "$pattern"; then
            error "Found unencrypted ML data: $pattern"
        fi
    done

    # Test large model files
    dd if=/dev/urandom of="model.bin" bs=1M count=100
    sudo cp model.bin "$ROOT_MOUNT/workspace/"
    rm model.bin

    # Verify large file handling
    if ! sudo test -f "$ROOT_MOUNT/workspace/model.bin"; then
        error "Failed to handle large model file"
    fi
}

test_jobstore_encryption() {
    log "Testing job store encryption modes..."

    # Get raw device for encryption verification
    local raw_device=$(sudo dmsetup deps -o devname $DEVICE | grep -o '[^[:space:]]*')

    # Test required encryption mode
    if [ "$JOBSTORE_ENCRYPTION" = "required" ]; then
        # Write test result
        echo '{"final_model": {"accuracy": 0.95}}' | \
            sudo tee "$ROOT_MOUNT/jobs/result.json" > /dev/null || \
            handle_error "permission" "jobs" "Failed to write result"

        # Verify encryption
        if sudo strings "/dev/$raw_device" | grep -q "accuracy"; then
            handle_error "encryption" "jobs" "Found unencrypted result data"
        fi
    fi

    # Test optional encryption mode
    if [ "$JOBSTORE_ENCRYPTION" = "optional" ]; then
        # Test both encrypted and unencrypted data
        echo '{"intermediate": {"loss": 0.1}}' | \
            sudo tee "$ROOT_MOUNT/jobs/intermediate.json" > /dev/null
        
        # Verify data is readable
        if ! sudo jq . "$ROOT_MOUNT/jobs/intermediate.json" >/dev/null 2>&1; then
            handle_error "corruption" "jobs" "Cannot read job store data"
        fi
    fi
}

test_key_management() {
    log "Testing key management..."

    # Verify keys are in memory only
    if grep -r "LUKS" /var/log/ /tmp/ /var/tmp/ 2>/dev/null; then
        handle_error "encryption" "keys" "Found key material on disk"
    fi

    # Test key slots
    for part in workspace jobs; do
        if [ -e "/dev/mapper/${part}_crypt" ]; then
            # Verify only one key slot is in use
            local key_slots=$(sudo cryptsetup luksDump "/dev/mapper/${part}_crypt" | grep "Key Slot" | grep "ENABLED" | wc -l)
            if [ "$key_slots" -ne 1 ]; then
                handle_error "encryption" "$part" "Unexpected number of key slots: $key_slots"
            fi
        fi
    done
}

test_system_state() {
    log "Testing system state..."

    # Verify swap is disabled
    if swapon --show | grep -q .; then
        handle_error "system" "swap" "Swap should be disabled"
    fi

    # Check memory pressure
    local memory_available=$(free -m | awk '/^Mem:/ {print $7}')
    if [ "$memory_available" -lt 1024 ]; then
        handle_error "system" "memory" "Low memory available: ${memory_available}M"
    fi

    # Check disk encryption status
    if ! sudo dmsetup status | grep -q "crypt"; then
        handle_error "system" "encryption" "Encryption not active"
    fi

    # Check verity status
    if ! sudo dmsetup status | grep -q "verity"; then
        handle_error "system" "verity" "Verity not active"
    fi
}

test_performance() {
    log "Testing I/O performance..."

    # Test parameters
    local sizes=("1M" "10M" "100M")
    local iterations=3
    local results=()

    for size in "${sizes[@]}"; do
        log "Testing with size $size"
        
        # Test encrypted write performance
        local write_time=$(TIMEFORMAT='%R'; time (
            dd if=/dev/urandom of="$ROOT_MOUNT/workspace/perf_test" bs=$size count=1 2>/dev/null
        ) 2>&1)
        results+=("Write ${size}: ${write_time}s")

        # Test encrypted read performance
        local read_time=$(TIMEFORMAT='%R'; time (
            dd if="$ROOT_MOUNT/workspace/perf_test" of=/dev/null bs=$size count=1 2>/dev/null
        ) 2>&1)
        results+=("Read ${size}: ${read_time}s")

        # Clean up
        sudo rm -f "$ROOT_MOUNT/workspace/perf_test"
    done

    # Report results
    log "Performance test results:"
    printf '%s\n' "${results[@]}" | sudo tee -a "$ROOT_MOUNT/tmp/perf_results.txt"
}

# Cleanup test environment
cleanup_test_env() {
    log "Cleaning up test environment..."
    
    # Cleanup partitions
    if [ -x "${TOOL_DIR}/cleanup_partitions.sh" ]; then
        "${TOOL_DIR}/cleanup_partitions.sh" || log "Warning: Cleanup script failed"
    fi
    
    # Remove loop device
    if [ -n "$DEVICE" ] && losetup -a | grep -q "$DEVICE"; then
        losetup -d "$DEVICE" || log "Warning: Failed to detach loop device"
    fi
    
    # Remove test files
    rm -f "$TEST_IMG" 2>/dev/null || true
    rm -rf "$ROOT_MOUNT" 2>/dev/null || true
    rm -rf "$TEST_CONFIG_DIR" 2>/dev/null || true
    
    log "Cleanup complete"
}

# Main function
main() {
    # Ensure we're not running on a real CVM
    if dmesg | grep -qE "Confidential|SEV-SNP|TDX guest"; then
        error "This test should not be run on a real CVM"
    fi
    
    # Check hardware and kernel capabilities
    check_hardware_capabilities
    check_kernel_modules
    
    # Run tests
    trap cleanup_test_env EXIT
    setup_test_env
    test_config_validation
    test_partition_setup
    test_operations
    
    log "All tests passed successfully!"
}

# Run main
main "$@" 