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

# Test helper functions
mount_image() {
    local test_dir="$1"
    guestmount -a "$OUTPUT_IMAGE" -i "$test_dir" || error "Failed to mount image"
}

unmount_image() {
    local test_dir="$1"
    guestunmount "$test_dir" || warning "Failed to unmount image"
}

setup_test() {
    local test_dir=$(mktemp -d)
    mount_image "$test_dir"
    echo "$test_dir"
}

cleanup_test() {
    local test_dir="$1"
    unmount_image "$test_dir"
    rm -rf "$test_dir"
}

# Common functions for test scripts
... 