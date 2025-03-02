# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../config/partition.conf"
source "${SCRIPT_DIR}/../config/security.conf"
source "${SCRIPT_DIR}/../config/tee.conf"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Logging functions
log() {
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}" >&2
    exit 1
}

warning() {
    echo -e "${YELLOW}[$(date '+%Y-%m-%d %H:%M:%S')] WARNING: $1${NC}" >&2
}

success() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')] SUCCESS: $1${NC}"
}

# Common validation functions
check_root() {
    if [[ $EUID -ne 0 ]]; then
        error "This script must be run as root"
    fi
}

check_output_dir() {
    if [ ! -d "$OUTPUT_DIR" ]; then
        log "Creating output directory: $OUTPUT_DIR"
        mkdir -p "$OUTPUT_DIR" || error "Failed to create output directory"
    fi
}

check_device() {
    if [ -z "$TARGET_DEVICE" ]; then
        return 0  # Skip check if device not specified
    fi
    if [ ! -b "$TARGET_DEVICE" ]; then
        error "Target device not found: $TARGET_DEVICE"
    fi
}

check_mount_point() {
    local mount_point="$1"
    if mountpoint -q "$mount_point" 2>/dev/null; then
        error "Mount point already in use: $mount_point"
    fi
}

check_image() {
    if [ ! -d "$OUTPUT_DIR" ]; then
        error "Output directory not found: $OUTPUT_DIR"
    fi
    
    if [ ! -f "$OUTPUT_IMAGE" ]; then
        error "Image not found: $OUTPUT_IMAGE"
    fi
}

# Common cleanup function
cleanup() {
    local exit_code=$?
    
    # Unmount any mounted filesystems
    for mount in "${ROOT_MOUNT}" "${APP_MOUNT}" "${RO_MOUNT}" "${DYNAMIC_MOUNT}"; do
        if mountpoint -q "$mount" 2>/dev/null; then
            umount "$mount" || warning "Failed to unmount $mount"
        fi
    done
    
    # Close any open LUKS devices
    for name in root_crypt app_crypt; do
        if [ -e "/dev/mapper/$name" ]; then
            cryptsetup close "$name" || warning "Failed to close $name"
        fi
    done
    
    # Remove temporary directories
    if [ -d "$ROOT_MOUNT" ]; then
        rm -rf "$ROOT_MOUNT" || warning "Failed to remove $ROOT_MOUNT"
    fi
    
    exit $exit_code
}

# Set trap for cleanup
trap cleanup EXIT 